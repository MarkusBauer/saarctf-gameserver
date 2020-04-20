"""
Calculate results and ranking for each team/round. That's a two-step process:

Results (TeamPoints):
("service" columns of the scoreboard)
- One entry per round/team/service
- Contains:
	- flags stolen up to this round
	- sla for this service (up to this round)
	- ...

Ranking (TeamRanking):
("team" columns of the scoreboard)
- One entry per round/team
- Contains:
	- total points
	- rank number [1..N]


Want to edit the score calculation? Check `calculate_scoring_for_round` and `calculate_ranking_per_round`.


// Dict key are typically (team_id, service_id).

"""

from collections import defaultdict
from math import sqrt
from typing import Dict, Tuple, List, Union, Iterable, Set
from sqlalchemy import func, alias, distinct, and_, text
from sqlalchemy.orm import aliased, defer
from sqlalchemy.sql.functions import count

from controlserver.logger import log
from controlserver.models import Team, TeamPoints, TeamRanking, SubmittedFlag, db, Service, CheckerResult, TeamPointsLite, CheckerResultLite, \
	LogMessage
from saarctf_commons.config import FLAG_ROUNDS_VALID


class ScoringCalculation:
	def __init__(self):
		self.first_blood_cache_services: Dict[int, Set[int]] = defaultdict(set)  # service_id => {payload1, payload2, ...}

	def scoring_and_ranking(self, roundnumber: int):
		self.calculate_scoring_for_round(roundnumber)
		self.calculate_ranking_per_round(roundnumber)

	# ----- Results ---

	def get_results_for_round_lite(self, roundnumber: int, teams: List[int] = None, services: List[Service] = None) -> Dict[
		Tuple[int, int], TeamPointsLite]:
		"""
		Get the results per team and service from a round, calculate if not present in database
		:param roundnumber:
		:param teams: List of all team IDs
		:param services: List of all services
		:return: Dict mapping (team_id, service_id) to Result
		"""
		if teams is None:
			teams = [id for id, in db.session.query(Team.id).all()]
		if services is None:
			services = Service.query.all()
		if roundnumber <= 0:
			results: Dict[Tuple[int, int], TeamPointsLite] = {}
			for id in teams:
				for service in services:
					results[(id, service.id)] = TeamPointsLite(
						# define here: default points for round 0
						team_id=id, service_id=service.id, round=roundnumber,
						flag_captured_count=0, flag_stolen_count=0,
						off_points=0.0, def_points=0.0, sla_points=0.0
					)
			return results
		else:
			team_points = TeamPointsLite.query().filter(TeamPoints.round == roundnumber).all()
			if len(team_points) < len(teams) * len(services):
				self.calculate_scoring_for_round(roundnumber)
				team_points = TeamPointsLite.query().filter(TeamPoints.round == roundnumber).all()
			return {(tp.team_id, tp.service_id): TeamPointsLite(*tp) for tp in team_points}

	def get_new_results_for_round(self, roundnumber: int, teams: List[int], services: List[Service]) -> Dict[Tuple[int, int], TeamPointsLite]:
		"""
		Return a dict with new / empty results, ready to be filled (and submitted using #save_teampoints)
		:param roundnumber:
		:param teams: all team IDs
		:param services:
		:return:
		"""
		result: Dict[Tuple[int, int], TeamPointsLite] = {}
		for id in teams:
			for service in services:
				if (id, service.id) not in result:
					result[(id, service.id)] = TeamPointsLite(team_id=id, service_id=service.id, round=roundnumber)
		return result

	def save_teampoints(self, roundnumber: int, teampoints: Dict[Tuple[int, int], Union[TeamPoints, TeamPointsLite]]):
		TeamPoints.query.filter(TeamPoints.round == roundnumber).delete()
		TeamPoints.efficient_insert(roundnumber, teampoints.values())
		db.session.commit()

	def get_checker_results(self, roundnumber: int) -> Dict[Tuple[int, int], CheckerResult]:
		if roundnumber <= 0:
			return defaultdict(lambda: CheckerResult(round=roundnumber, status='REVOKED'))
		checker_results: List[CheckerResult] = CheckerResult.query.filter(CheckerResult.round == roundnumber) \
			.options(db.defer(CheckerResult.output)).all()
		result: Dict[Tuple[int, int], CheckerResult] = defaultdict(lambda: CheckerResult(round=roundnumber, status='REVOKED'))
		for r in checker_results:
			result[(r.team_id, r.service_id)] = r
		return result

	def get_checker_results_lite(self, roundnumber: int) -> Dict[Tuple[int, int], CheckerResultLite]:
		if roundnumber <= 0:
			return defaultdict(lambda: CheckerResultLite(0, 0, roundnumber, 'REVOKED'))
		checker_results = db.session.query(
			CheckerResult.team_id, CheckerResult.service_id, CheckerResult.status, CheckerResult.run_over_time, CheckerResult.message) \
			.filter(CheckerResult.round == roundnumber).all()
		result: Dict[Tuple[int, int], CheckerResultLite] = defaultdict(lambda: CheckerResultLite(0, 0, roundnumber, 'REVOKED'))
		for team_id, service_id, status, run_over_time, message in checker_results:
			result[(team_id, service_id)] = CheckerResultLite(team_id, service_id, roundnumber, status, run_over_time, message)
		return result

	def is_first_blood_flag(self, flag: SubmittedFlag, service: Service, write_log=True):
		# check cache if we already found a first blood for this service/payload
		if service.num_payloads > 0 and flag.payload in self.first_blood_cache_services[service.id]:
			return
		if service.num_payloads == 0 and service.id in self.first_blood_cache_services:
			return
		# Check database if we already have a first blood flag
		query = SubmittedFlag.query.filter(SubmittedFlag.service_id == flag.service_id, SubmittedFlag.is_firstblood == True,
										   SubmittedFlag.ts <= flag.ts)
		if service.num_payloads > 0:
			query = query.filter(SubmittedFlag.payload == flag.payload)
		if query.count() == 0:
			# first blood!
			flag.is_firstblood = True
			submitted_by_team = Team.query.get(flag.submitted_by)
			victim_team = Team.query.get(flag.team_id)
			if write_log:
				log('scoring', f'First Blood: "{submitted_by_team.name}" on "{service.name}" (flag {flag.payload})',
					f'Time: {flag.ts.strftime("%H:%M:%S")}\nStolen from: {victim_team.name}\nSubmitted by: {submitted_by_team.name}\nFlag #{flag.id}, payload {flag.payload}, issued in round {flag.round_issued}.',
					level=LogMessage.NOTIFICATION, commit=False)
			self.first_blood_cache_services[service.id].add(flag.payload)
			db.session.add(flag)

	def recompute_first_blood_flags(self):
		"""
		Drop and recompute all first-blood markings on submitted flags. Restart other scoring calculators afterwards (to clear their cache).
		:return:
		"""
		# Remove all previous first blood flags
		SubmittedFlag.query.filter(SubmittedFlag.is_firstblood == True).update({SubmittedFlag.is_firstblood: False})
		self.first_blood_cache_services.clear()
		services = Service.query.all()
		for service in services:
			if service.num_payloads == 0:
				flags = [SubmittedFlag.query.filter(SubmittedFlag.service_id == service.id).order_by(SubmittedFlag.ts, SubmittedFlag.id).first()]
			else:
				data = db.session.execute(text('''
				WITH summary AS (
					SELECT *, ROW_NUMBER() OVER(PARTITION BY payload, service_id ORDER BY ts, round_submitted, id) AS rk
					FROM submitted_flags WHERE service_id=:serviceid
				) SELECT s.id FROM summary s WHERE s.rk = 1'''), {'serviceid': service.id})
				flags = SubmittedFlag.query.filter(SubmittedFlag.id.in_([d['id'] for d in data])).order_by(SubmittedFlag.ts).all()
			for flag in flags:
				self.is_first_blood_flag(flag, service, write_log=False)
		db.session.commit()

	def get_ranking_for_last_rounds(self, roundnumber: int) -> Dict[Tuple[int, int], int]:
		"""
		:param roundnumber:
		:return: Return (round, team_id) => rank for last FLAG_ROUNDS_VALID rounds
		"""
		ranks = db.session.query(TeamRanking.round, TeamRanking.team_id, TeamRanking.rank) \
			.filter(TeamRanking.round >= roundnumber - FLAG_ROUNDS_VALID - 1, TeamRanking.round < roundnumber).all()
		return {(round_number, team_id): rank for round_number, team_id, rank in ranks}

	def get_sla_delta_for(self, service_id: int, roundnumber: int) -> Dict[int, float]:
		"""
		:return: Dict: team_id => sla_delta
		"""
		tp = db.session.query(TeamPoints.team_id, TeamPoints.sla_delta) \
			.filter(TeamPoints.service_id == service_id, TeamPoints.round == roundnumber).all()
		return {team_id: sla_delta for team_id, sla_delta in tp}

	def calculate_scoring_for_round(self, roundnumber: int) -> None:
		"""
		Recalculate the Results for one round.
		If calculation depends on previous results, these are calculated as well.
		:param roundnumber:
		:return:
		"""

		# DO YOUR CALCULATION HERE
		# (and trigger first blood checks)

		# 1. Gather information
		# get the results of the checker scripts (for SLA)
		checker_results = self.get_checker_results(roundnumber)
		# get the results of the previous round, and empty results for this round
		teams: List[int] = [id for id, in db.session.query(Team.id).all()]
		services: List[Service] = Service.query.all()
		services_by_id = {service.id: service for service in services}
		last_round_points = self.get_results_for_round_lite(roundnumber - 1, teams, services)
		new_round_points = self.get_new_results_for_round(roundnumber, teams, services)
		team_rank_in_round = self.get_ranking_for_last_rounds(roundnumber)
		# Old sla_deltas: (service, round) => team_id => sla_delta
		sla_delta_for: Dict[Tuple[int, int], Dict[int, float]] = {(sid, roundnumber): {} for sid in services_by_id}
		# from here on, new_round_points contains the points ONLY from this round, until the last step

		# 2. Calculate SLA and number of active teams
		active_team_ids = set()
		for (team_id, service_id), teampoints in new_round_points.items():
			checker_result = checker_results[(team_id, service_id)]
			if checker_result.status == 'SUCCESS':
				sla_points = 1
			elif checker_result.status == 'CRASHED' or checker_result.status == 'REVOKED':
				# might be our fault, give partial points?
				sla_points = 0
			else:
				sla_points = 0
			if sla_points > 0 or checker_result.status == 'FLAGMISSING':
				active_team_ids.add(team_id)
			teampoints.sla_delta = sla_points  # 0/1
		num_active_teams = max(1, len(active_team_ids))
		for (team_id, service_id), teampoints in new_round_points.items():
			# SLA = (0/1) * sqrt(active_teams)
			teampoints.sla_delta *= sqrt(num_active_teams)
			sla_delta_for[service_id, roundnumber][team_id] = teampoints.sla_delta

		# 3.1 Gather all submitted flags (with number of previous submissions)
		sf1 = aliased(SubmittedFlag)  # submitted flags
		sf2 = aliased(SubmittedFlag)  # count for each flag: # submissions before this round
		sf3 = aliased(SubmittedFlag)  # count for each flag: # submissions this round
		query = db.session.query(sf1, count(distinct(sf2.id)), count(distinct(sf3.id)), func.array_agg(distinct(sf2.submitted_by))) \
			.outerjoin(sf2, and_(sf2.round_submitted < roundnumber, sf2.round_submitted >= roundnumber - FLAG_ROUNDS_VALID - 2,
								 sf1.team_id == sf2.team_id, sf1.service_id == sf2.service_id, sf1.round_issued == sf2.round_issued,
								 sf1.payload == sf2.payload)) \
			.outerjoin(sf3, and_(sf3.round_submitted == roundnumber, sf1.team_id == sf3.team_id, sf1.service_id == sf3.service_id,
								 sf1.round_issued == sf3.round_issued, sf1.payload == sf3.payload)) \
			.filter(sf1.round_submitted == roundnumber).order_by(sf1.ts, sf1.round_submitted, sf1.id) \
			.group_by(sf1) \
			.options(defer(sf1.round_submitted))
		flags = query.all()
		for flag, num_previous_submissions, num_submissions, previous_submitter_ids in flags:
			db.session.expunge(flag)
		# print(f'{len(flags)} flags submitted in round {roundnumber}')
		# 3.2 Distribute points for all flags submitted this round
		stolen_flags: Set[Tuple[int, int, int, int]] = set()  # service_id, team_id, round_issued, payload - first stolen this round
		stolen_flags_this_round: Set[Tuple[int, int, int, int]] = set()  # service_id, team_id, round_issued, payload - anything stolen this round
		for flag, num_previous_submissions, num_submissions, previous_submitter_ids in flags:
			try:
				service_flags_per_round = services_by_id[flag.service_id].flags_per_round
				attacker = new_round_points[(flag.submitted_by, flag.service_id)]
				victim = new_round_points[(flag.team_id, flag.service_id)]
				# Victim's rank when the flag was created (end of the round before)
				victim_rank = team_rank_in_round.get((flag.round_issued - 1, flag.team_id), len(teams))
				# Victim's SLA points when the flag was stored (0 if the flag couldn't be stored)
				if (flag.service_id, flag.round_issued) not in sla_delta_for:
					sla_delta_for[(flag.service_id, flag.round_issued)] = self.get_sla_delta_for(flag.service_id, flag.round_issued)
				victim_sla_when_issued = sla_delta_for.get((flag.service_id, flag.round_issued), {}).get(flag.team_id, 0)
				# Give each attacker points
				attacker.flag_captured_count += 1
				flagpoints = 1.0 + (1.0 / (num_previous_submissions + num_submissions)) ** 0.5 + (1.0 / victim_rank) ** 0.5
				attacker.off_points += flagpoints / service_flags_per_round
				# Deduce victim points - that happens only once for each stolen flag
				if (flag.service_id, flag.team_id, flag.round_issued, flag.payload) not in stolen_flags_this_round:
					stolen_flags_this_round.add((flag.service_id, flag.team_id, flag.round_issued, flag.payload))
					victim_prev_damage = (num_previous_submissions / num_active_teams) ** 0.3 * victim_sla_when_issued
					victim_new_damage = ((num_previous_submissions + num_submissions) / num_active_teams) ** 0.3 * victim_sla_when_issued
					victim.def_points -= (victim_new_damage - victim_prev_damage) / service_flags_per_round
					# Offensive points of previous attackers need to be reduced - also only once for each flag
					if num_previous_submissions > 0:
						assert len(previous_submitter_ids) == num_previous_submissions
						previous_flagpoints = 1.0 + (1.0 / num_previous_submissions) ** 0.5 + (1.0 / victim_rank) ** 0.5
						for ps in previous_submitter_ids:
							new_round_points[(ps, flag.service_id)].off_points += flagpoints - previous_flagpoints
				# if flag is not known to be stolen
				if num_previous_submissions == 0 and (flag.service_id, flag.team_id, flag.round_issued, flag.payload) not in stolen_flags:
					stolen_flags.add((flag.service_id, flag.team_id, flag.round_issued, flag.payload))
					victim.flag_stolen_count += 1
					# first blood check
					self.is_first_blood_flag(flag, services_by_id[flag.service_id])
			except KeyError:
				print(f'Flag submitted for invalid team/service: flag #{flag.id} ({flag.team_id}, {flag.service_id})')
				log('scoring', 'Flag submitted for invalid team/service', f'flag #{flag.id} ({flag.team_id}, {flag.service_id})',
					level=LogMessage.WARNING, commit=False)

		# 4. Add the points from previous round
		for (team_id, service_id), teampoints in new_round_points.items():
			lr = last_round_points[(team_id, service_id)]
			teampoints.off_points += lr.off_points
			teampoints.def_points += lr.def_points
			teampoints.sla_points = lr.sla_points + teampoints.sla_delta
			teampoints.flag_captured_count += lr.flag_captured_count
			teampoints.flag_stolen_count += lr.flag_stolen_count

		# 5. Finally - save the new results
		self.save_teampoints(roundnumber, new_round_points)
		# Commit everything
		db.session.commit()

	# ----- Ranking ---

	def get_ranking_for_round(self, roundnumber: int) -> List[TeamRanking]:
		"""
		Gives the order of teams for a given round, including their total points
		:param roundnumber:
		:return:
		"""
		if roundnumber <= 0:
			teams: List[Team] = Team.query.order_by(Team.id).all()
			return [TeamRanking(team_id=team.id, team=team, round=0, points=0, rank=1) for team in teams]
		ranking = TeamRanking.query.filter(TeamRanking.round == roundnumber).order_by(TeamRanking.rank, TeamRanking.team_id).all()
		if not ranking:
			self.calculate_ranking_per_round(roundnumber)
			ranking = TeamRanking.query.filter(TeamRanking.round == roundnumber).order_by(TeamRanking.rank, TeamRanking.team_id).all()
		return ranking

	def calculate_ranking_per_round(self, roundnumber: int) -> None:
		"""
		Compute the ranking, based on the results.
		:param roundnumber:
		:return:
		"""
		TeamRanking.query.filter(TeamRanking.round == roundnumber).delete()
		db.session.commit()
		teams: List[int] = [id for id, in db.session.query(Team.id).all()]
		results = self.get_results_for_round_lite(roundnumber, teams)
		ranking: Dict[int, TeamRanking] = {id: TeamRanking(round=roundnumber, team_id=id, points=0) for id in teams}
		# Computation - final points = off_points + def_points + sla_points
		for result in results.values():
			ranking[result.team_id].points += result.off_points + result.def_points + result.sla_points
		# do the ranking and save
		ranks = self.order_by_points(list(ranking.values()))
		db.session.bulk_save_objects(ranks)
		db.session.commit()

	def order_by_points(self, ranking: List[TeamRanking]) -> List[TeamRanking]:
		"""
		Order the given TeamRanking instances by points, and set the "ranking" parameter
		:param ranking:
		:return:
		"""
		ranking.sort(key=lambda tr: tr.points, reverse=True)
		i = 1
		previous_rank = None
		for rank in ranking:
			if previous_rank and previous_rank.points == rank.points:
				rank.rank = previous_rank.rank
			else:
				rank.rank = i
			previous_rank = rank
			if rank.points > 0:
				i += 1
		return ranking
