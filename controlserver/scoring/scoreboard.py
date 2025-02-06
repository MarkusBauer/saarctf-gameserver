"""
Write the scoreboard to disk.
"""
import os
import shutil
from abc import ABC, abstractmethod
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import htmlmin
from jinja2 import Environment, select_autoescape, FileSystemLoader
from filelock import FileLock
from sqlalchemy.orm import Session

from controlserver.models import TeamRanking, Team, TeamLogo, Service, CheckerResultLite, TeamPoints, TeamPointsLite, \
    SubmittedFlag, db_session_2
from controlserver.scoring.scoring import ScoringCalculation
from saarctf_commons.config import config
from saarctf_commons.redis import get_redis_connection
from saarctf_commons.db_utils import retry_on_sql_error

try:
    import ujson as json
except ImportError:
    import json  # type: ignore


class TickInformation:
    def __init__(self, ticknumber: int, ranking: list[TeamRanking], team_points: dict[tuple[int, int], TeamPointsLite],
                 checker_results: dict[tuple[int, int], CheckerResultLite]) -> None:
        self.ticknumber: int = ticknumber
        self.ranking: list[TeamRanking] = ranking
        self.ranking_by_team_id: dict[int, TeamRanking] = {r.team_id: r for r in ranking}
        self.team_points: dict[tuple[int, int], TeamPointsLite] = team_points
        self.checker_results: dict[tuple[int, int], CheckerResultLite] = checker_results

    def get_attacker_victim_count(self, previous_info: 'TickInformation') -> tuple[dict[int, int], dict[int, int]]:
        # precompute attacker/victim count
        attacker_count: dict[int, int] = defaultdict(lambda: 0)  # service_id => team_count
        victim_count: dict[int, int] = defaultdict(lambda: 0)
        for (team_id, service_id), pts in self.team_points.items():
            prev_pts = previous_info.team_points[(team_id, service_id)]
            if pts.flag_captured_count > prev_pts.flag_captured_count:
                attacker_count[service_id] += 1
            if pts.flag_stolen_count > prev_pts.flag_stolen_count:
                victim_count[service_id] += 1
        return attacker_count, victim_count


class StatisticJsonGenerator(ABC):
    """
    Job: maintain a JSON file with per-service, per-tick information. Format: {"services": [...], "<key>": [0: [a, b, c], ...]}
    where <key> and a,b,c are implementation-defined, called "the value".
    This class contains logic to perform the minimal necessary update to the file, but rewrite it in full if necessary.
    """

    def __init__(self, key: str) -> None:
        self.key = key

    @abstractmethod
    def get_single_tick_info(self, services: list[Service], info: TickInformation, previous_info: TickInformation) -> dict[int, Any]:
        """Return the value for the current tick. Format: {service-id: value}"""
        raise NotImplementedError()

    @abstractmethod
    def get_all_tick_info(self, services: list[Service], max_tick: int) -> dict[tuple[int, int], Any]:
        """Return the values for all ticks, up to and including max_tick. Format: {(tick, service-id): value}"""
        raise NotImplementedError()

    @abstractmethod
    def _empty_row(self, length: int) -> list[Any]:
        """Return an empty per-service row of given length, in case no information is available."""
        raise NotImplementedError()

    def _read(self, filename: str, default: dict) -> dict:
        try:
            return json.loads((config.SCOREBOARD_PATH / filename).read_text('utf-8'))
        except (IOError, ValueError):
            return default

    def update_file(self, filename: str, services: list[Service], info: TickInformation, previous_info: TickInformation) -> None:
        """
        Policy:
        - we ignore (and keep) all infos beyond our current tick number
        - we update if possible
        - we recreate if not possible
        """
        servicenames: list[str] = [service.name if info.ticknumber >= 0 else '???' for service in services]
        service_id_to_index = {service.id: i for i, service in enumerate(services)}
        data = self._read(filename, dict([('services', servicenames), (self.key, [[] for _ in range(len(services))])]))
        if len(data[self.key]) == 0:
            data['services'] = servicenames

        if info.ticknumber >= 0:
            # update existing files if possible
            if data['services'] == servicenames and len(data[self.key]) == len(services) \
                and all(len(row) >= max(0, info.ticknumber) for row in data[self.key]):
                # print(f'fast path {self.__class__.__name__} {info.ticknumber}')
                result = self.get_single_tick_info(services, info, previous_info)
                for service_id, value in result.items():
                    row = data[self.key][service_id_to_index[service_id]]
                    if len(row) > info.ticknumber:
                        row[info.ticknumber] = value
                    else:
                        row.append(value)
            else:
                # cannot update, recreate up to current location
                # print(f'slow path {self.__class__.__name__} {info.ticknumber}')
                rows: list[list[Any]] = data[self.key]
                if len(rows) != len(servicenames) or min(len(row) for row in rows) <= info.ticknumber:
                    rows = [self._empty_row(info.ticknumber + 1) for _ in services]
                if info.ticknumber > 0:
                    data['services'] = servicenames
                # fetch data from tick 0 up to now, and write to points table
                for (tick, service_id), result in self.get_all_tick_info(services, info.ticknumber).items():
                    rows[service_id_to_index[service_id]][tick] = result
                data[self.key] = rows

        (config.SCOREBOARD_PATH / filename).write_text(json.dumps(data), 'utf-8')


class TeamStatisticJsonGenerator(StatisticJsonGenerator):
    def __init__(self) -> None:
        super().__init__('points')
        self.team_id = 0

    def set_team_id(self, team_id: int) -> None:
        self.team_id = team_id

    def get_single_tick_info(self, services: list[Service], info: TickInformation, previous_info: TickInformation) -> dict[int, Any]:
        result = {}
        for service in services:
            pts = info.team_points[(self.team_id, service.id)]
            result[service.id] = pts.off_points + pts.def_points + pts.sla_points
        return result

    @retry_on_sql_error(attempts=3)
    def get_all_tick_info(self, services: list[Service], max_tick: int) -> dict[tuple[int, int], Any]:
        with db_session_2() as session:
            points = session.query(TeamPoints.tick, TeamPoints.service_id, TeamPoints.off_points,
                                   TeamPoints.def_points,
                                   TeamPoints.sla_points) \
                .filter(TeamPoints.team_id == self.team_id, 0 <= TeamPoints.tick,
                        TeamPoints.tick <= max_tick).all()
            return {(tick, service_id): p1 + p2 + p3 for tick, service_id, p1, p2, p3 in points}

    def _empty_row(self, length: int) -> list[Any]:
        return [0.0] * length


class ServiceStatisticJsonGenerator(StatisticJsonGenerator):
    def __init__(self) -> None:
        super().__init__('stats')

    def get_single_tick_info(self, services: list[Service], info: TickInformation, previous_info: TickInformation) -> dict[int, Any]:
        attacker_count, victim_count = info.get_attacker_victim_count(previous_info)
        return {service.id: {
            'a': attacker_count[service.id],
            'v': victim_count[service.id]
        } for service in services}

    @retry_on_sql_error(attempts=3)
    def get_all_tick_info(self, services: list[Service], max_tick: int) -> dict[tuple[int, int], Any]:
        with db_session_2() as session:
            raw_results = session.query(TeamPoints.tick, TeamPoints.team_id, TeamPoints.service_id,
                                        TeamPoints.flag_captured_count, TeamPoints.flag_stolen_count) \
                .filter(0 <= TeamPoints.tick, TeamPoints.tick <= max_tick).all()
            lookup: dict[tuple[int, int, int], tuple[int, int]] = \
                {(tick, team_id, service_id): (captured, stolen) for tick, team_id, service_id, captured, stolen in raw_results}
            result: dict[tuple[int, int], dict] = defaultdict(lambda: {'a': 0, 'v': 0})
            for tick, team_id, service_id, captured, stolen in raw_results:
                if (tick, team_id, service_id) in lookup:
                    last_captured, last_stolen = lookup[(tick, team_id, service_id)]
                    if captured > last_captured:
                        result[(tick, service_id)]['a'] += 1
                    if stolen > last_stolen:
                        result[(tick, service_id)]['v'] += 1
            return result

    def _empty_row(self, length: int) -> list[Any]:
        return [{'a': 0, 'v': 0}] * length


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
        self.teams: list[Team] = []
        self.services: list[Service] = []
        self.__should_publish = publish
        self.conn = get_redis_connection()

    def __publish(self, scoreboard_tick: int):
        self.conn.set('timing:scoreboard_tick', str(scoreboard_tick))
        self.conn.publish('timing:scoreboard_tick', str(scoreboard_tick))

    def update_tick_info(self, scoreboard_tick: int | None = None) -> int:
        self.check_scoreboard_prepared()
        scoreboard_tick = self.__create_tick_info_json(scoreboard_tick)
        if self.__should_publish:
            self.__publish(scoreboard_tick)
        return scoreboard_tick

    def exists(self, ticknumber: int, has_started: bool):
        """
        Return True if the scoreboard data for this tick has already been written (by #create_scoreboard)
        :param ticknumber:
        :param has_started:
        :return:
        """
        if ticknumber == 0 and not has_started:
            ticknumber = -1
        return (config.SCOREBOARD_PATH / 'api' / f'scoreboard_round_{ticknumber}.json').exists()

    @retry_on_sql_error(attempts=3)
    def __update_team_service_list(self) -> None:
        with db_session_2() as session:
            self.teams = session.query(Team).order_by(Team.id).all()
            self.services = session.query(Service).order_by(Service.id).all()
            session.expunge_all()

    @retry_on_sql_error(attempts=3)
    def create_scoreboard(self, ticknumber: int, has_started: bool = True, is_live: bool = False) -> None:
        """
        Write the scoreboard as it is AFTER a given tick
        :param ticknumber:
        :param has_started: True if the game already started. If False, service names will be hidden (by informal tick -1)
        :param is_live: True if that's the most recent tick
        :return:
        """
        self.__update_team_service_list()
        if ticknumber == 0 and not has_started:
            ticknumber = -1
        if self.__should_publish:
            self.__publish(ticknumber)
        with db_session_2() as session:
            info: TickInformation = self.__fetch_data(session, ticknumber)
            previous_info: TickInformation = self.__fetch_data(session, ticknumber - 1)
            last_checker_results: list[dict[tuple[int, int], CheckerResultLite]] = [
                previous_info.checker_results,
                self.calculation.get_checker_results_lite(session, ticknumber - 2),
                self.calculation.get_checker_results_lite(session, ticknumber - 3)
            ]
        # copy static files
        self.check_scoreboard_prepared()
        # render ALL the templates here
        # main scoreboard
        self.__create_logos()
        self.__create_team_json()
        # self.__create_main_html(info)
        self.__create_json_for_tick(info, previous_info, last_checker_results)
        self.__create_json_for_teams(info, previous_info)
        self.__create_service_stat_json(info, previous_info)
        if is_live:
            self.__create_tick_info_json(info.ticknumber)

    def __create_tick_info_json(self, scoreboard_tick: int | None) -> int:
        """
        Create a JSON file with the current tick, the last scoreboard result tick number and game state.
        :param scoreboard_tick:
        :return:
        """
        from controlserver.timer import Timer
        with self._lock():
            if scoreboard_tick is None:
                old_data = self._read_json('api/scoreboard_current.json', {'scoreboard_tick': -1})
                scoreboard_tick = old_data['scoreboard_tick']
            data = {
                'current_tick': Timer.current_tick,
                'state': Timer.state,
                'current_tick_until': Timer.tick_end,
                'scoreboard_tick': scoreboard_tick,
                'banned_teams': [int(b.decode()) for b in self.conn.smembers('network:banned')]
            }
            self._write_json('api/scoreboard_current.json', data)
        return scoreboard_tick

    def __create_json_for_tick(self, info: TickInformation, previous_info: TickInformation,
                               last_checker_results: list[dict[tuple[int, int], CheckerResultLite]]) -> None:
        """
        Create a JSON file with the precise results (checker, points, rank) of a tick.
        :param info:
        :param previous_info:
        :param last_checker_results:
        :return:
        """
        data: dict[str, Any] = {
            'tick': info.ticknumber,
            'scoreboard': []
        }
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
                    'st': pts.flag_stolen_count,  # flags stolen from this team
                    'cap': pts.flag_captured_count,  # flags captured by this team
                    'dst': pts.flag_stolen_count - prev_pts.flag_stolen_count,
                    'dcap': pts.flag_captured_count - prev_pts.flag_captured_count,
                    'c': check.status, 'm': check.message,
                    'dc': [results[(ranking.team_id, service.id)].status for results in last_checker_results]
                })
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
        first_blood_info = self.__get_first_blood_info(info.ticknumber)
        attacker_count, victim_count = info.get_attacker_victim_count(previous_info)
        data['services'] = [{
            'name': service.name if info.ticknumber >= 0 else '???',
            'attackers': attacker_count[service.id],
            'victims': victim_count[service.id],
            'first_blood': first_blood_info[service.id][0],
            'flag_stores': service.num_payloads if service.num_payloads > 1 else 1,
            'flag_stores_exploited': len(first_blood_info[service.id][1]) if service.num_payloads > 1 else (
                1 if first_blood_info[service.id][1] else 0)
        } for service in self.services]
        self._write_json(f'api/scoreboard_round_{info.ticknumber}.json', data)

    def __create_json_for_teams(self, info: TickInformation, previous_info: TickInformation) -> None:
        """
        Create files "scoreboard_team_<teamid>.json" containing the per-service points of each team.
        :param info:
        :return:
        """
        with self._lock():
            gen = TeamStatisticJsonGenerator()
            for team in self.teams:
                gen.set_team_id(team.id)
                filename = f'api/scoreboard_team_{team.id}.json'
                gen.update_file(filename, self.services, info, previous_info)

    def __create_service_stat_json(self, info: TickInformation, previous_info: TickInformation) -> None:
        with self._lock():
            gen = ServiceStatisticJsonGenerator()
            gen.update_file('api/scoreboard_service_stats.json', self.services, info, previous_info)

    def __create_team_json(self) -> None:
        with self._lock():
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

    def create_ctftime_json(self, ticknumber: int) -> str:
        with db_session_2() as session:
            rankings = self.calculation.get_ranking_for_tick(session, ticknumber)
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

    def __fetch_data(self, session: Session, ticknumber: int) -> TickInformation:
        return TickInformation(
            ticknumber,
            self.calculation.get_ranking_for_tick(session, ticknumber),
            self.calculation.get_results_for_tick_lite(session, ticknumber, [team.id for team in self.teams]),
            self.calculation.get_checker_results_lite(session, ticknumber)
        )

    @retry_on_sql_error(attempts=3)
    def __get_first_blood_info(self, ticknumber: int) -> dict[int, tuple[list[str], set[int]]]:
        """
        :param ticknumber:
        :return: A map from "service id" to a tuple ([list of first-blood teamnames, set-of-payloads-they-pwned])
        """
        with db_session_2() as session:
            result: dict[int, tuple[list[str], set[int]]] = defaultdict(lambda: ([], set()))
            flags: list[SubmittedFlag] = session.query(SubmittedFlag) \
                .filter(SubmittedFlag.is_firstblood == True, SubmittedFlag.tick_submitted <= ticknumber) \
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
        self.__update_team_service_list()
        self.__create_logos()
        self.__create_team_json()

    @contextmanager
    def _lock(self) -> Iterator[None]:
        with FileLock(config.SCOREBOARD_PATH / '.lock'):
            yield


def run_scoreboard_generator() -> None:
    from controlserver.timer import Timer, CTFState
    from controlserver.logger import log_result_of_execution
    scoring = ScoringCalculation(config.SCORING)
    scoreboard = Scoreboard(scoring)

    print('Preparing old scoreboard data ...')
    # Create previous ticks if not existing
    scoreboard.check_scoreboard_prepared()
    scoreboard.update_team_info()
    has_started = Timer.state != CTFState.STOPPED
    prepare_until = Timer.current_tick - 1 if Timer.state == CTFState.RUNNING else Timer.current_tick
    current = -1
    if not scoreboard.exists(0, False):
        scoreboard.create_scoreboard(0, False, prepare_until == 0)
    while current <= prepare_until:
        if not scoreboard.exists(current, has_started):
            scoreboard.create_scoreboard(current, has_started, current == prepare_until)
            print(f'- Prepared scoreboard for tick {current}')
            prepare_until = Timer.current_tick - 1 if Timer.state == CTFState.RUNNING else Timer.current_tick
        current += 1
    print(f'Scoreboard prepared up to tick {current - 1}')

    # listen for future scoreboard
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
                    log_result_of_execution('scoring',
                                            scoreboard.create_scoreboard,
                                            args=(current, Timer.state != CTFState.STOPPED, True),
                                            success='Scoreboard generated, took {:.1f} sec (daemon)',
                                            error='Scoreboard failed: {} {} (daemon)')
                    current += 1
