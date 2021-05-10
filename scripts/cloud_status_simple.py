import base64
import json
import os
import sys
from hashlib import sha256
from typing import Optional, List, Iterable, Dict

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config
from controlserver.models import Team

config.EXTERNAL_TIMER = True

"""
Generates a status json file for all teams registered.
Requires access to the VPN configuration files (cloud style). 
ARGUMENTS: [--create-only] [--reset] kind
"""


def first(x: Iterable):
	for y in x:
		return y
	return None


def generate_team_password(team_id: int) -> str:
	if config.CONFIG_FILE:
		folder = os.path.basename(os.path.dirname(config.CONFIG_FILE))  # for example "2020" or "test"
	else:
		folder = 'none'
	secret = f'NlY676oaZDABDmkOP3oxTBS8OwEoNL39fLZXb61|{folder}|{team_id}'
	password = base64.b32encode(sha256(secret.encode()).digest()).decode()[:12]
	return password


def simple_cloud_status(kinds: List[str], reset: bool, running: bool):
	if len(kinds) == 0:
		print(f'USAGE: {sys.argv[0]} [--create-only] [--reset] kind ...')
		sys.exit(1)
	import controlserver.app

	# load old status
	status: Dict[str, List[Dict]] = {'vms': []}
	if not reset:
		try:
			with open(config.CLOUDCONFIG_FILE, 'r') as f:
				status = json.loads(f.read())
		except:
			print('[!] Could not load ' + config.CLOUDCONFIG_FILE)

	for kind in kinds:
		teams = Team.query.order_by(Team.id).all()
		for team in teams:
			with open(os.path.join(config.VPN_BASE_DIR, 'config-client', f'client-team{team.id}-vulnbox.conf'), 'r') as f:
				vpnconfig = f.read()
			vm = first(vm for vm in status['vms'] if vm['kind'] == kind and vm['team'] == team.id)
			if not vm:
				vm = {"team": team.id, "kind": kind}
				status['vms'].append(vm)
			vm['root_password'] = generate_team_password(team.id)
			vm['files'] = {"/etc/openvpn/vulnbox.conf": {"content": vpnconfig, "permission": "0600", "owner": "root:root"}}
			vm['status'] = 'RUNNING' if running else 'STOPPED'

	with open(config.CLOUDCONFIG_FILE, 'w') as f:
		f.write(json.dumps(status))
	print(f'[*] Wrote {config.CLOUDCONFIG_FILE}, containing {len(status["vms"])} VMs')


if __name__ == '__main__':
	kinds = [k for k in sys.argv[1:] if not k.startswith('-')]
	simple_cloud_status(kinds, reset='--reset' in sys.argv, running='--create-only' not in sys.argv)
