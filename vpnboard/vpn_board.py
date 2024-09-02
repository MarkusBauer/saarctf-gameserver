import datetime
import os
import shutil
import sys
import threading
import time
import traceback
from multiprocessing.pool import ThreadPool
from pathlib import Path
from typing import Dict, Optional, List, Iterable, Set

import htmlmin
import sqlalchemy
from jinja2 import Environment, FileSystemLoader, select_autoescape

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.models import Team, db_session, init_database
from saarctf_commons.config import config, load_default_config
from saarctf_commons.redis import NamedRedisConnection, get_redis_connection
from vpnboard.vpnchecks import test_ping, test_nping, test_web

try:
    import ujson as json
except ImportError:
    import json  # type: ignore


def eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


class TeamResult:
    def __init__(self) -> None:
        self.router_ping_ms: Optional[float] = None
        self.testbox_ping_ms: Optional[float] = None
        self.testbox_ok: bool = False
        self.testbox_err: Optional[str] = None
        self.vulnbox_ping_ms: Optional[float] = None  # only filled if explicitly selected


class VpnBoard:
    jinja2_env = Environment(
        loader=FileSystemLoader(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')),
        autoescape=select_autoescape(['html', 'xml'])
    )

    def __init__(self, use_nping: bool) -> None:
        self.use_nping = use_nping
        if not config.VPNBOARD_PATH.exists():
            self.create_directories()
        if not os.path.exists(config.VPNBOARD_PATH / 'index.css'):
            self.copy_static_files()

    def create_directories(self) -> None:
        config.VPNBOARD_PATH.mkdir(exist_ok=True)

    def copy_static_files(self) -> None:
        static_dir: Path = Path(os.path.abspath(__file__)).parent.parent / 'controlserver' / 'static'
        shutil.copyfile(static_dir / 'css' / 'vpnboard.css', config.VPNBOARD_PATH / 'index.css')
        shutil.copyfile(static_dir / 'img' / 'favicon.png', config.VPNBOARD_PATH / 'favicon.png')

    def render_template(self, template: str, filename: str, minimize=False, **kwargs) -> None:
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
        with open(config.VPNBOARD_PATH / filename, 'wb') as f:
            f.write(content.encode('utf-8'))

    def write_json(self, filename: str, data):
        with open(config.VPNBOARD_PATH / filename, 'w') as f:
            json.dump(data, f)

    def build_vpn_json(self, teams: Iterable[Team]):
        data = {
            'teams': [{
                'id': team.id,
                'name': team.name,
                'ip': config.NETWORK.team_id_to_vulnbox_ip(team.id),
                'online': team.vpn_connected or team.vpn2_connected,
                'ever_online': team.vpn_last_connect is not None,
            } for team in teams]
        }
        self.write_json('all_teams.json', data)
        data = {
            'teams': [{
                'id': team.id,
                'name': team.name,
                'ip': config.NETWORK.team_id_to_vulnbox_ip(team.id),
                'online': team.vpn_connected or team.vpn2_connected,
                'ever_online': team.vpn_last_connect is not None
            } for team in teams if team.vpn_connected or team.vpn2_connected or team.vpn_last_connect is not None]
        }
        self.write_json('available_teams.json', data)

    def collect_team_results_threadpool(self, teams: List[Team], check_vulnboxes: bool = False) -> Dict[
        int, TeamResult]:
        """
        Dispatch tasks that check the connectivity of all given teams and return status info.
        Do not use celery, but an in-process threadpool instead.
        :param teams:
        :param check_vulnboxes: Only if True the vulnbox IPs will be pinged
        :return:
        """
        if not teams:
            return {}
        results: Dict[int, TeamResult] = {team.id: TeamResult() for team in teams}
        pool = ThreadPool(16)
        try:
            ping_func = test_nping if self.use_nping else test_ping
            data = pool.imap_unordered(lambda team: (
                team.id,
                # nping to gateway seems heavily rate-limited. We use normal ping instead.
                (test_ping if team.vpn2_connected or not self.use_nping else test_nping) \
                    (config.NETWORK.team_id_to_gateway_ip(team.id)),
                ping_func(config.NETWORK.team_id_to_testbox_ip(team.id)),
                test_web(config.NETWORK.team_id_to_testbox_ip(team.id)),
                ping_func(config.NETWORK.team_id_to_vulnbox_ip(team.id)) if check_vulnboxes else None,
            ), teams, 1)
        finally:
            pool.close()

        for team_id, ping_router, ping_testbox, web_testbox, ping_vulnbox in data:
            results[team_id].router_ping_ms = ping_router if isinstance(ping_router, float) else None
            results[team_id].testbox_ping_ms = ping_testbox if isinstance(ping_testbox, float) else None
            results[team_id].vulnbox_ping_ms = ping_vulnbox if isinstance(ping_vulnbox, float) else None
            if isinstance(web_testbox, str):
                results[team_id].testbox_ok = web_testbox == 'OK'
                results[team_id].testbox_err = web_testbox
            else:
                results[team_id].testbox_ok = False
                results[team_id].testbox_err = str(web_testbox)

        pool.join()
        return results

    def print_results_for_influxdb(self, ts: datetime.datetime, teams: List[Team], results: Dict[int, TeamResult],
                                   check_vulnboxes: bool) -> None:
        influx_ts = int(ts.timestamp() * 1000000000)
        routers_up = 0
        testbox_up = 0
        vulnbox_up = 0
        for team in teams:
            if team.id in results:
                result = results[team.id]
                fields = {
                    'router_up': '0i' if result.router_ping_ms is None else '1i',
                    'testbox_up': '0i' if result.testbox_ping_ms is None else '1i',
                    'testbox_ok': '0i' if result.testbox_ok else '1i',
                }
                if result.router_ping_ms is not None:
                    fields['router_ping_ms'] = str(result.router_ping_ms)
                    routers_up += 1
                if result.testbox_ping_ms is not None:
                    fields['testbox_ping_ms'] = str(result.testbox_ping_ms)
                    testbox_up += 1
                if check_vulnboxes:
                    fields['vulnbox_up'] = '0i' if result.vulnbox_ping_ms is None else '1i'
                    if result.vulnbox_ping_ms is not None:
                        vulnbox_up += 1
                    if result.vulnbox_ping_ms:
                        fields['vulnbox_ping_ms'] = str(result.vulnbox_ping_ms)
                fields_str = ','.join(f'{k}={v}' for k, v in fields.items())
                print(f'vpn_connection,team_id={team.id}i connected=1i {influx_ts}')
                print(f'vpn_board,team_id={team.id}i {fields_str} {influx_ts}')
            else:
                print(f'vpn_connection,team_id={team.id}i connected=0i {influx_ts}')
        print(f'vpn_connection_count,kind=router connected={routers_up}i {influx_ts}')
        print(f'vpn_connection_count,kind=testbox connected={testbox_up}i {influx_ts}')
        if check_vulnboxes:
            print(f'vpn_connection_count,kind=vulnbox connected={vulnbox_up}i {influx_ts}')

    def build_vpn_board(self, check_vulnboxes: bool = False, banned_teams: Set[int] | None = None) -> None:
        if banned_teams is None:
            banned_teams = set()
        db_session().expire_all()
        start = datetime.datetime.now(datetime.timezone.utc)
        teams = Team.query.order_by(Team.id).all()
        connected_teams = [team for team in teams if team.vpn_connected or team.vpn2_connected]
        results = self.collect_team_results_threadpool(connected_teams, check_vulnboxes)
        self.render_template('vpn.html', 'vpn.html', minimize=True, start=start, teams=teams, results=results,
                             check_vulnboxes=check_vulnboxes, banned_teams=banned_teams)
        self.build_vpn_json(teams)
        self.print_results_for_influxdb(start, teams, results, check_vulnboxes)
        seconds = (datetime.datetime.now(datetime.timezone.utc) - start).total_seconds()
        eprint(
            f'{start.strftime("%d.%m.%Y %H:%M:%S")}: Created VPN board, took {seconds:.3f} seconds ({"with" if check_vulnboxes else "without"} vulnboxes).')


class VpnStatusThread(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name='Redis Connection', daemon=True)
        self.vulnbox_connection_available = False
        self.banned_teams: Set[int] = set()

    def run(self) -> None:
        redis = get_redis_connection()
        state_bytes = redis.get('network:state')
        state: str = state_bytes.decode() if state_bytes else None
        if state is None:
            redis.set('network:state', 'off')
            self.vulnbox_connection_available = False
        else:
            self.vulnbox_connection_available = (state == 'on' or state == 'team')
        for banned_bytes in redis.smembers('network:banned'):
            self.banned_teams.add(int(banned_bytes.decode()))

        pubsub = redis.pubsub()
        pubsub.subscribe('network:state', 'network:ban', 'network:unban')
        for item in pubsub.listen():
            if item['type'] == 'message':
                if item['channel'] == b'network:state':
                    state = item['data'].decode()
                    self.vulnbox_connection_available = (state == 'on' or state == 'team')
                elif item['channel'] == b'network:ban':
                    self.banned_teams.add(int(item['data'].decode()))
                elif item['channel'] == b'network:unban':
                    self.banned_teams.discard(int(item['data'].decode()))


def main() -> None:
    use_nping = '--system-ping' not in sys.argv
    board = VpnBoard(use_nping=use_nping)

    check_vulnboxes_status = VpnStatusThread()
    check_vulnboxes_status.start()

    if '--daemon' in sys.argv:
        time.sleep(1)  # give redis time to connect
        eprint(f'{datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}: VPN Board daemon started.')
        while True:
            start = time.time()
            try:
                board.build_vpn_board(check_vulnboxes_status.vulnbox_connection_available,
                                      check_vulnboxes_status.banned_teams)
            except sqlalchemy.exc.SQLAlchemyError:
                traceback.print_exc()
                eprint(f'{datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}: Could not create VPN board.')
                sys.exit(1)
            except:
                traceback.print_exc()
                eprint(f'{datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}: Could not create VPN board.')
            duration = time.time() - start
            sleeptime = min(60, max(5, round((60 if duration >= 25 else 30) - duration)))
            eprint(f'sleeping {sleeptime} ...')
            time.sleep(sleeptime)
    else:
        time.sleep(1)
        board.build_vpn_board(check_vulnboxes_status.vulnbox_connection_available, check_vulnboxes_status.banned_teams)


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('VPN-Board Daemon')
    init_database()
    main()
