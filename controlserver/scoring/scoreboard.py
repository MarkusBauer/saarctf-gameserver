"""
Write the scoreboard to disk.
"""
import os
import shutil
from collections import defaultdict
from pathlib import Path
from typing import List, Tuple, Dict, Optional, Any, Set

import htmlmin
from jinja2 import Environment, select_autoescape, FileSystemLoader

from controlserver.models import TeamRanking, Team, TeamLogo, Service, CheckerResultLite, TeamPoints, TeamPointsLite, \
    SubmittedFlag, init_database, db_session_2
from controlserver.scoring.scoring import ScoringCalculation
from controlserver.timer import init_slave_timer
from saarctf_commons.config import config, load_default_config
from saarctf_commons.redis import get_redis_connection, NamedRedisConnection
from saarctf_commons.db_utils import retry_on_sql_error

try:
    import ujson as json
except ImportError:
    import json  # type: ignore


class RoundInformation:
    def __init__(self, roundnumber: int, ranking: List[TeamRanking], team_points: Dict[Tuple[int, int], TeamPointsLite],
                 checker_results: Dict[Tuple[int, int], CheckerResultLite]) -> None:
        self.roundnumber: int = roundnumber
        self.ranking: List[TeamRanking] = ranking
        self.ranking_by_team_id: Dict[int, TeamRanking] = {r.team_id: r for r in ranking}
        self.team_points: Dict[Tuple[int, int], TeamPointsLite] = team_points
        self.checker_results: Dict[Tuple[int, int], CheckerResultLite] = checker_results


class Scoreboard:
    jinja2_env = Environment(
        loader=FileSystemLoader(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates')),
        autoescape=select_autoescape(['html', 'xml'])
    )

    def __init__(self, calculation: ScoringCalculation, publish=False) -> None:
        base = Path(__file__).absolute().parent.parent.parent
        self.angular_build_path: Path = base / 'scoreboard' / 'dist' / 'scoreboard'
        self.calculation: ScoringCalculation = calculation
        self.preparedStaticFiles = False
        self.teams: List[Team] = []
        self.services: List[Service] = []
        self.__should_publish = publish
        self.conn = get_redis_connection()

    def __publish(self, scoreboard_tick: int):
        self.conn.set('timing:scoreboard_tick', str(scoreboard_tick))
        self.conn.publish('timing:scoreboard_tick', str(scoreboard_tick))

    def update_round_info(self, scoreboard_tick: Optional[int] = None) -> int:
        self.check_scoreboard_prepared()
        scoreboard_tick = self.__create_round_info_json(scoreboard_tick)
        if self.__should_publish:
            self.__publish(scoreboard_tick)
        return scoreboard_tick

    def exists(self, roundnumber: int, has_started: bool):
        """
        Return True if the scoreboard data for this round has already been written (by #create_scoreboard)
        :param roundnumber:
        :param has_started:
        :return:
        """
        if roundnumber == 0 and not has_started:
            roundnumber = -1
        return (config.SCOREBOARD_PATH / 'api' / f'scoreboard_round_{roundnumber}.json').exists()

    def create_scoreboard(self, roundnumber: int, has_started: bool = True, is_live: bool = False) -> None:
        """
        Write the scoreboard as it is AFTER a given round
        :param roundnumber:
        :param has_started: True if the game already started. If False, service names will be hidden (by informal tick -1)
        :param is_live: True if that's the most recent round
        :return:
        """
        self.teams = Team.query.order_by(Team.id).all()
        self.services = Service.query.order_by(Service.id).all()
        if roundnumber == 0 and not has_started:
            roundnumber = -1
        if self.__should_publish:
            self.__publish(roundnumber)
        info: RoundInformation = self.__fetch_data(roundnumber)
        previous_info: RoundInformation = self.__fetch_data(roundnumber - 1)
        last_checker_results: List[Dict[Tuple[int, int], CheckerResultLite]] = [
            previous_info.checker_results,
            self.calculation.get_checker_results_lite(roundnumber - 2),
            self.calculation.get_checker_results_lite(roundnumber - 3)
        ]
        # copy static files
        self.check_scoreboard_prepared()
        # render ALL the templates here
        # main scoreboard
        self.__create_logos()
        self.__create_team_json()
        # self.__create_main_html(info)
        self.__create_json_for_round(info, previous_info, last_checker_results)
        self.__create_json_for_teams(info)
        if is_live:
            self.__create_round_info_json(info.roundnumber)

    '''
    def __create_main_html(self, info: RoundInformation):
        self._render_template(
            'scoreboard/index.html', 'index.html', minimize=True,
            services=self.services, currentRound=info.roundnumber,
            rankings=info.ranking, points=info.team_points, checker_results=info.checker_results
        )

    def __create_offline_html(self, info: RoundInformation):
        anon_services = Service.query.order_by(Service.id).all()
        for service in anon_services:
            service.name = '?'
        self._render_template(
            'scoreboard/index.html', 'index.html', minimize=True,
            services=anon_services, currentRound=info.roundnumber,
            rankings=info.ranking, points=info.team_points, checker_results=info.checker_results
        )
    '''

    def __create_round_info_json(self, scoreboard_tick: Optional[int]) -> int:
        """
        Create a JSON file with the current round, the last scoreboard result tick number and game state.
        :param scoreboard_tick:
        :return:
        """
        from controlserver.timer import Timer
        if scoreboard_tick is None:
            old_data = self._read_json('api/scoreboard_current.json', {'scoreboard_tick': -1})
            scoreboard_tick = old_data['scoreboard_tick']
        data = {
            'current_tick': Timer.currentRound,
            'state': Timer.state,
            'current_tick_until': Timer.roundEnd,
            'scoreboard_tick': scoreboard_tick,
            'banned_teams': [int(b.decode()) for b in self.conn.smembers('network:banned')]
        }
        self._write_json('api/scoreboard_current.json', data)
        return scoreboard_tick

    def __create_json_for_round(self, info: RoundInformation, previous_info: RoundInformation,
                                last_checker_results: List[Dict[Tuple[int, int], CheckerResultLite]]) -> None:
        """
        Create a JSON file with the precise results (checker, points, rank) of a round.
        :param info:
        :param previous_info:
        :param last_checker_results:
        :return:
        """
        data: Dict[str, Any] = {
            'tick': info.roundnumber,
            'scoreboard': []
        }
        attacker_count: Dict[int, int] = defaultdict(lambda: 0)  # service_id => team_count
        victim_count: Dict[int, int] = defaultdict(lambda: 0)
        for ranking in info.ranking:
            off_points = 0.0
            def_points = 0.0
            sla_points = 0.0
            prev_off_points = 0.0
            prev_def_points = 0.0
            prev_sla_points = 0.0
            services = []
            for service in self.services:
                pts = info.team_points[(ranking.team_id, service.id)]
                prev_pts = previous_info.team_points[(ranking.team_id, service.id)]
                check = info.checker_results[(ranking.team_id, service.id)]
                off_points += pts.off_points
                def_points += pts.def_points
                sla_points += pts.sla_points
                prev_off_points += prev_pts.off_points
                prev_def_points += prev_pts.def_points
                prev_sla_points += prev_pts.sla_points
                services.append({
                    'o': pts.off_points, 'd': pts.def_points, 's': pts.sla_points,
                    'do': pts.off_points - prev_pts.off_points,
                    'dd': pts.def_points - prev_pts.def_points,
                    'ds': pts.sla_points - prev_pts.sla_points,
                    'st': pts.flag_stolen_count, 'cap': pts.flag_captured_count,
                    'dst': pts.flag_stolen_count - prev_pts.flag_stolen_count,
                    'dcap': pts.flag_captured_count - prev_pts.flag_captured_count,
                    'c': check.status, 'm': check.message,
                    'dc': [results[(ranking.team_id, service.id)].status for results in last_checker_results]
                })
                if pts.off_points > prev_pts.off_points:
                    attacker_count[service.id] += 1
                if pts.def_points < prev_pts.def_points:
                    victim_count[service.id] += 1
            data['scoreboard'].append({
                'team_id': ranking.team_id,
                'rank': ranking.rank,
                'points': ranking.points,
                'services': services,
                'o': off_points,
                'd': def_points,
                's': sla_points,
                'do': off_points - prev_off_points,
                'dd': def_points - prev_def_points,
                'ds': sla_points - prev_sla_points,
            })
        first_blood_info = self.__get_first_blood_info(info.roundnumber)
        data['services'] = [{
            'name': service.name if info.roundnumber >= 0 else '???',
            'attackers': attacker_count[service.id],
            'victims': victim_count[service.id],
            'first_blood': first_blood_info[service.id][0],
            'flag_stores': service.num_payloads if service.num_payloads > 1 else 1,
            'flag_stores_exploited': len(first_blood_info[service.id][1]) if service.num_payloads > 1 else (
                1 if first_blood_info[service.id][1] else 0)
        } for service in self.services]
        self._write_json(f'api/scoreboard_round_{info.roundnumber}.json', data)

    @retry_on_sql_error(attempts=2)
    def __get_team_points(self, team_id: int, max_round: int) -> list[tuple[int, int, float, float, float]]:
        with db_session_2() as session:
            return session.query(TeamPoints.round, TeamPoints.service_id, TeamPoints.off_points,
                                 TeamPoints.def_points,
                                 TeamPoints.sla_points) \
                .filter(TeamPoints.team_id == team_id, 0 <= TeamPoints.round,
                        TeamPoints.round <= max_round).all()

    def __create_json_for_teams(self, info: RoundInformation) -> None:
        """
        Create files "scoreboard_team_<teamid>.json" containing the per-service points of each team.
        :param info:
        :return:
        """
        servicenames: List[str] = [service.name if info.roundnumber >= 0 else '???' for service in self.services]

        for team in self.teams:
            filename = f'api/scoreboard_team_{team.id}.json'
            data = self._read_json(filename,
                                   {'services': servicenames, 'points': [[] for _ in range(len(self.services))]})
            if len(data['points']) == 0:
                data['services'] = servicenames
            # update existing files if possible
            if data['services'] == servicenames and len(data['points']) == len(self.services) and all(
                    len(row) == max(0, info.roundnumber) for row in data['points']):
                for i, service in enumerate(self.services):
                    pts = info.team_points[(team.id, service.id)]
                    data['points'][i].append(pts.off_points + pts.def_points + pts.sla_points)
            else:
                rows: list[list[float]] = [[0.0] * (info.roundnumber + 1) for _ in self.services]
                points = self.__get_team_points(team.id, info.roundnumber)
                service_id_to_index = {service.id: i for i, service in enumerate(self.services)}
                for tick, service_id, p1, p2, p3 in points:
                    rows[service_id_to_index[service_id]][tick] = p1 + p2 + p3
                data['points'] = rows
            self._write_json(filename, data)

    def __create_team_json(self) -> None:
        data = {team.id: {
            'name': team.name,
            'vulnbox': team.vulnbox_ip,
            'aff': team.affiliation or '',
            'web': team.website or '',
            'logo': team.logo + '.png' if team.logo else False
        } for team in self.teams}
        self._write_json('api/scoreboard_teams.json', data)

    def __create_logos(self) -> None:
        logo_path = config.SCOREBOARD_PATH / 'logos'
        if os.path.exists(logo_path):
            existing_images = os.listdir(logo_path)
        else:
            os.makedirs(logo_path, exist_ok=True)
            existing_images = []
        for team in self.teams:
            if team.logo and (team.logo + '.png') not in existing_images:
                TeamLogo.save_image(team.logo, logo_path / f'{team.logo}.png')

    def create_ctftime_json(self, roundnumber: int) -> str:
        with db_session_2() as session:
            rankings = self.calculation.get_ranking_for_tick(roundnumber, session=session)
            nop_team_ranking = 999999999
            for rank in rankings:
                if rank.team_id == config.SCORING.nop_team_id:
                    nop_team_ranking = rank.rank
                    break
            data = {'standings': [{
                'pos': ranking.rank - 1 if ranking.rank > nop_team_ranking else ranking.rank,
                'team': ranking.team.name,
                'score': round(ranking.points, 4)
            } for ranking in rankings if ranking.points > 0 and ranking.team_id != config.SCORING.nop_team_id]}
        return json.dumps(data, indent=4)

    '''
    def old_create_round_json(self, info: RoundInformation):
        # from sample_files.debug_sql_timing import timing
        roundnumber = info.roundnumber
        round_infos = {info.roundnumber: info}
        # timing()
        for team in self.teams:
            data = self.read_json('teams/{}.json'.format(team.id), {'name': team.name, 'scores': []})
            scores = data['scores']
            for i in range(0, roundnumber + 1):
                if len(scores) <= i:
                    scores.append(None)
                if not scores[i]:
                    # create entry for this round
                    if not i in round_infos:
                        round_infos[i] = self.fetch_data(i)
                    info = round_infos[i]
                    scores[i] = {
                        'round': i,
                        'rank': info.ranking_by_team_id[team.id].rank,
                        'points': info.ranking_by_team_id[team.id].points,
                        'services': [
                            {
                                'name': service.name,
                                'status': info.checker_results[(team.id, service.id)].status,
                                'flag_points': info.team_points[(team.id, service.id)].flag_points,
                                'sla_points': info.team_points[(team.id, service.id)].sla_points,
                                'sla_percent': (info.team_points[(team.id, service.id)].sla_points * 100 / (info.roundnumber or 1)
                                                if info.roundnumber > 0 else 1)
                            } for service in self.services
                        ]
                    }
            self.write_json('teams/{}.json'.format(team.id), data)

    # if team == self.teams[0]:
    # 	timing('Team '+team.name)
    '''

    def __fetch_data(self, roundnumber: int) -> RoundInformation:
        return RoundInformation(
            roundnumber,
            self.calculation.get_ranking_for_tick(roundnumber),
            self.calculation.get_results_for_tick_lite(roundnumber, [team.id for team in self.teams]),
            self.calculation.get_checker_results_lite(roundnumber)
        )

    @staticmethod
    def __get_first_blood_info(roundnumber: int) -> Dict[int, Tuple[List[str], Set[int]]]:
        """
        :param roundnumber:
        :return: A map from "service id" to a tuple ([list of first-blood teamnames, set-of-payloads-they-pwned])
        """
        result: Dict[int, Tuple[List[str], Set[int]]] = defaultdict(lambda: ([], set()))
        flags: List[SubmittedFlag] = SubmittedFlag.query.filter(SubmittedFlag.is_firstblood == True,
                                                                SubmittedFlag.round_submitted <= roundnumber) \
            .order_by(SubmittedFlag.ts).all()
        for flag in flags:
            lst, payloads = result[flag.service_id]
            payloads.add(flag.payload)
            team_name = flag.submitted_by_team.name
            if len(lst) == 0 or lst[-1] != team_name:
                lst.append(team_name)
        return result

    def check_scoreboard_prepared(self, force_recreate: bool = False) -> None:
        if not self.preparedStaticFiles or not (config.SCOREBOARD_PATH / 'api').exists() or force_recreate:
            config.SCOREBOARD_PATH.mkdir(exist_ok=True)
            (config.SCOREBOARD_PATH / 'api').mkdir(exist_ok=True)
            # copy resources for static builds (vpn board etc)
            static_dir: Path = Path(__file__).absolute().parent.parent / 'static'
            shutil.copyfile(static_dir / 'css' / 'index.css', config.SCOREBOARD_PATH / 'index.css')
            # copy angular build
            for fname in os.listdir(self.angular_build_path):
                if (self.angular_build_path / fname).is_dir():
                    if (config.SCOREBOARD_PATH / fname).exists():
                        shutil.rmtree(config.SCOREBOARD_PATH / fname)
                    shutil.copytree(self.angular_build_path / fname, config.SCOREBOARD_PATH / fname)
                else:
                    shutil.copyfile(self.angular_build_path / fname, config.SCOREBOARD_PATH / fname)
            self.preparedStaticFiles = True

    def _render_template(self, template: str, filename: str, minimize=False, **kwargs) -> None:
        """
        Render a template to file
        :param template:
        :param filename:
        :param kwargs:
        :return:
        """
        template_jinja = self.jinja2_env.get_template(template)
        content = template_jinja.render(**kwargs)
        if minimize:
            content = htmlmin.minify(content, remove_empty_space=True)
        with open(config.SCOREBOARD_PATH / filename, 'wb') as f:
            f.write(content.encode('utf-8'))

    def _read_json(self, filename: str, default: Any = None) -> Any:
        try:
            with open(config.SCOREBOARD_PATH / filename, 'r') as f:
                return json.loads(f.read())
        except IOError:
            return default or {}
        except ValueError:
            return default or {}

    def _write_json(self, filename: str, data: Any) -> None:
        s = json.dumps(data)
        # with gzip.open(config.SCOREBOARD_PATH / filename + '.gz'), 'wb') as f:
        #	f.write(s.encode('utf-8'))
        with open(config.SCOREBOARD_PATH / filename, 'w') as f:
            f.write(s)

    def update_team_info(self) -> None:
        self.teams = Team.query.order_by(Team.id).all()
        self.__create_logos()
        self.__create_team_json()


def run_scoreboard_generator() -> None:
    from controlserver.timer import Timer, CTFState
    from controlserver.logger import logResultOfExecution
    scoring = ScoringCalculation(config.SCORING)
    scoreboard = Scoreboard(scoring)

    print('Preparing old scoreboard data ...')
    # Create previous rounds if not existing
    scoreboard.check_scoreboard_prepared()
    scoreboard.update_team_info()
    has_started = Timer.state != CTFState.STOPPED
    prepare_until = Timer.currentRound - 1 if Timer.state == CTFState.RUNNING else Timer.currentRound
    current = -1
    if not scoreboard.exists(0, False):
        scoreboard.create_scoreboard(0, False, prepare_until == 0)
    while current <= prepare_until:
        if not scoreboard.exists(current, has_started):
            scoreboard.create_scoreboard(current, has_started, current == prepare_until)
            print(f'- Prepared scoreboard for tick {current}')
            prepare_until = Timer.currentRound - 1 if Timer.state == CTFState.RUNNING else Timer.currentRound
        current += 1
    print(f'Scoreboard prepared up to tick {current - 1}')

    # Listen for future scoreboard
    print('Waiting for new ticks ...')
    pubsub = get_redis_connection().pubsub()
    pubsub.subscribe(b'timing:scoreboard_tick')
    for item in pubsub.listen():
        if item['type'] == 'message':
            if item['channel'] == b'timing:scoreboard_tick':
                prepare_until = int(item['data'].decode())
                if prepare_until < current - 1:
                    print('  received ', prepare_until)
                while current <= prepare_until:
                    print(f'- Create scoreboard for tick {current} ...')
                    # scoreboard.create_scoreboard(current, Timer.state != CTFState.STOPPED, True)
                    logResultOfExecution('scoring',
                                         scoreboard.create_scoreboard,
                                         args=(current, Timer.state != CTFState.STOPPED, True),
                                         success='Scoreboard generated, took {:.1f} sec (daemon)',
                                         error='Scoreboard failed: {} {} (daemon)')
                    current += 1
