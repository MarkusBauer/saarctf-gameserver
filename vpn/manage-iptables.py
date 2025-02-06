#!/usr/bin/env python3

"""
Script that keeps running on the VPN server, dynamically adding iptables rules to:
- open/close the network
- ban/unban teams

Redis keys:
- network:state     "on" or "off" or "team"
- network:banned    <set of banned team ids>
Redis events
- network:state     "on" or "off" or "team"
- network:ban       <team id>
- network:unban     <team id>
"""
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from typing import Iterable, List, Any

from sqlalchemy import func
from redis import StrictRedis
from redis.exceptions import RedisError

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.models import Team, init_database, db_session_2
from saarctf_commons.logging_utils import setup_script_logging
from saarctf_commons.redis import get_redis_connection, NamedRedisConnection
from saarctf_commons.config import config, load_default_config

CHAIN = 'vpn-blocking'
RULE_NETCLOSED = ['-j', 'REJECT', '-m', 'comment', '--comment', 'Network is closed']
RULE_NETTEAMONLY = ['-m', 'mark', '--mark', '0x0800/0x0c00', '-j', 'RETURN', '-m', 'comment', '--comment', 'Network is open for teams only']


def iptables_add(chain: str, rule: List[str]) -> None:
    if not iptables_exists(chain, rule):
        subprocess.check_call(['iptables', '-A', chain] + rule)


def iptables_insert(chain: str, rule: List[str]) -> None:
    if not iptables_exists(chain, rule):
        subprocess.check_call(['iptables', '-I', chain, '1'] + rule)


def iptables_remove(chain: str, rule: List[str]) -> None:
    while subprocess.call(['iptables', '-D', chain] + rule, stderr=subprocess.DEVNULL) == 0:
        pass


def iptables_exists(chain: str, rule: List[str]) -> bool:
    ret = subprocess.call(['iptables', '-C', chain] + rule, stderr=subprocess.DEVNULL)
    return ret == 0


def iptables_flush(chain: str) -> None:
    subprocess.check_call(['iptables', '-F', chain])


class IpTablesManager:
    def __init__(self, chain: str = CHAIN) -> None:
        self.chain = chain
        self.state = 'off'
        self.banned: set[str] = set()
        self.allowed: set[str] = set()
        self._lock: threading.RLock = threading.RLock()

    def init_firewall(self, state: str, banned: Iterable[str], allowed: Iterable[str]) -> None:
        subprocess.check_call(['iptables', '-F', self.chain])
        self.banned = set(banned)
        self.allowed = set(allowed)
        self.state = state
        self.rewrite_chain()
        logging.info('[OK]   Updated firewall')

    def update_state(self, state: str) -> None:
        """
        :param state: "on" or "team" or "off"
        :return:
        """
        self.state = state
        self.rewrite_chain()

    def rewrite_chain(self) -> None:
        with self._lock:
            if self.state == 'on':
                iptables_flush(self.chain)
                logging.info('[UP]   Network open')
            elif self.state == 'team':
                iptables_flush(self.chain)
                iptables_add(self.chain, RULE_NETTEAMONLY)
                iptables_add(self.chain, RULE_NETCLOSED)
                logging.info('[TEAM] Network open within teams only')
            elif self.state == 'team-no-vulnbox':
                iptables_flush(self.chain)
                # first deny vulnboxes, then allow team-internal traffic, then deny other traffic. build backwards
                iptables_add(self.chain, RULE_NETCLOSED)
                iptables_insert(self.chain, RULE_NETTEAMONLY)
                self._insert_no_vulnbox_rules()
                logging.info('[TEAM] Network open within teams only, excluding vulnboxes')
            else:
                iptables_flush(self.chain)
                iptables_add(self.chain, RULE_NETCLOSED)
                logging.info('[DOWN] Network closed')
            for team in self.banned:
                self._ban_rules(team)
            for team in self.allowed:
                self._allow_rules(team)

    def _insert_no_vulnbox_rules(self) -> None:
        with db_session_2() as session:
            max_id = session.query(func.max(Team.id)).scalar()
        for team_id in range(1, max_id + 2):
            net = config.NETWORK.team_id_to_vulnbox_ip(team_id)
            iptables_insert(self.chain, ['-s', net, '-j', 'REJECT'])
            iptables_insert(self.chain, ['-d', net, '-j', 'REJECT'])

    def ban_team(self, team: str) -> None:
        self.banned.add(team)
        iprange = self._ban_rules(team)
        logging.info(f'[+B]   Ban team {team} ({iprange})')

    def _ban_rules(self, team: str) -> str:
        with self._lock:
            iprange = config.NETWORK.team_id_to_network_range(int(team))
            # Ban regular interface
            rule1 = ['-i', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
            rule2 = ['-o', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
            iptables_add(self.chain, rule1)
            iptables_add(self.chain, rule2)
            # Ban "cloud"-interface (members)
            rule1 = ['-i', f'tun{1000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
            rule2 = ['-o', f'tun{1000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
            iptables_add(self.chain, rule1)
            iptables_add(self.chain, rule2)
            # Ban "cloud"-interface (vulnbox)
            rule1 = ['-i', f'tun{2000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
            rule2 = ['-o', f'tun{2000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
            iptables_add(self.chain, rule1)
            iptables_add(self.chain, rule2)
        return iprange

    def unban_team(self, team: str) -> None:
        self.banned.discard(team)
        iprange = self._unban_rules(team)
        logging.info(f'[-B]   Remove ban from team {team} ({iprange})')

    def _unban_rules(self, team: str) -> str:
        with self._lock:
            iprange = config.NETWORK.team_id_to_network_range(int(team))
            rule1 = ['-i', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
            rule2 = ['-o', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
            iptables_remove(self.chain, rule1)
            iptables_remove(self.chain, rule2)
            # Unban "cloud"-interface (members)
            rule1 = ['-i', f'tun{1000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
            rule2 = ['-o', f'tun{1000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
            iptables_remove(self.chain, rule1)
            iptables_remove(self.chain, rule2)
            # Unban "cloud"-interface (vulnbox)
            rule1 = ['-i', f'tun{2000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
            rule2 = ['-o', f'tun{2000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
            iptables_remove(self.chain, rule1)
            iptables_remove(self.chain, rule2)
        return iprange

    def add_network_team(self, team: str) -> None:
        """
        Open the network for this team only (and for communication with gameserver only)
        :param team:
        :return:
        """
        self.allowed.add(team)
        iprange1, iprange2 = self._allow_rules(team)
        logging.info(f'[+A]   Add network for team {team} ({iprange1} <-> {iprange2})')

    def _allow_rules(self, team: str) -> tuple[str, str]:
        with self._lock:
            iprange1 = config.NETWORK.team_id_to_network_range(int(team))
            iprange2 = config.CONFIG['network']['gameserver_range']
            rule1 = ['--src', iprange1, '--dst', iprange2, '-j', 'RETURN', '-m', 'comment', '--comment', f'Open network for team {team}']
            rule2 = ['--src', iprange2, '--dst', iprange1, '-j', 'RETURN', '-m', 'comment', '--comment', f'Open network for team {team}']
            iptables_insert(self.chain, rule2)
            iptables_insert(self.chain, rule1)
        return iprange1, iprange2

    def remove_network_team(self, team: str) -> None:
        self.allowed.discard(team)
        iprange1, iprange2 = self._disallow_rules(team)
        logging.info(f'[-A]   Remove network for team {team} ({iprange1} <-> {iprange2})')

    def _disallow_rules(self, team: str) -> tuple[str, str]:
        with self._lock:
            iprange1 = config.NETWORK.team_id_to_network_range(int(team))
            iprange2 = config.CONFIG['network']['gameserver_range']
            rule1 = ['--src', iprange1, '--dst', iprange2, '-j', 'RETURN', '-m', 'comment', '--comment', f'Open network for team {team}']
            rule2 = ['--src', iprange2, '--dst', iprange1, '-j', 'RETURN', '-m', 'comment', '--comment', f'Open network for team {team}']
            iptables_remove(self.chain, rule1)
            iptables_remove(self.chain, rule2)
        return iprange1, iprange2


class NewTeamWatcher(threading.Thread):
    def __init__(self, manager: IpTablesManager) -> None:
        super().__init__(name='team-watcher', daemon=True)
        self._manager = manager
        self._running = True

    def run(self) -> None:
        with db_session_2() as session:
            num_teams = session.query(Team).count()

        while self._running:
            try:
                with db_session_2() as session:
                    current_num_teams = session.query(Team).count()
                if num_teams != current_num_teams and self._running:
                    logging.info(f'[team] Number of teams changed from {num_teams} to {current_num_teams}, re-writing rules...')
                    self._manager.rewrite_chain()
                    num_teams = current_num_teams
            except:
                logging.exception('team number check failed')
                traceback.print_exc()
            time.sleep(60)

    def stop(self) -> None:
        self._running = False

    def __enter__(self) -> 'NewTeamWatcher':
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()


def manage_iptables(redis: StrictRedis) -> None:
    state_bytes = redis.get('network:state')
    state: str | None = state_bytes.decode() if state_bytes else None
    if state is None:
        redis.set('network:state', 'off')
        state = 'off'
    banned = redis.smembers('network:banned')
    allowed = redis.smembers('network:permissions')

    pubsub = redis.pubsub()
    pubsub.subscribe('network:state', 'network:ban', 'network:unban', 'network:add_permission',
                     'network:remove_permission')

    manager = IpTablesManager(CHAIN)
    manager.init_firewall(state, [team.decode() for team in banned], [team.decode() for team in allowed])

    with NewTeamWatcher(manager):
        for item in pubsub.listen():
            if item['type'] == 'message':
                if item['channel'] == b'network:state':
                    manager.update_state(item['data'].decode())
                elif item['channel'] == b'network:ban':
                    manager.ban_team(item['data'].decode())
                elif item['channel'] == b'network:unban':
                    manager.unban_team(item['data'].decode())
                elif item['channel'] == b'network:add_permission':
                    manager.add_network_team(item['data'].decode())
                elif item['channel'] == b'network:remove_permission':
                    manager.remove_network_team(item['data'].decode())
                else:
                    logging.info(f'[debug] unknown message {repr(item["channel"])}, data {repr(item["data"])}')


def main() -> None:
    for _ in range(18):  # wait at most 3 minutes if redis connections fail, then abort
        try:
            logging.info('       Connecting to redis...')
            redis = get_redis_connection()
            manage_iptables(redis)
            return
        except RedisError:
            traceback.print_exc()
            logging.info('       waiting for reconnect ...')
            time.sleep(10)
    raise Exception('Too many connection retries')


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    setup_script_logging('manage-iptables')
    NamedRedisConnection.set_clientname('iptables-Control')
    init_database()
    main()
