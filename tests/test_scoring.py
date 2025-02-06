import json
import math
import os
import time
import unittest
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import List, Tuple, Dict

from controlserver.models import TeamPoints, TeamRanking, SubmittedFlag, db_session, CheckerResult, db_session_2
from controlserver.scoring.scoreboard import Scoreboard
from controlserver.scoring.scoring import ScoringCalculation
from controlserver.timer import init_mock_timer, CTFState
from saarctf_commons import config
from tests.utils.base_cases import DatabaseTestCase
from tests.utils.scriptrunner import ScriptRunner


class ScoringTestCase(DatabaseTestCase):
    def setUp(self):
        super().setUp()
        self.config = config.config.SCORING

    def save_checker_results(self, results: List[Tuple[int, List[str]]]) -> None:
        session = db_session()
        for tick, states in results:
            for team_id in range(1, 5):
                for service_id in range(1, 4):
                    status = states[(team_id - 1) * 3 + service_id - 1]
                    self.assertIn(status, CheckerResult.states)
                    session.add(
                        CheckerResult(team_id=team_id, service_id=service_id, tick=tick, status=status, celery_id=''))
        session.commit()

    def save_stolen_flags(self, service_id: int, flags: List[Tuple[int, int, int, int, int]]) -> None:
        session = db_session()
        for stolen_by, stolen_in, team_id, issued, payload in flags:
            session.add(
                SubmittedFlag(service_id=service_id, submitted_by=stolen_by, tick_submitted=stolen_in, team_id=team_id,
                              tick_issued=issued, payload=payload))
            session.commit()
            time.sleep(0.002)

    def test_empty_scratch(self) -> None:
        self.assertEqual(0, TeamPoints.query.count())
        self.demo_team_services()

    def test_scoring(self) -> None:
        self.demo_team_services()
        self._create_results()

        # run scoring algorithm
        scoring = ScoringCalculation(self.config)
        for rn in range(1, 21):
            scoring.calculate_scoring_for_tick(rn)
            scoring.calculate_ranking_per_tick(rn)

        # Check results
        results = self.get_results()
        rankings = self.get_rankings()

        # 1. Check SLA
        sla_ranking_sum: dict[tuple[int, int], float] = defaultdict(lambda: 0.0)
        for team_id in (1, 2, 3, 4):
            for service_id in (1, 2, 3):
                sla_sum = 0.0
                for rn in range(1, 21):
                    sla = self.sla_formula(4 if rn != 6 else 3)
                    # offline: service 3 tickticktickticktickticktick 3-5 | tick6 team4
                    if service_id == 3 and 3 <= rn <= 5: sla = 0.0
                    if team_id == 4 and rn == 6: sla = 0.0
                    sla_sum += sla
                    self.assertAlmostEqual(results[service_id, team_id, rn].sla_delta, sla)  # type: ignore[misc]
                    self.assertAlmostEqual(results[service_id, team_id, rn].sla_points, sla_sum)  # type: ignore[misc]
                    sla_ranking_sum[(team_id, rn)] += sla_sum
        print('Checked SLA calculation.')

        # 2. Check OFF
        off_ranking_sum: dict[tuple[int, int], float] = defaultdict(lambda: 0.0)
        for team_id in (1, 2, 3, 4):
            for service_id in (1, 2, 3):
                off_sum = 0.0
                captured = 0
                for rn in range(1, 21):
                    off = 0.0
                    if team_id == 2 and service_id == 1:
                        if rn == 8:
                            off = self.flag_formula(1, 1) + 2 * self.flag_formula(1, 4)
                            captured += 3
                        elif rn == 9:
                            off = self.flag_formula(1, 3) + self.flag_formula(1, 4)
                            captured += 2
                        elif rn == 11:
                            off = 2 * self.flag_formula(1, 3) + 2 * self.flag_formula(2, 4)
                            captured += 4
                        elif rn == 15:
                            off = self.flag_formula(1, 4)  # at this point in time, #3 did not steal this flag
                            captured += 1
                        elif rn == 17:
                            off = self.flag_formula(2, 4) - self.flag_formula(1, 4)  # now #3 did also steal this flag
                    elif team_id == 2 and service_id == 2 and rn == 20:
                        off = self.flag_formula(1, 3)
                        captured += 1
                    elif team_id == 3 and service_id == 1:
                        if rn == 11:
                            off = 2 * self.flag_formula(2, 4)
                            captured += 2
                        elif rn == 17:
                            off = self.flag_formula(2,
                                                    4)  # at this point in time, #2 submitted the flag two ticks before
                            captured += 1
                    elif team_id == 3 and service_id == 3 and rn == 15:
                        off = self.flag_formula(1, 1, 2) + self.flag_formula(1, 4, 2) + self.flag_formula(1, 4, 2)
                        captured += 3
                    off_sum += off
                    self.assertEqual(results[service_id, team_id, rn].flag_captured_count, captured)
                    self.assertAlmostEqual(results[service_id, team_id, rn].off_points, off_sum)  # type: ignore[misc]
                    off_ranking_sum[(team_id, rn)] += off_sum
        print('Checked OFF calculation')

        # 3. Check DEF
        def_ranking_sum: dict[tuple[int, int], float] = defaultdict(lambda: 0.0)
        for team_id in (1, 2, 3, 4):
            for service_id in (1, 2, 3):
                for rn in range(1, 21):
                    stolen = 0
                    defp = 0.0
                    if team_id == 2 and service_id == 3 and rn >= 15:
                        defp += self.def_formula(1, service_flag_count=2)
                        stolen += 1
                    elif team_id == 3 and service_id == 1:
                        if rn >= 8:
                            defp += self.def_formula(1)
                            stolen += 1
                        if rn >= 9:
                            defp += self.def_formula(1)
                            stolen += 1
                        if rn >= 11:
                            defp += 2 * self.def_formula(1)
                            stolen += 2
                    elif team_id == 3 and service_id == 2 and rn >= 20:
                        defp += self.def_formula(1)
                        stolen += 1
                    elif team_id == 4 and service_id == 1:
                        if rn >= 8:
                            defp += 2 * self.def_formula(1)
                            stolen += 2
                        if rn >= 9:
                            defp += self.def_formula(1)
                            stolen += 1
                        if rn >= 11:
                            defp += 2 * self.def_formula(2)
                            stolen += 2
                        if rn >= 17:  # first stolen in 15, second steal in 17
                            defp += self.def_formula(2)
                            stolen += 1
                        elif rn >= 15:
                            defp += self.def_formula(1)
                            stolen += 1
                    elif team_id == 4 and service_id == 3 and rn >= 15:
                        defp += 2 * self.def_formula(1, service_flag_count=2)
                        stolen += 2
                    self.assertEqual(results[service_id, team_id, rn].flag_stolen_count, stolen)
                    self.assertAlmostEqual(results[service_id, team_id, rn].def_points, defp)  # type: ignore[misc]
                    def_ranking_sum[(team_id, rn)] += defp
        print('Checked DEF calculation')

        # 4. Check first blood
        first_blood_flags = [(1, 2, 8, 3, 8, 0), (2, 2, 20, 3, 10, 0), (3, 3, 15, 2, 15, 0), (3, 3, 15, 4, 15, 1)]
        for flag in self.get_flags():
            key = (flag.service_id, flag.submitted_by, flag.tick_submitted,
                   flag.team_id, flag.tick_issued, flag.payload)
            should_be = key in first_blood_flags
            self.assertEqual(should_be, flag.is_firstblood, f'wrong: {key}')

        # 5. Check ranking
        for team_id in (1, 2, 3, 4):
            for rn in range(1, 21):
                points = sla_ranking_sum[team_id, rn] + off_ranking_sum[team_id, rn] + def_ranking_sum[team_id, rn]
                self.assertAlmostEqual(rankings[team_id, rn].points, points)  # type: ignore[misc]
                pass
        pass

    def test_scoring_factors(self) -> None:
        self.config = config.ScoringConfig.from_dict(config.config.SCORING.to_dict())
        self.config.off_factor = 2.0
        self.config.def_factor = 3.5
        self.config.sla_factor = 0.8
        self.test_scoring()

    def _create_results(self):
        # mock checker results
        checker_results = [
            (1, ['SUCCESS', 'SUCCESS', 'SUCCESS'] * 4),
            (2, ['SUCCESS', 'SUCCESS', 'SUCCESS'] * 4),
            (3, ['SUCCESS', 'SUCCESS', 'OFFLINE'] * 4),  # Service 3 is broken for all
            (4, ['SUCCESS', 'SUCCESS', 'FLAGMISSING'] * 4),
            (5, ['SUCCESS', 'SUCCESS', 'MUMBLE'] * 4),
            (6, ['SUCCESS', 'SUCCESS', 'SUCCESS'] * 3 + ['OFFLINE', 'OFFLINE', 'OFFLINE']),
            # team 4 is completely offline
        ]
        checker_results += [(i, ['SUCCESS', 'SUCCESS', 'SUCCESS'] * 4) for i in
                            range(7, 21)]  # rest is ok - up to tick 20
        self.save_checker_results(checker_results)
        # stolen flags: [stolen_by, stolen_in, team_id, issued, payload]
        self.save_stolen_flags(1, [
            (2, 8, 3, 8, 0), (2, 8, 4, 7, 0), (2, 8, 4, 8, 0),
            (2, 9, 3, 9, 0), (2, 9, 4, 9, 0),
            (2, 11, 3, 10, 0), (2, 11, 4, 10, 0), (2, 11, 3, 11, 0), (2, 11, 4, 11, 0),
            (3, 11, 4, 10, 0), (3, 11, 4, 11, 0),  # 2 and 3 steal the same flags
            (2, 15, 4, 15, 0), (3, 17, 4, 15, 0),  # two team steal the same flag in a different tick
        ])
        self.save_stolen_flags(2, [(2, 20, 3, 10, 0)])  # submit flag that is just about to expire
        self.save_stolen_flags(3, [(3, 15, 2, 15, 0), (3, 15, 4, 15, 0),
                                   (3, 15, 4, 15, 1)])  # submit 1 flag from #2 and 2 flags from #4

    def test_scoring_double_submit(self) -> None:
        """
        This scenario caused a bug once: first 1 team submits, next tick 2 more teams submit the same flag.
        :return:
        """
        self.demo_team_services()
        # mock checker results
        checker_results = [(i, ['SUCCESS', 'SUCCESS', 'SUCCESS'] * 4) for i in range(1, 4)]
        self.save_checker_results(checker_results)
        # stolen flags: [stolen_by, stolen_in, team_id, issued, payload]
        self.save_stolen_flags(1, [
            (2, 2, 1, 1, 0),  # first team 2 steals the flag
            (3, 3, 1, 1, 0), (4, 3, 1, 1, 0),  # then team 3+4 steal the flag
        ])

        # run scoring algorithm
        scoring = ScoringCalculation(self.config)
        for rn in range(1, 4):
            scoring.calculate_scoring_for_tick(rn)
            scoring.calculate_ranking_per_tick(rn)

        # Check results
        results = self.get_results()
        rankings = self.get_rankings()

        # 1. Check OFF
        off_ranking_sum: dict[tuple[int, int], float] = defaultdict(lambda: 0.0)
        for team_id in (1, 2, 3, 4):
            for service_id in (1, 2, 3):
                captured = 0
                for rn in range(1, 4):
                    off = 0.0
                    if team_id == 2 and service_id == 1:
                        if rn == 2:
                            off = self.flag_formula(1, 4)  # rank in tick 0 == len(teams)
                            captured += 1
                        elif rn >= 3:
                            off = self.flag_formula(3, 4)
                    elif team_id in (3, 4) and service_id == 1:
                        if rn == 3:
                            off = self.flag_formula(3, 4)
                            captured += 1
                    self.assertEqual(results[service_id, team_id, rn].flag_captured_count, captured)
                    self.assertAlmostEqual(results[service_id, team_id, rn].off_points, off)  # type: ignore[misc]
                    off_ranking_sum[(team_id, rn)] += off
        print('Checked OFF calculation')

        # 2. Check DEF
        def_ranking_sum: dict[tuple[int, int], float] = defaultdict(lambda: 0.0)
        for team_id in (1, 2, 3, 4):
            for service_id in (1, 2, 3):
                stolen = 0
                for rn in range(1, 4):
                    defp = 0.0
                    if team_id == 1 and service_id == 1:
                        if rn == 2:
                            defp = self.def_formula(1)
                            stolen += 1
                        elif rn >= 3:
                            defp = self.def_formula(3)
                    self.assertEqual(results[service_id, team_id, rn].flag_stolen_count, stolen)
                    self.assertAlmostEqual(results[service_id, team_id, rn].def_points, defp)  # type: ignore[misc]
                    def_ranking_sum[(team_id, rn)] += defp
        print('Checked DEF calculation')

        # 3. Check first blood
        first_blood_flags = [(1, 2, 2, 1, 1, 0)]
        for flag in self.get_flags():
            should_be = (flag.service_id, flag.submitted_by, flag.tick_submitted, flag.team_id, flag.tick_issued,
                         flag.payload) in first_blood_flags
            self.assertEqual(should_be, flag.is_firstblood)

    def flag_formula(self, num_stealers: int, victim_rank: int, service_flag_count: int = 1) -> float:
        raw = (1.0 + (1.0 / num_stealers) ** 0.5 + (1 / victim_rank) ** 0.5) / service_flag_count
        return raw * self.config.off_factor

    def sla_formula(self, teams_online: int) -> float:
        return math.sqrt(teams_online) * self.config.sla_factor

    def def_formula(self, times_stolen: int, teams_online: int = 4, service_flag_count: int = 1):
        raw = -(times_stolen * 1.0 / teams_online) ** 0.3 * self.sla_formula(teams_online) / service_flag_count
        return raw * self.config.def_factor

    def get_results(self) -> Dict[Tuple[int, int, int], TeamPoints]:
        # service, team, tick
        result = {}
        for tp in TeamPoints.query.all():
            result[(tp.service_id, tp.team_id, tp.tick)] = tp
        return result

    def get_rankings(self) -> Dict[Tuple[int, int], TeamRanking]:
        result = {}
        for tr in TeamRanking.query.all():
            result[(tr.team_id, tr.tick)] = tr
        return result

    def get_flags(self) -> list[SubmittedFlag]:
        with db_session_2() as session:
            return session.query(SubmittedFlag).all()

    def test_scoreboard(self) -> None:
        timer = init_mock_timer()
        self.demo_team_services()
        self._create_results()
        with TemporaryDirectory() as directory:
            base = Path(directory)
            config.current_config.SCOREBOARD_PATH = base
            scoring = ScoringCalculation(self.config)
            scoreboard = Scoreboard(scoring, publish=False)
            scoreboard.update_tick_info()
            scoreboard.create_scoreboard(-1, False, False)
            scoreboard.create_scoreboard(0, True, False)
            files = os.listdir(base / 'api')
            for f in ['scoreboard_current.json', 'scoreboard_round_-1.json', 'scoreboard_round_0.json',
                      'scoreboard_team_1.json', 'scoreboard_team_2.json', 'scoreboard_team_3.json',
                      'scoreboard_team_4.json', 'scoreboard_teams.json']:
                self.assertIn(f, files)

            for rn in range(1, 21):
                timer.current_tick = rn
                scoring.calculate_scoring_for_tick(rn)
                scoring.calculate_ranking_per_tick(rn)
                scoreboard.create_scoreboard(rn, True, True)
                self.assertTrue((base / 'api' / f'scoreboard_round_{rn}.json').exists())

    def test_ctftime_export(self) -> None:
        timer = init_mock_timer()
        timer.state = CTFState.STOPPED
        timer.desired_state = CTFState.STOPPED
        timer.update_redis()
        self.demo_team_services()
        self._create_results()
        scoring = ScoringCalculation(self.config)
        for rn in range(1, 21):
            timer.current_tick = rn
            scoring.calculate_scoring_for_tick(rn)
            scoring.calculate_ranking_per_tick(rn)

        with TemporaryDirectory() as directory:
            result = ScriptRunner.run_script('scripts/export_ctftime_scoreboard.py',
                                             [os.path.join(directory, 'ctftime.json')])
            ScriptRunner.assert_no_exception(result)
            with open(os.path.join(directory, 'ctftime.json'), 'r') as f:
                content = json.loads(f.read())
            self.assertEqual(content, {'standings': [
                {'pos': 1, 'team': 'Team2', 'score': 139.9671},
                {'pos': 2, 'team': 'Team3', 'score': 117.2199},
                {'pos': 3, 'team': 'Team4', 'score': 97.8485}
            ]})


if __name__ == '__main__':
    unittest.main()
