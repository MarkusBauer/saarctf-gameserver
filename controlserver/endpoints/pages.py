"""
Pages for the management interface
"""

import copy
import datetime
import os
import threading
import time
from collections import defaultdict
from math import ceil, floor
from typing import List, Optional, Tuple

from flask import Blueprint, render_template, jsonify, request
from sqlalchemy import distinct, Integer

from controlserver.db_filesystem import DBFilesystem
from controlserver.models import *
from controlserver.vpncontrol import VPNControl
from saarctf_commons.config import get_redis_connection, REDIS, SCOREBOARD_PATH, team_id_to_network_range, FLOWER_AJAX_URL
from controlserver.logger import logResultOfExecution

app = Blueprint('endpoints', __name__)


@app.route('/')
def frontpage():
	from controlserver.timer import Timer, CTFState
	# basic checks - things you should know
	missing_scripts = db.session.query(Service.name).order_by(Service.name) \
		.filter(Service.checker_script_dir.isnot(None)).filter(Service.package.is_(None)).all()
	missing_scoreboard = not os.path.exists(os.path.join(SCOREBOARD_PATH, 'api', 'scoreboard_current.json'))
	unwriteable_scoreboard = not missing_scoreboard and \
							 (not os.access(SCOREBOARD_PATH, os.W_OK | os.X_OK) or
							  not os.access(os.path.join(SCOREBOARD_PATH, 'api'), os.W_OK | os.X_OK) or
							  (os.path.exists(os.path.join(SCOREBOARD_PATH, 'index.css')) and not os.access(os.path.join(SCOREBOARD_PATH, 'index.css'), os.W_OK)))
	teams = Team.query.order_by(Team.id).all()
	# render
	return render_template(
		'index.html', Timer=Timer, CTFState=CTFState,
		missing_scripts=', '.join([service.name for service in missing_scripts]),
		missing_scoreboard=missing_scoreboard,
		unwriteable_scoreboard=unwriteable_scoreboard,
		teams=teams,
		fluid_layout=True,
		flower_ajax_url=FLOWER_AJAX_URL,
		scoreboard_path=SCOREBOARD_PATH
	)


@app.route('/overview/timing')
def overview_timing():
	from controlserver.timer import Timer
	return jsonify({
		'state': Timer.state,
		'desiredState': Timer.desiredState,
		'currentRound': Timer.currentRound,
		'roundStart': Timer.roundStart,
		'roundEnd': Timer.roundEnd,
		'roundTime': Timer.roundTime,
		'lastRound': Timer.stopAfterRound,
		'startAt': Timer.startAt,
		'serverTime': int(time.time()),
		'masterTimers': Timer.countMasterTimer()
	})


@app.route('/overview/set_timing', methods=['POST'])
def overview_set_timing():
	from controlserver.timer import Timer, CTFState
	if 'state' in request.json:
		state = CTFState(request.json['state'])
		if state == CTFState.RUNNING:
			Timer.startCtf()
		elif state == CTFState.SUSPENDED:
			Timer.suspendCtfAfterRound()
		elif state == CTFState.STOPPED:
			Timer.stopCtfAfterRound()
	if 'roundtime' in request.json:
		roundtime = request.json['roundtime']
		if roundtime >= 5 and roundtime < 1000:
			Timer.roundTime = roundtime
	if 'lastround' in request.json:
		lastround = request.json['lastround'] or None
		if lastround is None or lastround > Timer.currentRound:
			Timer.stopAfterRound = lastround
		elif lastround == Timer.currentRound:
			Timer.stopCtfAfterRound()
	if 'startAt' in request.json:
		startAt = request.json['startAt'] or None
		if startAt is None or startAt >= int(time.time()):
			Timer.startAt = startAt
	return 'OK'


@app.route('/overview/logs')
@app.route('/overview/logs/<int:minId>')
def overview_logs(minId: Optional[int] = None):
	if minId is not None:
		logs = LogMessage.query.filter(LogMessage.level >= LogMessage.INFO).filter(LogMessage.id > minId) \
			.order_by(LogMessage.id.desc()).limit(100).all()
	else:
		logs = LogMessage.query.filter(LogMessage.level >= LogMessage.INFO).order_by(LogMessage.id.desc()).limit(30).all()
	log_dicts = LogMessage.serialize_list(logs)
	for log in log_dicts:
		log['created'] = int(log['created'].timestamp())
	return jsonify(log_dicts)


@app.route('/overview/components')
def overview_components():
	clients = [client for client in get_redis_connection().client_list() if int(client['db']) == REDIS['db']]
	clients.sort(key=lambda client: client['name'])
	return jsonify({'redis': clients})


@app.route('/overview/vpn')
def overview_vpn():
	vpn = VPNControl()
	teams = [{'id': team.id, 'name': team.name, 'network': team_id_to_network_range(team.id), 'tick': tick} for team, tick in vpn.get_banned_teams()]
	teams_online = Team.query.filter(Team.vpn_connected == True).count()
	teams_online_once = Team.query.filter(Team.vpn_connected == False, Team.vpn_last_connect != None).count()
	teams_offline = Team.query.filter(Team.vpn_connected == False, Team.vpn_last_connect == None).count()

	# format: dt_bytes, dt_syns, dg_bytes, dg_syns, ut_bytes, ut_syns, ug_bytes, ug_syns
	# list of last X time points, ascending
	last = int(request.args.get('last', 0))
	trafficstats = []
	trafficstats_keys = []
	for line in TeamTrafficStats.query_sum_lite().filter(TeamTrafficStats.time > datetime.datetime.fromtimestamp(last)) \
			.filter(TeamTrafficStats.time <= text('NOW()')).filter(TeamTrafficStats.time >= text("NOW() - interval '12 hours'")) \
			.group_by(TeamTrafficStats.time).order_by(TeamTrafficStats.time.desc()).limit(60).all():
		trafficstats_keys.append(line[0].timestamp())
		trafficstats.append(list(map(int, line[1:])))

	return jsonify({
		'state': vpn.get_state(), 'banned': teams,
		'teams_online': teams_online, 'teams_online_once': teams_online_once, 'teams_offline': teams_offline,
		'traffic_stats': trafficstats[::-1],
		'traffic_stats_keys': trafficstats_keys[::-1]
	})


@app.route('/overview/set_vpn', methods=['POST'])
def overview_set_vpn():
	vpn = VPNControl()
	if 'state' in request.json:
		vpn.set_state(request.json['state'])
	if 'ban' in request.json:
		vpn.ban_team(request.json['ban']['team_id'], request.json['ban']['tick'])
	if 'unban' in request.json:
		vpn.unban_team(request.json['unban'])
	return 'OK'


@app.route('/packages')
@app.route('/packages/')
def packages():
	package_count = db.session.query(func.count(distinct(CheckerFilesystem.package))).scalar()
	file_count, file_size = db.session.query(func.count(CheckerFile.id), func.sum(func.length(CheckerFile.content))).first()
	return render_template(
		'packages.html',
		package_count=package_count, file_count=file_count, file_size=round((file_size or 0) / 1024),
		services=Service.query.order_by(Service.name).all(), teams=Team.query.order_by(Team.name).all()
	)


@app.route('/packages/update', methods=['POST'])
def packages_update():
	dbfs = DBFilesystem()
	messages = []

	if 'service' in request.json and request.json['service']:
		services: List[Service] = Service.query.filter(Service.id == int(request.json['service'])).all()
	else:
		services: List[Service] = Service.query.all()
	changed_packages = []
	for service in services:
		if service.checker_script_dir:
			if not os.path.exists(service.checker_script_dir):
				messages.append(f'[{service.name}] Folder does not exist: "{service.checker_script_dir}"')
				continue
			package, is_new = dbfs.move_folder_to_package(service.checker_script_dir)
			if package != service.package:
				if is_new:
					messages.append('[{}] Created new package: {}'.format(service.name, package))
				else:
					messages.append('[{}] Switching to package: {}'.format(service.name, package))
				service.package = package
				changed_packages.append(package)
			else:
				messages.append('[{}] No updates.'.format(service.name))
			checker_script = service.checker_script.split(':')[0]
			if not os.path.exists(os.path.join(service.checker_script_dir, checker_script)):
				messages.append(f'[{service.name}] Checker script "{checker_script}" not found in path "{service.checker_script_dir}"')
			# try to upload an setup script
			if os.path.exists(os.path.join(service.checker_script_dir, 'dependencies.sh')):
				setup_package = package
			elif os.path.exists(os.path.join(os.path.dirname(service.checker_script_dir), 'dependencies.sh')):
				fname = os.path.join(os.path.dirname(service.checker_script_dir), 'dependencies.sh')
				setup_package, is_new = dbfs.move_single_file_to_package(fname)
			else:
				setup_package = None
			if setup_package != service.setup_package:
				service.setup_package = setup_package
				messages.append(f'[{service.name}] Init script from package: {setup_package}')

	# notify workers, so they will preload these packages
	if changed_packages:
		import checker_runner.runner
		checker_runner.runner.preload_packages.apply_async(args=(changed_packages,), time_limit=120, soft_time_limit=100)

	db.session.commit()
	messages.append('OK')

	return jsonify(messages)


@app.route('/packages/push', methods=['POST'])
def packages_push():
	packages_db = db.session.query(Service.package).all()
	packages = [x for x, in packages_db if x]

	import checker_runner.runner
	checker_runner.runner.preload_packages.apply_async(args=(packages,), time_limit=90, soft_time_limit=60)

	return jsonify('Workers notified about {} packages'.format(len(packages)))


@app.route('/packages/run', methods=['POST'])
def packages_run():
	command = request.json['command']
	if command:
		print(command)
		import checker_runner.runner
		task = checker_runner.runner.run_command.apply_async(args=(command,), time_limit=120, soft_timeout=100)
		print(task)
		return jsonify(task.id)
	return jsonify(False)


@app.route('/packages/test', methods=['POST'])
def packages_test():
	team_id = request.json['team_id']
	service_id = request.json['service_id']
	roundnumber = request.json['round']
	team = Team.query.filter(Team.id == team_id).first()
	service = Service.query.filter(Service.id == service_id).first()
	if not roundnumber:
		min_round = db.session.query(func.min(CheckerResult.round)).filter(CheckerResult.team_id == team_id) \
			.filter(CheckerResult.service_id == service_id).scalar()
		roundnumber = min_round - 1 if min_round is not None and min_round < 0 else -1

	# Check for changed files
	if service.checker_script_dir:
		if not os.path.exists(service.checker_script_dir):
			message = f'Folder "{service.checker_script_dir}" does not exist.'
			package = None
		else:
			dbfs = DBFilesystem()
			package, is_new = dbfs.move_folder_to_package(service.checker_script_dir)
			if package == service.package:
				message = 'Testing with CURRENT script'
			elif is_new:
				message = 'Testing with NEW script "{}"'.format(package)
			else:
				message = 'Testing with OLD script "{}"'.format(package)
	else:
		message = 'Script not managed by package'
		package = None

	from controlserver.dispatcher import Dispatcher
	task, result = Dispatcher.default.dispatch_test_script(team, service, roundnumber, package)
	return jsonify({
		'task': task.id,
		'result_id': result.id,
		'message': message,
		'ident': '{}/{} ({})'.format(service.name, team.name, roundnumber)
	})


@app.route('/checker_status')
@app.route('/checker_status/')
@app.route('/checker_status/<int:roundnumber>')
def checker_status(roundnumber: int = None):
	from controlserver.timer import Timer
	from controlserver.dispatcher import Dispatcher
	if not roundnumber: roundnumber = Timer.currentRound
	count = db.session.query(func.count(CheckerResult.id)).filter(CheckerResult.round == roundnumber) \
		.filter(CheckerResult.status != 'PENDING').filter(CheckerResult.status != 'REVOKED').scalar()
	combinations = Dispatcher.default.get_round_combinations(roundnumber)
	if not combinations:
		return render_template('404.html', message='Round {} has not yet been dispatched.'.format(roundnumber)), 404
	services = Service.query.order_by(Service.name).all()

	# Big table statistics
	results: List[CheckerResult] = db.session.query(CheckerResult.service_id, CheckerResult.status, CheckerResult.time, CheckerResult.finished,
													CheckerResult.run_over_time) \
		.filter(CheckerResult.round == roundnumber).order_by(CheckerResult.finished).all()
	stats_dispatched: Dict[int, int] = defaultdict(lambda: 0)  # service => count
	stats_results: Dict[int, int] = defaultdict(lambda: 0)  # service => count of results
	stats_finished: Dict[int, int] = defaultdict(lambda: 0)  # service => count of non-pending results
	stats_time: Dict[int, float] = defaultdict(lambda: 0.0)  # service => sum of execution time
	stats_time_count: Dict[int, int] = defaultdict(lambda: 0)  # service => number of execution times
	stats_toolate: Dict[int, int] = defaultdict(lambda: 0)  # service => number of too lates
	stats_status: Dict[int, Dict[str, int]] = defaultdict(lambda: defaultdict(lambda: 0))  # service => status => count
	total_status: Dict[str, int] = defaultdict(lambda: 0)
	for team_id, service_id in combinations:
		stats_dispatched[service_id] += 1
	for result in results:
		stats_results[result.service_id] += 1
		if result.status != 'REVOKED' and result.status != 'PENDING':
			stats_finished[result.service_id] += 1
		if result.time:
			stats_time[result.service_id] += result.time
			stats_time_count[result.service_id] += 1
		stats_status[result.service_id][result.status] += 1
		total_status[result.status] += 1
		if result.run_over_time:
			stats_toolate[result.service_id] += 1
	for service in services:
		stats_status[service.id]['PENDING'] += stats_dispatched[service.id] - stats_results[service.id]
		total_status['PENDING'] += stats_dispatched[service.id] - stats_results[service.id]
	total_time = sum(stats_time.values())
	total_time_count = sum(stats_time_count.values())

	# graph data
	redis = get_redis_connection()
	bucketsize = 5
	round_start = int(redis.get(f'round:{roundnumber}:start') or 0)
	round_end = int(redis.get(f'round:{roundnumber}:end') or 0)
	first_finished = None
	last_finished = None
	for r in results:
		if r.finished is not None:
			ts1 = int(floor(r.finished.timestamp()))
			first_finished = ts1 if not first_finished or ts1 < first_finished else first_finished
			ts2 = int(ceil(r.finished.timestamp()))
			last_finished = ts2 if not last_finished or ts2 > last_finished else last_finished
	# List[round => (last_finished, {status => count})]
	finished_per_round: List[Tuple[datetime.datetime, Dict[str, int]]] = []
	no_finished_timestamp = 0
	t = min(round_start, first_finished or round_start)
	i = 0
	finished_per_round.append((datetime.datetime.fromtimestamp(t), defaultdict(lambda: 0)))
	for result in results:
		if result.finished is None:
			no_finished_timestamp += 1
		else:
			while result.finished.timestamp() >= t:
				t += bucketsize
				finished_per_round.append((datetime.datetime.fromtimestamp(t), copy.copy(finished_per_round[i][1])))
				i += 1
			finished_per_round[i][1][result.status if not result.run_over_time else 'TOOLATE'] += 1
	while t < round_end and t < time.time():
		t += bucketsize
		finished_per_round.append((datetime.datetime.fromtimestamp(t), copy.copy(finished_per_round[i][1])))
		i += 1

	return render_template(
		'checker_status.html', roundnumber=roundnumber, services=services, states=CheckerResult.states,
		count_finished=count or 0, count_dispatched=len(combinations),
		server_time=int(time.time()), round_start=round_start, round_start_dt=datetime.datetime.fromtimestamp(round_start), round_end=round_end,
		stats_dispatched=stats_dispatched, stats_finished=stats_finished, stats_time=stats_time, stats_status=stats_status,
		stats_time_count=stats_time_count, stats_toolate=stats_toolate, total_toolate=sum(stats_toolate.values()),
		total_time=total_time, total_time_count=total_time_count, total_status=total_status,
		status_format={'SUCCESS': 'success', 'FLAGMISSING': 'info', 'MUMBLE': 'info', 'OFFLINE': 'info', 'TIMEOUT': 'warning', 'REVOKED': 'danger',
					   'CRASHED': 'danger'},
		finished_per_round=finished_per_round, no_finished_timestamp=no_finished_timestamp, first_finished=first_finished, last_finished=last_finished
	)


@app.route('/checker_status/overview/')
@app.route('/checker_status/overview/all')
@app.route('/checker_status/overview')
def checker_status_overview():
	from controlserver.timer import Timer
	from controlserver.dispatcher import Dispatcher

	if request.url_rule.rule.endswith('/all'):
		first_round = 1
	else:
		first_round = max(Timer.currentRound - 30, 1)
	last_round = Timer.currentRound
	redis = get_redis_connection()
	results_ok = db.session.query(CheckerResult.round, func.count(CheckerResult.id), func.sum(CheckerResult.run_over_time.cast(Integer))).group_by(
		CheckerResult.round) \
		.filter(CheckerResult.round >= first_round).filter(CheckerResult.round <= last_round) \
		.filter(CheckerResult.status.in_(['SUCCESS', 'FLAGMISSING', 'MUMBLE', 'OFFLINE'])).all()
	results_warn = db.session.query(CheckerResult.round, func.count(CheckerResult.id)).group_by(CheckerResult.round) \
		.filter(CheckerResult.round >= first_round).filter(CheckerResult.round <= last_round) \
		.filter(CheckerResult.status == 'TIMEOUT').all()
	results_error = db.session.query(CheckerResult.round, func.count(CheckerResult.id)).group_by(CheckerResult.round) \
		.filter(CheckerResult.round >= first_round).filter(CheckerResult.round <= last_round) \
		.filter(CheckerResult.status == 'CRASHED').all()
	results_revoked = db.session.query(CheckerResult.round, func.count(CheckerResult.id)).group_by(CheckerResult.round) \
		.filter(CheckerResult.round >= first_round).filter(CheckerResult.round <= last_round) \
		.filter(CheckerResult.status == 'REVOKED').all()
	results_last_finished = db.session.query(CheckerResult.round, func.max(CheckerResult.finished)).group_by(CheckerResult.round) \
		.filter(CheckerResult.round >= first_round).filter(CheckerResult.round <= last_round).all()

	rounds = {}
	for i in range(first_round, Timer.currentRound + 1):
		rounds[i] = {
			'number': i,
			'start': datetime.datetime.fromtimestamp(int(redis.get('round:{}:start'.format(i)))),
			'end': datetime.datetime.fromtimestamp(int(redis.get('round:{}:end'.format(i)))),
			'time': int(redis.get('round:{}:time'.format(i))),
			'dispatched': len(Dispatcher.default.get_round_combinations(i) or []),
			'tasks_ok': 0,
			'tasks_warn': 0,
			'tasks_error': 0,
			'tasks_revoked': 0,
			'tasks_toolate': 0,
			'last_finished': None
		}
	for i, count, over_time in results_ok:
		rounds[i]['tasks_ok'] = count - over_time
		rounds[i]['tasks_toolate'] = over_time
	for i, count in results_warn:
		rounds[i]['tasks_warn'] = count
	for i, count in results_error:
		rounds[i]['tasks_error'] = count
	for i, count in results_revoked:
		rounds[i]['tasks_revoked'] = count
	for i, last_finished in results_last_finished:
		rounds[i]['last_finished'] = last_finished
	return render_template('checker_status_overview.html', rounds=rounds, first_round=first_round)


@app.route('/scripts/recreate_scoreboard', methods=['POST'])
def recreate_scoreboard():
	def recreate_scoreboard():
		from controlserver.scoring.scoring import ScoringCalculation
		from controlserver.scoring.scoreboard import Scoreboard
		from controlserver.timer import Timer, CTFState
		scoring = ScoringCalculation()
		scoreboard = Scoreboard(scoring)
		scoreboard.create_scoreboard(0, False, False)
		rn = 0
		end_round: int = Timer.currentRound - 1 if Timer.state == CTFState.RUNNING else Timer.currentRound
		while rn <= end_round:
			scoreboard.create_scoreboard(rn, Timer.state != CTFState.STOPPED or end_round > 0, rn == end_round)
			rn += 1
			end_round: int = Timer.currentRound - 1 if Timer.state == CTFState.RUNNING else Timer.currentRound

	def do_scoreboard():
		logResultOfExecution(
			'scoring',
			recreate_scoreboard, args=(),
			success='Scoreboard generated manually, took {:.1f} sec',
			error='Scoreboard failed (manually): {} {}'
		)

	threading.Thread(target=do_scoreboard(), name='manual_scoreboard', daemon=True).start()
	return jsonify({'ok': True, 'message': 'Recalculation started'})
