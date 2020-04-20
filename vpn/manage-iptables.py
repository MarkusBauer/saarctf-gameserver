#!/usr/bin/env python3

"""
Script that keeps running on the VPN server, dynamically adding iptables rules to:
- open/close the network
- ban/unban teams

Redis keys:
- network:state     "on" or "off"
- network:banned    <set of banned team ids>
Redis events
- network:state     "on" or "off"
- network:ban       <team id>
- network:unban     <team id>
"""

import os
import subprocess
import sys
from typing import Iterable, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.set_redis_clientname('VPN-Control')
config.EXTERNAL_TIMER = True

CHAIN = 'vpn-blocking'
RULE_NETCLOSED = ['-j', 'REJECT', '-m', 'comment', '--comment', 'Network is closed']


def iptables_add(chain: str, rule: List[str]):
    if not iptables_exists(chain, rule):
        subprocess.check_call(['iptables', '-A', chain] + rule)


def iptables_remove(chain: str, rule: List[str]):
    while subprocess.call(['iptables', '-D', chain] + rule, stderr=subprocess.DEVNULL) == 0:
        pass


def iptables_exists(chain: str, rule: List[str]) -> bool:
    ret = subprocess.call(['iptables', '-C', chain] + rule, stderr=subprocess.DEVNULL)
    return ret == 0


def init_firewall(state: str, banned: Iterable[str]):
    subprocess.check_call(['iptables', '-F', CHAIN])
    update_state(state)
    for team in banned:
        ban_team(team)
    print('[OK]   Updated firewall')


def update_state(state: str):
    """
    :param state: "on" or "off"
    :return:
    """
    if state == 'on':
        iptables_remove(CHAIN, RULE_NETCLOSED)
        print('[UP]   Network open')
    else:
        iptables_add(CHAIN, RULE_NETCLOSED)
        print('[DOWN] Network closed')


def ban_team(team: str):
    iprange = config.team_id_to_network_range(int(team))
    rule1 = ['-i', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
    rule2 = ['-o', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
    iptables_add(CHAIN, rule1)
    iptables_add(CHAIN, rule2)
    print(f'[+B]   Ban team {team} ({iprange})')


def unban_team(team: str):
    iprange = config.team_id_to_network_range(int(team))
    rule1 = ['-i', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
    rule2 = ['-o', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
    iptables_remove(CHAIN, rule1)
    iptables_remove(CHAIN, rule2)
    print(f'[-B]   Remove ban from team {team} ({iprange})')


def main():
    print('       Connecting...')
    redis = config.get_redis_connection()
    state_bytes = redis.get('network:state')
    state: str = state_bytes.decode() if state_bytes else None
    if state is None:
        redis.set('network:state', 'off')
        state = 'off'
    banned = redis.smembers('network:banned')
    init_firewall(state, [team.decode() for team in banned])

    pubsub = redis.pubsub()
    pubsub.subscribe('network:state', 'network:ban', 'network:unban')
    for item in pubsub.listen():
        if item['type'] == 'message':
            print(f'[debug] message {repr(item["channel"])}, data {repr(item["data"])}')
            if item['channel'] == b'network:state':
                update_state(item['data'].decode())
            elif item['channel'] == b'network:ban':
                ban_team(item['data'].decode())
            elif item['channel'] == b'network:unban':
                unban_team(item['data'].decode())


if __name__ == '__main__':
    main()
