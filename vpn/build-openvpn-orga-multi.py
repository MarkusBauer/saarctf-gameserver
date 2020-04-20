#!/usr/bin/env python3
import os
import subprocess
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

EASYRSA_BINARY = '/usr/share/easy-rsa/easyrsa'

server_config_file = os.path.join(config.VPN_BASE_DIR, 'config-server', 'orga-multi.conf')
client_config_file = os.path.join(config.VPN_BASE_DIR, 'config-client', 'orga-multi.conf')
orga_secrets_dir = os.path.join(config.VPN_BASE_DIR, 'orga-secrets')


def generate_vpn_keys():
	path = os.path.join(orga_secrets_dir, 'pki')
	if os.path.exists(os.path.join(path, 'ta.key')):
		print('[.] VPN keys already present')
		return
	env = dict(os.environ.items())
	env['EASYRSA_BATCH'] = '1'
	subprocess.check_call([EASYRSA_BINARY, 'init-pki'], env=env, cwd=orga_secrets_dir)
	subprocess.check_call([EASYRSA_BINARY, 'build-ca', 'nopass'], env=env, cwd=orga_secrets_dir)
	subprocess.check_call([EASYRSA_BINARY, 'gen-req', 'server', 'nopass'], env=env, cwd=orga_secrets_dir)
	subprocess.check_call([EASYRSA_BINARY, 'gen-req', 'TeamMember', 'nopass'], env=env, cwd=orga_secrets_dir)
	subprocess.check_call([EASYRSA_BINARY, 'sign-req', 'server', 'server'], env=env, cwd=orga_secrets_dir)
	subprocess.check_call([EASYRSA_BINARY, 'sign-req', 'client', 'TeamMember'], env=env, cwd=orga_secrets_dir)
	subprocess.check_call([EASYRSA_BINARY, 'gen-dh'], env=env, cwd=orga_secrets_dir)
	subprocess.check_call(['openvpn', '--genkey', '--secret', 'ta.key'], cwd=path)
	print('[*] VPN keys have been generated.')


def configure_vpnserver():
	generate_vpn_keys()
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
	included_files = {
		'ca': orga_secrets_dir + '/pki/ca.crt',
		'cert': orga_secrets_dir + '/pki/issued/TeamMember.crt',
		'key': orga_secrets_dir + '/pki/private/TeamMember.key',
		'tls-auth': orga_secrets_dir + '/pki/ta.key'
	}
	for name, fname in included_files.items():
		client_config += f'\n<{name}>\n'
		with open(fname, 'r') as f:
			client_config += f.read()
		client_config += f'\n</{name}>\n'
	with open(client_config_file, 'w') as f:
		f.write(client_config)


if __name__ == '__main__':
	os.makedirs(orga_secrets_dir, exist_ok=True)
	configure_vpnserver()
	print('Configurations generated:')
	print(f'  server: {server_config_file}')
	print(f'  client: {client_config_file}')
	print('Activation: systemctl start vpn@orga-multi && systemctl enable vpn@orga-multi')
