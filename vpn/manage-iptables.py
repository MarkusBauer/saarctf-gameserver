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

import os
import subprocess
import sys
from typing import Iterable, List

from sqlalchemy import func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.set_redis_clientname('VPN-Control')
config.EXTERNAL_TIMER = True

CHAIN = 'vpn-blocking'
CHAIN_ALLOW_TEAMS = 'vpn-allow-teams'
RULE_NETCLOSED = ['-j', 'REJECT', '-m', 'comment', '--comment', 'Network is closed']
RULE_NETTEAMONLY = ['-j', CHAIN_ALLOW_TEAMS, '-m', 'comment', '--comment', 'Network is open for teams only']


def iptables_add(chain: str, rule: List[str]):
	if not iptables_exists(chain, rule):
		subprocess.check_call(['iptables', '-A', chain] + rule)


def iptables_insert(chain: str, rule: List[str]):
	if not iptables_exists(chain, rule):
		subprocess.check_call(['iptables', '-I', chain, '1'] + rule)


def iptables_remove(chain: str, rule: List[str]):
	while subprocess.call(['iptables', '-D', chain] + rule, stderr=subprocess.DEVNULL) == 0:
		pass


def iptables_exists(chain: str, rule: List[str]) -> bool:
	ret = subprocess.call(['iptables', '-C', chain] + rule, stderr=subprocess.DEVNULL)
	return ret == 0


def fill_netteamonly_chain():
	from controlserver import app
	from controlserver.models import Team, db
	max_id = db.session.query(func.max(Team.id)).scalar()
	for team_id in range(1, max_id + 2):
		net = config.team_id_to_network_range(team_id)
		iptables_insert(CHAIN_ALLOW_TEAMS, ['-s', net, '-d', net, '-j', 'RETURN'])


def init_firewall(state: str, banned: Iterable[str], allowed: Iterable[str]):
	subprocess.check_call(['iptables', '-F', CHAIN])
	update_state(state)
	for team in banned:
		ban_team(team)
	for team in allowed:
		add_network_team(team)
	print('[OK]   Updated firewall')


def update_state(state: str):
	"""
	:param state: "on" or "team" or "off"
	:return:
	"""
	if state == 'on':
		iptables_remove(CHAIN, RULE_NETCLOSED)
		iptables_remove(CHAIN, RULE_NETTEAMONLY)
		print('[UP]   Network open')
	elif state == 'team':
		iptables_remove(CHAIN, RULE_NETCLOSED)
		iptables_add(CHAIN, RULE_NETTEAMONLY)
		# fill chain with -j RETURN for each team
		fill_netteamonly_chain()
		print('[TEAM] Network open within teams only')
	else:
		iptables_add(CHAIN, RULE_NETCLOSED)
		iptables_remove(CHAIN, RULE_NETTEAMONLY)
		print('[DOWN] Network closed')


def ban_team(team: str):
	iprange = config.team_id_to_network_range(int(team))
	# Ban regular interface
	rule1 = ['-i', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
	rule2 = ['-o', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
	iptables_add(CHAIN, rule1)
	iptables_add(CHAIN, rule2)
	# Ban "cloud"-interface (members)
	rule1 = ['-i', f'tun{1000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
	rule2 = ['-o', f'tun{1000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
	iptables_add(CHAIN, rule1)
	iptables_add(CHAIN, rule2)
	# Ban "cloud"-interface (vulnbox)
	rule1 = ['-i', f'tun{2000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
	rule2 = ['-o', f'tun{2000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
	iptables_add(CHAIN, rule1)
	iptables_add(CHAIN, rule2)
	print(f'[+B]   Ban team {team} ({iprange})')


def unban_team(team: str):
	iprange = config.team_id_to_network_range(int(team))
	rule1 = ['-i', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
	rule2 = ['-o', f'tun{team}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
	iptables_remove(CHAIN, rule1)
	iptables_remove(CHAIN, rule2)
	# Unban "cloud"-interface (members)
	rule1 = ['-i', f'tun{1000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
	rule2 = ['-o', f'tun{1000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
	iptables_remove(CHAIN, rule1)
	iptables_remove(CHAIN, rule2)
	# Unban "cloud"-interface (vulnbox)
	rule1 = ['-i', f'tun{2000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (incoming)']
	rule2 = ['-o', f'tun{2000 + int(team)}', '-j', 'DROP', '-m', 'comment', '--comment', f'Ban team {team} (outgoing)']
	iptables_remove(CHAIN, rule1)
	iptables_remove(CHAIN, rule2)
	print(f'[-B]   Remove ban from team {team} ({iprange})')


def add_network_team(team: str):
	"""
	Open the network for this team only (and for communication with gameserver only)
	:param team:
	:return:
	"""
	iprange1 = config.team_id_to_network_range(int(team))
	iprange2 = config.CONFIG['network']['gameserver_range']
	rule1 = ['--src', iprange1, '--dst', iprange2, '-j', 'RETURN', '-m', 'comment', '--comment', f'Open network for team {team}']
	rule2 = ['--src', iprange2, '--dst', iprange1, '-j', 'RETURN', '-m', 'comment', '--comment', f'Open network for team {team}']
	iptables_insert(CHAIN, rule2)
	iptables_insert(CHAIN, rule1)
	print(f'[+B]   Add network for team {team} ({iprange1} <-> {iprange2})')


def remove_network_team(team: str):
	iprange1 = config.team_id_to_network_range(int(team))
	iprange2 = config.CONFIG['network']['gameserver_range']
	rule1 = ['--src', iprange1, '--dst', iprange2, '-j', 'RETURN', '-m', 'comment', '--comment', f'Open network for team {team}']
	rule2 = ['--src', iprange2, '--dst', iprange1, '-j', 'RETURN', '-m', 'comment', '--comment', f'Open network for team {team}']
	iptables_remove(CHAIN, rule1)
	iptables_remove(CHAIN, rule2)
	print(f'[+B]   Remove network for team {team} ({iprange1} <-> {iprange2})')


def main():
	print('       Connecting...')
	redis = config.get_redis_connection()
	state_bytes = redis.get('network:state')
	state: str = state_bytes.decode() if state_bytes else None
	if state is None:
		redis.set('network:state', 'off')
		state = 'off'
	banned = redis.smembers('network:banned')
	allowed = redis.smembers('network:permissions')
	init_firewall(state, [team.decode() for team in banned], [team.decode() for team in allowed])

	pubsub = redis.pubsub()
	pubsub.subscribe('network:state', 'network:ban', 'network:unban', 'network:add_permission', 'network:remove_permission')
	for item in pubsub.listen():
		if item['type'] == 'message':
			print(f'[debug] message {repr(item["channel"])}, data {repr(item["data"])}')
			if item['channel'] == b'network:state':
				update_state(item['data'].decode())
			elif item['channel'] == b'network:ban':
				ban_team(item['data'].decode())
			elif item['channel'] == b'network:unban':
				unban_team(item['data'].decode())
			elif item['channel'] == b'network:add_permission':
				add_network_team(item['data'].decode())
			elif item['channel'] == b'network:remove_permission':
				remove_network_team(item['data'].decode())



if __name__ == '__main__':
	main()
