"""
- Dispatches the checker scripts (into the message queue)
- Revoke pending checker script at the end of the round
- Collect checker script results (in case of failure / timeout) and stores them in the database


For each round, a single "Task Group" is created, which can be used to manage all tasks of one round together.

"""

import itertools
import json
import os
import random
import time
from typing import Dict, List, Tuple, Optional, Any

from billiard.exceptions import WorkerLostError
from celery import group, states
from celery.canvas import Signature
from celery.result import GroupResult, AsyncResult
from sqlalchemy import func

from checker_runner.runner import run_checkerscript, celeryapp, run_checkerscript_external
from controlserver.logger import log
from controlserver.models import Team, Service, LogMessage, CheckerResult, db
from gamelib import flag_ids
from saarctf_commons.config import get_redis_connection, CONFIG, SCOREBOARD_PATH, FLAG_ROUNDS_VALID


class Dispatcher:
	# Singleton (for better cache usage)
	default = None  # type: Dispatcher

	def __init__(self):
		# caches, also stored in Redis
		self.round_taskgroups: Dict[int, GroupResult] = {}
		self.round_combination_ids: Dict[int, List[Tuple[int, int]]] = {}

	def dispatch_checker_scripts(self, roundnumber: int):
		redis = get_redis_connection()
		if CONFIG.get('dispatcher_check_vpn_status', False):
			teams = Team.query.filter((Team.vpn_connected == True) | (Team.vpn2_connected == True)).all()
		else:
			teams = Team.query.all()
		services = Service.query.order_by(Service.id).filter(Service.checker_enabled == True).all()
		combinations = list(itertools.product(teams, services))
		if len(combinations) > 0:
			random.shuffle(combinations)
			taskgroup_sig: Signature = group([self.__prepare_checker_script(team, service, roundnumber) for team, service in combinations])
			taskgroup: GroupResult = taskgroup_sig.apply_async()
			taskgroup.save()
			self.round_taskgroups[roundnumber] = taskgroup
			combination_ids = [(team.id, service.id) for team, service in combinations]
			self.round_combination_ids[roundnumber] = combination_ids
			redis.set('dispatcher:taskgroup:{}:order'.format(roundnumber), json.dumps(combination_ids))
			redis.set('dispatcher:taskgroup:{}:id'.format(roundnumber), taskgroup.id)
			self.create_flagid_json(teams, services, roundnumber)

	def __prepare_checker_script(self, team: Team, service: Service, roundnumber, package=None):
		if service.checker_subprocess:
			run_func = run_checkerscript_external
			timeout = service.checker_timeout + 5
		else:
			run_func = run_checkerscript
			timeout = service.checker_timeout
		return run_func.signature(
			(
				service.package if not package else package,
				service.checker_script,
				service.id,
				team.id,
				roundnumber
			),
			time_limit=timeout + 5, soft_time_limit=timeout,
			countdown=150 if service.checker_script == 'pendingtest' else None,
			queue=service.checker_route or 'celery'
		)

	def dispatch_test_script(self, team: Team, service: Service, roundnumber: int, package: str = None) -> Tuple[AsyncResult, CheckerResult]:
		# cleanup database
		CheckerResult.query.filter(CheckerResult.team_id == team.id, CheckerResult.service_id == service.id,
								   CheckerResult.round == roundnumber).delete()
		result = CheckerResult(team_id=team.id, service_id=service.id, round=roundnumber, status='PENDING')
		db.session.add(result)
		# dispatch
		sig = self.__prepare_checker_script(team, service, roundnumber, package)
		task: AsyncResult = sig.apply_async()
		result.celery_id = task.id
		db.session.commit()
		return task, result

	def get_round_taskgroup(self, roundnumber: int) -> Optional[GroupResult]:
		if roundnumber not in self.round_taskgroups:
			redis = get_redis_connection()
			group_id = redis.get(f'dispatcher:taskgroup:{roundnumber}:id')
			if not group_id:
				return None
			self.round_taskgroups[roundnumber] = GroupResult.restore(group_id, app=celeryapp)
		return self.round_taskgroups[roundnumber]

	def get_round_combinations(self, roundnumber) -> Optional[List[Tuple[int, int]]]:
		"""
		:param roundnumber:
		:return: The order in which the tasks have been dispatched in this round. None if tasks aren't fully dispatched yet.
		"""
		if roundnumber not in self.round_combination_ids:
			redis = get_redis_connection()
			data = redis.get('dispatcher:taskgroup:{}:order'.format(roundnumber))
			if not data:
				return None
			self.round_combination_ids[roundnumber] = json.loads(data)
		return self.round_combination_ids[roundnumber]

	def revoke_checker_scripts(self, roundnumber: int):
		taskgroup = self.get_round_taskgroup(roundnumber)
		if taskgroup:
			taskgroup.revoke()
		time.sleep(0.5)

	def collect_checker_results(self, roundnumber: int):
		if roundnumber <= 0:
			return

		taskgroup = self.get_round_taskgroup(roundnumber)
		combinations = self.get_round_combinations(roundnumber)
		collect_time = time.time()

		stats = {states.SUCCESS: 0, states.STARTED: 0, states.REVOKED: 0, states.FAILURE: 0}
		if taskgroup and combinations:
			for (team_id, service_id), result in zip(combinations, taskgroup.results):
				try:
					status = result.status
				except WorkerLostError:
					status = states.FAILURE
				if status == states.RETRY or status == states.PENDING:
					status = states.REVOKED
				stats[status] += 1
				if status == states.FAILURE:
					# timeout or critical (exception)
					r = result.get(propagate=False)
					is_timeout = isinstance(r, Exception) and 'TimeLimitExceeded' in repr(type(r))
					db_result = CheckerResult(round=roundnumber, service_id=service_id, team_id=team_id, celery_id=result.id)
					if is_timeout:
						db_result.status = 'TIMEOUT'
					else:
						db_result.status = 'CRASHED'
						old_result = CheckerResult.query.filter(CheckerResult.round==roundnumber, CheckerResult.service_id==service_id,
																CheckerResult.team_id==team_id).first()
						if old_result:
							db_result.output = old_result.output + '\n' + repr(type(r)) + ' ' + repr(r)
						else:
							db_result.output = repr(type(r)) + ' ' + repr(r)
					db.session.execute(CheckerResult.upsert().values(db_result.props_dict()))
				elif status == states.STARTED:
					# result is here too late
					db_result = CheckerResult(round=roundnumber, service_id=service_id, team_id=team_id, celery_id=result.id)
					db_result.status = 'TIMEOUT'
					db_result.message = 'Service not checked completely'
					db_result.output = 'Still running after round end...'
					db_result.run_over_time = True
					db.session.execute(CheckerResult.upsert().values(db_result.props_dict()))
				elif status == states.REVOKED:
					# never tried to run this task
					db_result = CheckerResult(round=roundnumber, service_id=service_id, team_id=team_id, celery_id=result.id)
					db_result.status = 'REVOKED'
					db_result.message = 'Service not checked'
					db_result.output = 'Not started before the round ended'
					db.session.execute(CheckerResult.upsert().values(db_result.props_dict()))
				elif status == states.SUCCESS:
					result.forget()
			db.session.commit()

			# Warning if time runs out
			if stats[states.REVOKED] > 0:
				log('dispatcher',
					'Not all checker scripts have been executed. {} / {} revoked, {} / {} still active'.format(
						stats[states.REVOKED], len(combinations), stats[states.STARTED], len(combinations)),
					level=LogMessage.WARNING)
			elif stats[states.STARTED] > 0:
				log('dispatcher', 'Not all checker scripts finished in time: {} / {} still active'.format(
					stats[states.STARTED], len(combinations)), level=LogMessage.WARNING)
			else:
				last_finished = db.session.query(func.max(CheckerResult.finished)).filter(CheckerResult.round == roundnumber).scalar()
				if last_finished and collect_time - last_finished.timestamp() <= 3.5:
					log('dispatcher', 'Worker close to overload: Last checker script finished {:.1f} sec before deadline'.format(
						collect_time - last_finished.timestamp()), level=LogMessage.WARNING)

		# Log checker script errors
		# print(stats)
		crashed = db.session.query(CheckerResult.service_id, func.count()) \
			.filter(CheckerResult.round == roundnumber).filter(CheckerResult.status == 'CRASHED') \
			.group_by(CheckerResult.service_id).all()
		for service_id, count in crashed:
			service = Service.query.filter(Service.id == service_id).first()
			log('dispatcher', 'Checker scripts for {} produced {} errors in round {}'.format(service.name, count, roundnumber),
				level=LogMessage.ERROR)

	def get_checker_results(self, roundnumber: int) -> List[CheckerResult]:
		"""
		:param roundnumber:
		:return: All the results of a given round
		"""
		return CheckerResult.query.filter(CheckerResult.round == roundnumber).all()

	def create_flagid_json(self, teams: List[Team], services: List[Service], roundnumber: int):
		data: Dict[str, Any] = {
			'teams': [{
				'id': team.id,
				'name': team.name,
				'ip': team.vulnbox_ip,
				'online': team.vpn_connected or team.vpn2_connected
			} for team in teams]
		}
		for service in services:
			if service.flag_ids:
				flag_id_types = service.flag_ids.split(',')
				if 'flag_ids' not in data: data['flag_ids'] = {}
				data['flag_ids'][service.name] = {}
				for team in teams:
					data['flag_ids'][service.name][team.vulnbox_ip] = {}
					for r in range(max(1, roundnumber - FLAG_ROUNDS_VALID), roundnumber + 1):
						ids = [flag_ids.generate_flag_id(flag_id_type, service.id, team.id, r, i) for i, flag_id_type in enumerate(flag_id_types)]
						if len(ids) == 1:
							data['flag_ids'][service.name][team.vulnbox_ip][r] = ids[0]
						else:
							data['flag_ids'][service.name][team.vulnbox_ip][r] = ids
		with open(os.path.join(SCOREBOARD_PATH, 'attack.json'), 'w') as f:
			json.dump(data, f)


Dispatcher.default = Dispatcher()
