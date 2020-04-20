#!/usr/bin/env python3
import os
import struct
import subprocess
import sys
from os.path import join
from typing import List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.EXTERNAL_TIMER = True

from controlserver.models import Team

"""
ARGUMENTS: none
"""

BASEPORT = 10000


def read(fname: str) -> str:
	with open(fname, 'r') as f:
		return f.read()


def write(fname: str, content: str):
	with open(fname, 'w') as f:
		f.write(content)


def readb(fname: str) -> bytes:
	with open(fname, 'rb') as f:
		return f.read()


def writeb(fname: str, content: bytes):
	with open(fname, 'wb') as f:
		f.write(content)


def network_to_mask(network: str) -> str:
	"""
	"1.2.3.4/16" => "1.2.3.4 255.255.0.0"
	:param network:
	:return:
	"""
	ip, netrange = network.split('/')
	mask_int = int('1' * int(netrange) + '0' * (32 - int(netrange)), 2)
	mask = str(mask_int >> 24) + '.' + str((mask_int >> 16) & 0xff) + '.' + str((mask_int >> 8) & 0xff) + '.' + str(
		mask_int & 0xff)
	return ip + ' ' + mask


def build_team_config(team: Team, client_root: str, secret_root: str):
	secret_file = join(secret_root, f'team{team.id}.key')

	# Create config
	content = f'''
	topology p2p
	remote {config.CONFIG['network']['vpn_host']} {BASEPORT + team.id}
	proto udp
	dev game
	dev-type tun
	
	ifconfig {' '.join(config.team_id_to_vpn_peers(team.id)[::-1])}
	route {network_to_mask(config.CONFIG['network']['game'])}
	
	user nobody
	group nogroup
	nobind
	persist-key
	persist-tun
	
	# Do not change these two lines!
	shaper 5000000
	keepalive 10 60
	connect-retry 5 30
	
	cipher AES-128-CBC
	auth SHA256
	
	verb 3
	
	<secret>
	{read(secret_file)}
	</secret>
	'''.replace('\n\t', '\n')

	write(join(client_root, f'client-team{team.id}.conf'), content)
	# copy over key files
	print(f'[OK] Wrote team #{team.id} client configuration.')


def build_server_config(team: Team, server_root: str, secret_root: str):
	secret_file = join(secret_root, f'team{team.id}.key')

	# Create secret
	if not os.path.exists(secret_file):
		subprocess.check_call(['openvpn', '--genkey', '--secret', secret_file])
		print(f'[OK] Created team #{team.id} secret key.')
	else:
		print(f'...  Team #{team.id} secret key present.')

	# write config
	root = os.path.dirname(os.path.abspath(__file__))
	# root = '/saarctf/vpn'  # for debugging
	serverconfig = f'''
	# OpenVPN Configuration for Team #{team.id} - "{team.name}"
	topology p2p
	ifconfig {' '.join(config.team_id_to_vpn_peers(team.id))}
	proto udp
	port {BASEPORT + team.id}
	dev tun{team.id}
	dev-type tun
	
	# route game network there
	route {network_to_mask(config.team_id_to_network_range(team.id))}
	#push "route {network_to_mask(config.CONFIG['network']['game'])}"
	#TODO avoid loops
	
	cipher AES-128-CBC
	# ncp-ciphers AES-128-GCM
	auth SHA256
	keepalive 15 60
	connect-retry 5 30
	
	# "secure" version
	#user nobody
	#group nogroup
	#persist-tun
	
	# version with up/down callbacks
	route-delay
	up-restart
	up-delay
	
	max-clients 1
	persist-key
	status /var/log/vpn/openvpn-status-team{team.id}.log

	script-security 2
	up "{root}/on-connect.sh {team.id}"
	down "{root}/on-disconnect.sh {team.id}"
	
	verb 3
	explicit-exit-notify 1
	
	<secret>
	{read(secret_file)}
	</secret>
	'''.replace('\n\t', '\n')
	if team.id == 0:
		serverconfig = serverconfig.replace('\nup ', '\n# up ')\
			.replace('\ndown ', '\n# down ').replace('\ndev ', '\ndev orga0  # not ')
	write(join(server_root, f'team{team.id}.conf'), serverconfig)

	print(f'[OK] Created team #{team.id} server config')


def build_bpf(max_team_id: int):
	root = os.path.dirname(os.path.abspath(__file__))
	if max_team_id > 511:
		raise Exception('You hit the limit in bpf/traffic_stats.c. Please update and recompile!')
	bpfcode = readb(os.path.join(root, 'bpf', 'traffic_stats.o'))
	old = struct.pack('<I', 0xdeadbeef)
	if bpfcode.count(old) != 2:
		print('contant found:', bpfcode.count(old))
		assert bpfcode.count(old) == 2
	for team_id in range(1, max_team_id + 11):
		new = struct.pack('<I', team_id)
		team_bpfcode = bpfcode.replace(old, new)
		writeb(os.path.join(root, 'bpf', f'traffic_stats_team{team_id}.o'), team_bpfcode)
	print('[OK] BPF files produced.')


def build_systemd_file(teams: List[Team]):
	prefix = '''
	[Unit]
	After=network.target
	After=vpn@team0.service
	Requires=vpn@team0.service
	'''.replace('\n\t', '\n')

	lines = [f'After=vpn@team{team.id}.service\nRequires=vpn@team{team.id}.service' for team in teams]

	suffix = '''
	
	[Service]
	Type=oneshot
	RemainAfterExit=true
	ExecStart=/bin/true
	
	[Install]
	WantedBy=multi-user.target
	'''.replace('\n\t', '\n')
	text = prefix + '\n'.join(lines) + suffix
	with open(join(config.VPN_BASE_DIR, 'vpn.service'), 'w') as f:
		f.write(text)
	print('[OK] Systemd service generated.')


def main():
	import controlserver.app
	server_root = join(config.VPN_BASE_DIR, 'config-server')  # output: server config
	client_root = join(config.VPN_BASE_DIR, 'config-client')  # output: team config
	secret_root = join(config.VPN_BASE_DIR, 'secrets')
	os.makedirs(server_root, exist_ok=True)
	os.makedirs(client_root, exist_ok=True)
	os.makedirs(secret_root, exist_ok=True)
	print(f'SETUP: rm -r /etc/openvpn/server && ln -s "{server_root}" /etc/openvpn/server\n\n')

	teams = list(Team.query.order_by(Team.id).all())
	if len(sys.argv) > 1:
		prebuild_count = int(sys.argv[1])
		max_id = max(team.id for team in teams)
		for i in range(max_id+1, max_id+prebuild_count+1):
			teams.append(Team(id=i, name=f'unnamed team #{i}'))
	for team in teams:
		assert '\n' not in team.name
		build_server_config(team, server_root, secret_root)
		build_team_config(team, client_root, secret_root)
	if teams:
		build_bpf(max(team.id for team in teams))
		build_systemd_file(teams)
	else:
		print('No teams.')
	# build a config for the orgas
	orga = Team(id=0, name='orga')
	build_server_config(orga, server_root, secret_root)
	build_team_config(orga, client_root, secret_root)

	print('[DONE]')


if __name__ == '__main__':
	main()
