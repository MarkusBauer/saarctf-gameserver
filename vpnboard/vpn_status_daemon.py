import datetime
import logging
import os
import sys
import threading
import time
import traceback
from multiprocessing.pool import ThreadPool
from typing import Set, Any

import sqlalchemy
from redis import StrictRedis
from redis.exceptions import RedisError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.models import Team, init_database, db_session_2
from saarctf_commons.config import config, load_default_config
from saarctf_commons.db_utils import retry_on_sql_error
from saarctf_commons.logging_utils import setup_script_logging
from saarctf_commons.metric_utils import setup_default_metrics
from saarctf_commons.redis import NamedRedisConnection, get_redis_connection
from vpnboard import VpnStatus, VpnStatusHandler
from vpnboard.records import WireguardPeerLogger, MetricStatusHandler
from vpnboard.vpn_board import VpnBoard
from vpnboard.vpnchecks import test_ping, test_nping, test_web
from vpnboard.wg_status import get_wireguard_status

USE_WIREGUARD: bool = True
PING_CONCURRENCY: int = 24


class VpnStatusThread(threading.Thread):
    def __init__(self) -> None:
        super().__init__(name='Redis Connection', daemon=True)
        self._logger = logging.Logger(self.__class__.__name__)
        self.vulnbox_connection_available = False
        self.banned_teams: Set[int] = set()
        self.initialized: bool = False

    def run(self) -> None:
        for _ in range(18):  # wait at most 3 minutes if redis connections fail, then abort
            try:
                self._watch_redis(get_redis_connection())
                return
            except RedisError:
                traceback.print_exc()
                logging.info('waiting for reconnect ...')
                time.sleep(10)
                logging.info('reconnecting ...')
        print('Too many connection attempts')
        sys.exit(1)

    def _watch_redis(self, redis: StrictRedis) -> None:
        state_bytes = redis.get('network:state')
        state: str | None = state_bytes.decode() if state_bytes else None
        if state is None:
            redis.set('network:state', 'off')
            self.vulnbox_connection_available = False
        else:
            self.vulnbox_connection_available = (state == 'on' or state == 'team')
        for banned_bytes in redis.smembers('network:banned'):
            self.banned_teams.add(int(banned_bytes.decode()))
        self.initialized = True

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


class VpnStatusDaemon:
    """
    Periodically collect VPN status information and route it to affected components.
    These are: DB, VpnBoard, Logs, Metrics
    """

    def __init__(self, use_nping: bool) -> None:
        self.use_nping = use_nping
        self._logger = logging.getLogger('vpn_status_daemon')
        self._vpn_status = VpnStatusThread()
        self._handlers: list[VpnStatusHandler] = [
            VpnBoard(),
            MetricStatusHandler(),
            WireguardPeerLogger()
        ]

    def __enter__(self) -> 'VpnStatusDaemon':
        self._vpn_status.start()
        # give redis time to connect
        for _ in range(12):
            if self._vpn_status.initialized:
                break
            time.sleep(1)

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass

    @retry_on_sql_error(attempts=40, sleeptime=1.5)
    def update_status(self, check_vulnboxes: bool) -> list[VpnStatus]:
        with db_session_2() as session:
            states = [VpnStatus(team) for team in session.query(Team).order_by(Team.id).all()]
            if USE_WIREGUARD:
                self.update_team_wireguard_status(states)
                session.commit()
            self.ping_teams_threadpool([s for s in states if s.connected], check_vulnboxes)
            session.expunge_all()
            return states

    def update_team_wireguard_status(self, states: list[VpnStatus]) -> None:
        """Fetch the current wireguard status from wireguard and write to DB"""
        from pyroute2 import WireGuard
        with WireGuard() as wg:
            for team_status in states:
                team = team_status.team
                # fetch status
                try:
                    team_status.wg = get_wireguard_status(team.id, wg=wg)
                except ValueError as e:
                    self._logger.warning(f'Team {team.id} has no readable interface ({e})')
                    if team.wg_boxes_connected or team.wg_vulnbox_connected:
                        team.wg_boxes_connected = False
                        team.wg_vulnbox_connected = False
                        team.vpn_connection_count = 0
                    continue

                # check vulnbox connection status
                vulnbox_peer = team_status.wg.get_peer_for(config.NETWORK.team_id_to_vulnbox_ip(team.id))
                if vulnbox_peer is not None:
                    if not team.wg_vulnbox_connected and vulnbox_peer.connected:
                        # new connection
                        team.wg_vulnbox_connected = True
                        team.vpn_last_connect = vulnbox_peer.last_handshake
                    elif team.wg_vulnbox_connected and not vulnbox_peer.connected:
                        # disconnect
                        team.wg_vulnbox_connected = False
                        if vulnbox_peer.last_handshake is not None:
                            team.vpn_last_disconnect = vulnbox_peer.last_handshake + datetime.timedelta(minutes=2)
                        else:
                            team.vpn_last_disconnect = datetime.datetime.now()
                elif team.wg_vulnbox_connected:
                    # peer disappeared, no disconnect timestamp
                    team.wg_vulnbox_connected = False
                # check router/testbox connection status
                interesting_peers = [
                    vulnbox_peer,
                    team_status.wg.get_peer_for(config.NETWORK.team_id_to_gateway_ip(team.id)),
                    team_status.wg.get_peer_for(config.NETWORK.team_id_to_testbox_ip(team.id))
                ]
                boxes_connected = any(p is not None and p.connected for p in interesting_peers)
                if boxes_connected != team.wg_boxes_connected:
                    team.wg_boxes_connected = boxes_connected
                # connection count
                cc = team_status.wg.connection_count
                if cc != team.vpn_connection_count:
                    team.vpn_connection_count = cc

    def ping_teams_threadpool(self, states: list[VpnStatus], check_vulnboxes: bool = False) -> None:
        """
        Dispatch tasks that check the connectivity of all given teams and update status info with ping timings.
        Do not use celery, but an in-process threadpool instead.
        :param states:
        :param check_vulnboxes: Only if True the vulnbox IPs will be pinged
        :return:
        """
        if not states:
            return
        pool = ThreadPool(PING_CONCURRENCY)
        try:
            ping_func = test_nping if self.use_nping else test_ping
            data = pool.imap_unordered(lambda s: (
                s,
                # nping to gateway seems heavily rate-limited. We use normal ping instead.
                (test_ping if s.team.vpn2_connected or not self.use_nping else test_nping) \
                    (config.NETWORK.team_id_to_gateway_ip(s.team.id)),
                ping_func(config.NETWORK.team_id_to_testbox_ip(s.team.id)),
                test_web(config.NETWORK.team_id_to_testbox_ip(s.team.id)),
                ping_func(config.NETWORK.team_id_to_vulnbox_ip(s.team.id)) if check_vulnboxes else None,
            ), states, 1)
        finally:
            pool.close()

        for state, ping_router, ping_testbox, web_testbox, ping_vulnbox in data:
            state.router_ping_ms = ping_router if isinstance(ping_router, float) else None
            state.testbox_ping_ms = ping_testbox if isinstance(ping_testbox, float) else None
            state.vulnbox_ping_ms = ping_vulnbox if isinstance(ping_vulnbox, float) else None
            if isinstance(web_testbox, str):
                state.testbox_ok = web_testbox == 'OK'
                state.testbox_err = web_testbox
            else:
                state.testbox_ok = False
                state.testbox_err = str(web_testbox)

        pool.join()

    def run_once(self) -> None:
        start = time.time()
        check_vulnboxes = self._vpn_status.vulnbox_connection_available
        states = self.update_status(check_vulnboxes)

        for handler in self._handlers:
            handler.update(states, self._vpn_status.banned_teams, check_vulnboxes, start)

        duration = time.time() - start
        self._logger.info(f'Created VPN board, took {duration:.3f} seconds '
                          f'({"with" if self._vpn_status.vulnbox_connection_available else "without"} vulnboxes).')

    def run_loop(self) -> None:
        self._logger.info('VPN Board daemon started.')
        while True:
            start = time.monotonic()
            try:
                self.run_once()
            except sqlalchemy.exc.SQLAlchemyError:
                self._logger.exception('Could not create VPN board.')
                sys.exit(1)
            except:
                self._logger.exception('Could not create VPN board.')
            duration = time.monotonic() - start
            sleeptime = min(60, max(5, round((60 if duration >= 25 else 30) - duration)))
            self._logger.debug(f'sleeping {sleeptime} ...')
            time.sleep(sleeptime)


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('VPN-Board Daemon')
    setup_script_logging('vpn-status-daemon')
    setup_default_metrics()
    init_database()

    use_nping = '--system-ping' not in sys.argv
    with VpnStatusDaemon(use_nping) as vpn_status_daemon:
        if '--daemon' in sys.argv:
            vpn_status_daemon.run_loop()
        else:
            vpn_status_daemon.run_once()
