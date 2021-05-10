#!/usr/bin/env python3
import os
import subprocess
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vpn.vpnlib import generate_vpn_keys, format_vpn_keys
from saarctf_commons import config

server_config_file = os.path.join(config.VPN_BASE_DIR, 'config-server', 'orga-multi.conf')
client_config_file = os.path.join(config.VPN_BASE_DIR, 'config-client', 'orga-multi.conf')
orga_secrets_dir = os.path.join(config.VPN_BASE_DIR, 'orga-secrets')


def configure_vpnserver():
	generate_vpn_keys(orga_secrets_dir)
	server_config = f'''
	port 1194
	proto udp
	dev orga1
	dev-type tun

	server {config.team_id_to_gateway_ip(0)[:-1]}128 255.255.255.128
	keepalive 10 120

	push "route 10.32.0.0 255.255.0.0"
	push "route 10.33.0.0 255.255.0.0"

	ca {orga_secrets_dir}/pki/ca.crt
	cert {orga_secrets_dir}/pki/issued/server.crt
	key {orga_secrets_dir}/pki/private/server.key
	dh {orga_secrets_dir}/pki/dh.pem
	tls-auth {orga_secrets_dir}/pki/ta.key
	duplicate-cn
	cipher AES-128-GCM

	user nobody
	group nogroup
	persist-key
	persist-tun
	status /var/log/vpn/openvpn-status-orga-multi.log
	verb 3
	explicit-exit-notify 1
	'''.replace('\n\t', '\n')
	with open(server_config_file, 'w') as f:
		f.write(server_config)

	client_config = f'''
	remote {config.CONFIG["network"]["vpn_host"]} 1194
	client
	dev tun
	proto udp
	nobind

	remote-cert-tls server
	cipher AES-128-GCM

	user nobody
	group nogroup
	persist-key
	persist-tun
	'''.replace('\n\t', '\n')
	client_config += format_vpn_keys(orga_secrets_dir)
	with open(client_config_file, 'w') as f:
		f.write(client_config)


if __name__ == '__main__':
	os.makedirs(orga_secrets_dir, exist_ok=True)
	configure_vpnserver()
	print('Configurations generated:')
	print(f'  server: {server_config_file}')
	print(f'  client: {client_config_file}')
	print('Activation: systemctl start vpn@orga-multi && systemctl enable vpn@orga-multi')
