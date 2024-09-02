import random
import time
import unittest
import os
from typing import List
from unittest import skip

from sqlalchemy import func

from controlserver.models import TeamPoints, Team, Service, SubmittedFlag, TeamRanking, CheckerResultLite, db_session
from controlserver.scoring.scoring import ScoringCalculation
from saarctf_commons.config import config
from saarctf_commons.debug_sql_timing import timing, print_query_stats, reset_timing
from tests.utils.base_cases import DatabaseTestCase

"""
=== BENCHMARK RESULTS (something large / i7 6700k) ===
--- 04.12.2019 ---
average: 0.693 sec    min: 0.143 sec    max: 0.987 sec
avg first 15: 0.268 sec         avg last 15: 0.941 sec
104194.9 ms  (+ 69465.7 ms)  Created large ranking
"""

"""
=== BENCHMARK RESULTS (Faust / i7 6700k) ===
--- 04.12.2019 ---
average: 0.086 sec    min: 0.043 sec    max: 0.139 sec
avg first 15: 0.058 sec         avg last 15: 0.106 sec
19514.1 ms  (+ 14103.5 ms)  Created FaustCTF 2019 ranking
"""

"""
=== BENCHMARK RESULTS (something large / i5 4690) ===
--- 04.12.2019 ---
average: 0.766 sec    min: 0.160 sec    max: 1.102 sec
avg first 15: 0.336 sec         avg last 15: 1.022 sec
116339.2 ms  (+ 76767.9 ms)  Created large ranking
"""

"""
=== BENCHMARK RESULTS (Faust / i5 4690) ===
--- 04.12.2019 ---
average: 0.100 sec    min: 0.052 sec    max: 0.143 sec
avg first 15: 0.059 sec         avg last 15: 0.117 sec
21983.6 ms  (+ 16169.3 ms)  Created FaustCTF 2019 ranking
"""


@skip('benchmark')
class BenchTestCase(DatabaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        config.SCORING.FLAG_ROUNDS_VALID = 10
        config.CONFIG['scoring']['nop_team_id'] = -1
        config.SCORING.NOP_TEAM_ID = -1

    def _print_stats(self):
        print('# Teams:    {}'.format(Team.query.count()))
        print('# Services: {}'.format(Service.query.count()))
        print('# Flags:    {}'.format(SubmittedFlag.query.count()))
        flags_per_service = SubmittedFlag.query.with_entities(SubmittedFlag.service_id, func.count()).group_by(SubmittedFlag.service_id) \
            .order_by(SubmittedFlag.service_id).all()
        print('# Flags per service: {}'.format([cnt for id, cnt in flags_per_service]))
        highscores = SubmittedFlag.query.with_entities(SubmittedFlag.submitted_by, func.count()).group_by(SubmittedFlag.submitted_by).all()
        highscores = [cnt for id, cnt in highscores]
        highscores.sort(reverse=True)
        print('Highscores: {}'.format(highscores[:3]))

    def _init_teams(self, team_count: int, **kwargs):
        for i in range(team_count):
            db_session().add(Team(name=f'Team {i + 1}', vpn_connected=True, **kwargs))

    def _init_services(self, service_count: int, **kwargs):
        for i in range(service_count):
            db_session().add(Service(name=f'Service {i + 1}', checker_script='', **kwargs))

    def _submit_checker_results(self, endround: int, chance_offline=0.02, chance_flagmissing=0.02, chance_mumble=0.05, seed=1337):
        rnd = random.Random(seed)
        teams = Team.query.all()
        services = Service.query.all()
        results = []
        for r in range(1, endround + 1):
            for t in teams:
                for s in services:
                    x = rnd.random()
                    if x < chance_offline:
                        state = 'OFFLINE'
                    elif x < chance_offline + chance_flagmissing:
                        state = 'FLAGMISSING'
                    elif x < chance_offline + chance_flagmissing + chance_mumble:
                        state = 'MUMBLE'
                    else:
                        state = 'SUCCESS'
                    results.append(CheckerResultLite(t.id, s.id, r, state))
        CheckerResultLite.efficient_insert(results)

    def _submit_random_flags(self, endround: int, chance=0.33, seed=1337):
        rnd = random.Random(seed)
        teams = Team.query.all()
        services = Service.query.all()
        team_exploit_ready = {}
        team_patch_ready = {}
        team_strength = {team.id: rnd.randint(400, 1600) / 1000.0 for team in teams}
        for s in services:
            service_difficulty = rnd.randint(1, 5)
            for t in teams:
                team_exploit_ready[(t.id, s.id)] = int(rnd.randint(1, round(endround / chance)) * service_difficulty * team_strength[t.id])
                team_patch_ready[(t.id, s.id)] = int(rnd.randint(1, round(endround)) * service_difficulty * team_strength[t.id])
        for s in services:
            submitted_flags = []
            sid = s.id
            for attacker in teams:
                if team_exploit_ready[(attacker.id, sid)] > endround: continue
                for victim in teams:
                    for r in range(team_exploit_ready[(attacker.id, sid)], min(endround, team_patch_ready[(victim.id, sid)])):
                        # hack!
                        p = 0
                        if s.num_payloads > 1: p = rnd.randint(0, s.num_payloads - 1)
                        flag = SubmittedFlag(submitted_by=attacker.id, service_id=sid, team_id=victim.id, round_issued=r, payload=p,
                                             round_submitted=r + rnd.randint(0, 4))
                        submitted_flags.append(flag)
            print(f'Service {sid}, submitting {len(submitted_flags)} flags...')
            SubmittedFlag.efficient_insert(submitted_flags)
            db_session().commit()

    def _recreate_ranking(self, endround: int) -> List[float]:
        scoring = ScoringCalculation(config.SCORING)
        times = []
        for rn in range(1, endround + 1):
            # Remove old points/ranking from DB
            TeamPoints.query.filter(TeamPoints.round == rn).delete()
            TeamRanking.query.filter(TeamRanking.round == rn).delete()
            db_session().commit()

            ts = time.time()
            scoring.calculate_scoring_for_tick(rn)
            scoring.calculate_ranking_per_tick(rn)
            ts = time.time() - ts
            if rn % 10 == 0:
                print(f'- Round {rn} recalculated in {ts:.3f} seconds')
            times.append(ts)
        return times

    def test_something_like_faust2019(self):
        # Faust 2019 had: 6 working services, 53 teams, 87477 submitted flags, highscores 11678.00, 7620.00, 7758.00
        reset_timing()
        timing()
        self._init_teams(53)
        self._init_services(6)
        self._submit_checker_results(160)
        self._submit_random_flags(160, chance=0.33, seed=0x1337)
        timing('Prepared DB')
        self._print_stats()
        time.sleep(0.5)

        timing()
        times = self._recreate_ranking(160)
        print(f'average: {sum(times) / len(times):.3f} sec    min: {min(times):.3f} sec    max: {max(times):.3f} sec')
        print(f'avg first 15: {sum(times[:15]) / len(times[:15]):.3f} sec         avg last 15: {sum(times[-15:]) / len(times[-15:]):.3f} sec')
        timing('Created FaustCTF 2019 ranking')
        print_query_stats()
        time.sleep(0.5)

    def test_something_large(self):
        reset_timing()
        timing()
        self._init_teams(150)
        self._init_services(10)
        timing('Teams + Services')
        self._submit_checker_results(100)
        timing('Checker results')
        self._submit_random_flags(100, chance=0.25, seed=0xabcd)
        timing('Prepared DB')
        self._print_stats()
        time.sleep(0.5)

        timing()
        times = self._recreate_ranking(100)
        print(f'average: {sum(times) / len(times):.3f} sec    min: {min(times):.3f} sec    max: {max(times):.3f} sec')
        print(f'avg first 15: {sum(times[:15]) / len(times[:15]):.3f} sec         avg last 15: {sum(times[-15:]) / len(times[-15:]):.3f} sec')
        timing('Created large ranking')
        print_query_stats()
        time.sleep(0.5)


if __name__ == '__main__':
    unittest.main()
