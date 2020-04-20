#!/usr/bin/env python3

"""
Script that periodically writes the network statistics into database.
"""

import ctypes
import datetime
import json
import os
import sys
import time
from math import floor
from typing import Iterable, Dict, List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.set_redis_clientname('VPN-Stats')
config.EXTERNAL_TIMER = True

libbpf = ctypes.CDLL("libbpf.so")

# how often you want results. Should be 60 for now, and must be a divisor or multiple of 60
TICK_TIME = 60

BPF_RETRY_COUNT = 100

'''
=== Format of the map data ===
Key: __u32 team_id
Type: 4* 4* __u64
- egress_with_game   = (packets, bytes, syns, syn_acks)
- egress_with_teams  = (packets, bytes, syns, syn_acks)
- ingress_with_total = (packets, bytes, syns, syn_acks)
- ingress_with_teams = (packets, bytes, syns, syn_acks)

egress:  team's download, vpn -> team
ingress: team's upload,   team -> vpn

The map is created and filled by a BPF program (vpn/bpf/traffic_stats), 
which is attached to every tun interface (vpn/on-connect.sh, vpn/bpf/install.sh).
All counters are absolute (since map creation) and only increasing. 

We read: down_game, down_team, up_game, up_teams (not: total)
'''


def open_bpfmap(fname: str) -> int:
	global BPF_RETRY_COUNT
	fd = libbpf.bpf_obj_get(fname.encode())
	while fd < 0 and BPF_RETRY_COUNT > 0:
		print('[-] BPF map not available, retry later ...')
		BPF_RETRY_COUNT -= 1
		time.sleep(10)
		fd = libbpf.bpf_obj_get(fname.encode())
	if fd < 0:
		raise Exception('Could not open BPF map')
	return fd


def read_team_infos(fd: int, team_ids: Iterable[int]) -> Dict[int, List[int]]:
	"""
	:param fd:
	:param team_ids:
	:return: Dict [team_id => value_list] where value_list = [down_game, down_team, up_game, up_teams]
	"""
	key = (ctypes.c_int32 * 1)(1)
	value = (ctypes.c_int64 * 16)()
	result = {}
	for team_id in team_ids:
		key[0] = team_id
		if libbpf.bpf_map_lookup_elem(fd, key, value) != 0:
			raise Exception(f"Key {team_id} not found")
		stats = list(value)
		# correct "total" entry
		stats[8] -= stats[12]
		stats[9] -= stats[13]
		stats[10] -= stats[14]
		stats[11] -= stats[15]
		result[team_id] = stats
	# print(f'{team_id}: {result[team_id]}')
	return result


def wait_for_next_tick(offset: float = 1):
	ts = time.time() % TICK_TIME
	waittime = TICK_TIME - (ts % TICK_TIME)
	if offset < 0 and waittime - offset > TICK_TIME:
		return
	if waittime < offset:
		waittime += TICK_TIME
	print(f'...  next action in {waittime:.1f} sec')
	time.sleep(waittime)


def save_difference(timestamp: int, new_results: Dict[int, List[int]], last_minute_results: Dict[int, List[int]]):
	from controlserver.models import TeamTrafficStats, db
	stuff_to_save = {}
	for team_id, new_values in new_results.items():
		old_values = last_minute_results.get(team_id)
		if old_values is not None:
			diff = [n - o for n, o in zip(new_values, old_values)]
			stuff_to_save[team_id] = diff
	TeamTrafficStats.efficient_insert(timestamp, stuff_to_save)
	db.session.commit()
	check_for_suspicious_numbers(new_results, last_minute_results)


def check_for_suspicious_numbers(new_results: Dict[int, List[int]], traffic_last_tick: Dict[int, List[int]]):
	from controlserver.logger import log
	from controlserver.models import LogMessage
	for team_id, traffic in traffic_last_tick.items():
		if team_id not in new_results:
			continue
		# check for too much team upload (=VPN ingress)
		new_traffic = new_results[team_id]
		team_upload = new_traffic[9] + new_traffic[13] - traffic[9] - traffic[13]
		if team_upload > 5500000 * TICK_TIME:
			log('traffic-control', f'Team #{team_id} uploaded too much last minute ({team_upload / 1000000:.1f} MB)', level=LogMessage.IMPORTANT)


def main():
	import controlserver.app
	from controlserver.models import Team, db
	redis = config.get_redis_connection()
	fd = open_bpfmap('/sys/fs/bpf/tc/globals/counting_map')
	try:
		if not redis.get('network:state') == b'on':
			print('[-]  VPN is offline, stats paused.')

		loaded_data = None
		if os.path.exists('/tmp/vpn-stats-state.json'):
			with open('/tmp/vpn-stats-state.json', 'r') as f:
				loaded_data = json.loads(f.read())

		if loaded_data and loaded_data['last_minute_tick'] == floor(time.time() / TICK_TIME) * TICK_TIME:
			# We have data from last minute on disk, read it
			last_minute_results = loaded_data['last_minute_results']
			old_vpn_status = loaded_data['old_vpn_status']
			last_minute_tick = loaded_data['last_minute_tick']
			print(f'[OK] Initialized from saved state, {len(last_minute_results)} teams.')

		else:
			# Initially wait for the next minute to start
			wait_for_next_tick(-1)

			# Initially fill the cache
			team_ids = [r[0] for r in db.session.query(Team.id).filter(Team.vpn_last_connect != None).all()]
			last_minute_results = read_team_infos(fd, team_ids)
			old_vpn_status = redis.get('network:state') == b'on'
			last_minute_tick = round(time.time() / TICK_TIME) * TICK_TIME
			print(f'[OK] Initialized, {len(team_ids)} teams.')

		try:
			while True:
				wait_for_next_tick(1)
				t = time.time()
				t_display = datetime.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d %H:%M:%S')

				# 1. Retrieve network status
				print(f'...  Network status at {t_display}')
				team_ids = [r[0] for r in db.session.query(Team.id).filter(Team.vpn_last_connect != None).all()]
				new_results = read_team_infos(fd, team_ids)
				new_vpn_status = redis.get('network:state') == b'on'

				# 2. If network was enabled in between take stats
				if old_vpn_status or new_vpn_status:
					save_difference(round(t / TICK_TIME) * TICK_TIME, new_results, last_minute_results)
					t = time.time() - t
					print(f'[OK] Saved stats of {len(team_ids)} teams in {t:.3f} seconds.')
				else:
					print(f'[-]  VPN is offline, no stats taken.')

				# 3. Save current results as base for next tick
				last_minute_results = new_results
				old_vpn_status = new_vpn_status
				last_minute_tick = round(t / TICK_TIME) * TICK_TIME
		except KeyboardInterrupt:
			with open('/tmp/vpn-stats-state.json', 'w') as f:
				f.write(json.dumps({
					'last_minute_results': last_minute_results,
					'old_vpn_status': old_vpn_status,
					'last_minute_tick': last_minute_tick
				}))
			print('[Terminating]')
	finally:
		os.close(fd)


if __name__ == '__main__':
	main()
