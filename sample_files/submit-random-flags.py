import os
import random
import sys

from controlserver.models import Team, Service, SubmittedFlag, db

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.EXTERNAL_TIMER = True
from controlserver.scoring.scoreboard import Scoreboard
from controlserver.scoring.scoring import ScoringCalculation
from sample_files.debug_sql_timing import timing, print_query_stats


def submit_random_flags(endround: int, chance=0.33):
	import controlserver.app
	teams = Team.query.filter(Team.id != 1).all()
	services = Service.query.all()
	team_exploit_ready = {}
	team_patch_ready = {}
	for s in services:
		service_difficulty = random.randint(1, 5)
		for t in teams:
			team_exploit_ready[(t.id, s.id)] = random.randint(1, round(endround / chance)) * service_difficulty
			team_patch_ready[(t.id, s.id)] = random.randint(1, round(endround)) * service_difficulty // 3
			if t.name == 'saarsec':
				team_exploit_ready[(t.id, s.id)] = int(team_exploit_ready[(t.id, s.id)] * 0.8)
				team_patch_ready[(t.id, s.id)] = int(team_patch_ready[(t.id, s.id)] * 0.8)
	for s in services:
		submitted_flags = []
		sid = s.id
		for attacker in teams:
			# print(f'Service {sid}, team {attacker.name}: exploit {team_exploit_ready[(attacker.id, sid)]} / patch {team_patch_ready[(attacker.id, sid)]}')
			if team_exploit_ready[(attacker.id, sid)] > endround: continue
			for victim in teams:
				for r in range(team_exploit_ready[(attacker.id, sid)], min(endround, team_patch_ready[(victim.id, sid)])):
					# hack!
					p = 0
					if s.num_payloads > 1: p = random.randint(0, s.num_payloads - 1)
					flag = SubmittedFlag(submitted_by=attacker.id, service_id=sid, team_id=victim.id, round_issued=r, payload=p,
										 round_submitted=r + random.randint(0, 4))
					submitted_flags.append(flag)
			# print(len(submitted_flags))
		print(f'Service {sid}, submitting {len(submitted_flags)} flags...')
		db.session.add_all(submitted_flags)
		db.session.commit()


if __name__ == '__main__':
	config.set_redis_clientname('script-' + os.path.basename(__file__))
	from controlserver.timer import Timer, CTFState

	roundnumber = Timer.currentRound
	if Timer.state == CTFState.RUNNING:
		roundnumber -= 1
	timing()
	submit_random_flags(roundnumber)
	timing('Submitter')
	print('Done.')
