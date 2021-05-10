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
from vpn.vpnlib import *

BASEPORT = 12000
BASEPORT2 = 14000


def build_cloud_server_config(team: Team, server_root: str, secret_root: str):
	# Create secret
	secret_path = join(secret_root, f'team{team.id}')
	os.makedirs(secret_path, exist_ok=True)
	generate_vpn_keys(secret_path)

	# write config
	root = os.path.dirname(os.path.abspath(__file__))
	# root = '/saarctf/vpn'  # for debugging
	serverconfig = f'''
	# OpenVPN Cloud Configuration for Team #{team.id} - "{team.name}"
	proto udp
	port {BASEPORT + team.id}
	dev tun{1000 + team.id}
	dev-type tun

	push "route 10.32.0.0 255.255.0.0"
	push "route 10.33.0.0 255.255.0.0"

	server {config.team_id_to_gateway_ip(team.id)[:-1]}128 255.255.255.128

	duplicate-cn
	client-to-client
	cipher AES-128-GCM
	ncp-disable
	keepalive 15 60
	connect-retry 5 30

	# "secure" version
	#user nobody
	#group nogroup
	#persist-tun

	# version with up/down callbacks
	up-restart

	max-clients 63
	persist-key
	status /var/log/vpn/openvpn-cloud-status-team{team.id}.log

	script-security 2
	up "{root}/on-device-up.sh {team.id}"
	down "{root}/on-cloud.sh on-cloud-down.py {team.id}"
	client-connect "{root}/on-cloud.sh on-cloud-connect.py {team.id}"
	client-disconnect "{root}/on-cloud.sh on-cloud-disconnect.py {team.id}"

	verb 3
	explicit-exit-notify 1
	'''.replace('\n\t', '\n')
	serverconfig += format_vpn_server_keys(secret_path)
	write(join(server_root, f'team{team.id}-cloud.conf'), serverconfig)

	print(f'[OK] Created team #{team.id} server config')


def build_cloud_team_config(team: Team, client_root: str, secret_root: str):
	secret_path = join(secret_root, f'team{team.id}')

	# Create config
	content = f'''
	client
	remote {config.CONFIG['network']['vpn_host']} {BASEPORT + team.id}
	proto udp
	dev game
	dev-type tun

	user nobody
	group nogroup
	nobind
	persist-key
	persist-tun

	remote-cert-tls server
	cipher AES-128-GCM

	# Do not change these two lines!
	shaper 5000000
	keepalive 10 60
	connect-retry 5 30

	verb 3
	'''.replace('\n\t', '\n')
	content += format_vpn_keys(secret_path)

	write(join(client_root, f'client-cloud-team{team.id}.conf'), content)
	# copy over key files
	print(f'[OK] Wrote team #{team.id} client configuration.')


def build_vulnbox_server_config(team: Team, server_root: str, secret_root: str):
	secret_file = join(secret_root, f'team{team.id}.key')

	# Create secret
	if not os.path.exists(secret_file):
		subprocess.check_call(['openvpn', '--genkey', '--secret', secret_file])
		print(f'[OK] Created team #{team.id} secret key.')
	else:
		print(f'...  Team #{team.id} secret key present.')

	# write config
	root = os.path.dirname(os.path.abspath(__file__))
	serverconfig = f'''
	# OpenVPN Configuration for vulnbox of Team #{team.id} - "{team.name}"
	topology p2p
	ifconfig {config.team_id_to_gateway_ip(team.id)} {config.team_id_to_vulnbox_ip(team.id)}
	proto udp
	port {BASEPORT2 + team.id}
	dev tun{2000 + team.id}
	dev-type tun

	# route game network there
	#route {network_to_mask(config.team_id_to_network_range(team.id))}
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
	write(join(server_root, f'team{team.id}-vulnbox.conf'), serverconfig)

	print(f'[OK] Created team #{team.id} server config')


def build_vulnbox_team_config(team: Team, client_root: str, secret_root: str):
	secret_file = join(secret_root, f'team{team.id}.key')

	# Create config
	content = f'''
	topology p2p
	remote {config.CONFIG['network']['vpn_host']} {BASEPORT2 + team.id}
	proto udp
	dev game
	dev-type tun

	ifconfig {config.team_id_to_vulnbox_ip(team.id)} {config.team_id_to_gateway_ip(team.id)}
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

	write(join(client_root, f'client-team{team.id}-vulnbox.conf'), content)
	# copy over key files
	print(f'[OK] Wrote team #{team.id} client configuration.')




def build_systemd_file(teams: List[Team]):
	prefix = '''
	[Unit]
	After=network.target
	'''.replace('\n\t', '\n')

	lines = [f'After=vpn2@team{team.id}-cloud.service\nRequires=vpn2@team{team.id}-cloud.service' for team in teams]
	lines += [f'After=vpn@team{team.id}-vulnbox.service\nRequires=vpn@team{team.id}-vulnbox.service' for team in teams]

	suffix = '''

	[Service]
	Type=oneshot
	RemainAfterExit=true
	ExecStart=/bin/true

	[Install]
	WantedBy=multi-user.target
	'''.replace('\n\t', '\n')
	text = prefix + '\n'.join(lines) + suffix
	write(join(config.VPN_BASE_DIR, 'vpncloud.service'), text)
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
		for i in range(max_id + 1, max_id + prebuild_count + 1):
			teams.append(Team(id=i, name=f'unnamed team #{i}'))
	for team in teams:
		assert '\n' not in team.name
		build_cloud_server_config(team, server_root, secret_root)
		build_cloud_team_config(team, client_root, secret_root)
		build_vulnbox_server_config(team, server_root, secret_root)
		build_vulnbox_team_config(team, client_root, secret_root)
	if teams:
		build_bpf(max(team.id for team in teams))
		build_systemd_file(teams)
	else:
		print('No teams.')

	print('[DONE]')


if __name__ == '__main__':
	main()
