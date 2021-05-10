"""
This module loads the configuration file and exposes it with a nicer interface.
The configuration file is a json file, to get the format see the examples in the repository root.

The file is looked up in this order, the first match is loaded:
- $SAARCTF_CONFIG
- $SAARCTF_CONFIG_DIR/config_test.json
- $SAARCTF_CONFIG_DIR/config2.json
- $SAARCTF_CONFIG_DIR/config.json
- <repo-root>/config_test.json
- <repo-root>/config2.json
- <repo-root>/config.json

"""

import binascii
import json
import os
from typing import Dict, Optional, Tuple, List, Any
import redis

if 'SAARCTF_CONFIG_DIR' in os.environ:
	basedir = os.path.abspath(os.environ['SAARCTF_CONFIG_DIR'])
else:
	basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
possible_config_files = [
	basedir + '/config_test.json',
	basedir + '/config2.json',
	basedir + '/config.json'
]
if 'SAARCTF_CONFIG' in os.environ:
	possible_config_files = [os.environ['SAARCTF_CONFIG']] + possible_config_files

VPN_BASE_DIR = os.path.join(basedir, 'vpn')
CLOUDCONFIG_FILE = os.path.join(basedir, 'cloud-status.json')

# Load configuration file
CONFIG: Dict[str, Any] = {}
CONFIG_FILE = None
for configfile in possible_config_files:
	if os.path.exists(configfile):
		with open(configfile, 'rb') as f:
			CONFIG = json.loads(f.read())
			CONFIG_FILE = configfile
		break
if not CONFIG:
	raise Exception('No config file found! Candidates: ' + ', '.join(possible_config_files))


def config_clean_comments(d: Dict):
	for k, v in list(d.items()):
		if k.startswith("__"):
			del d[k]
		elif type(v) is dict:
			config_clean_comments(v)


config_clean_comments(CONFIG)

POSTGRES: Dict = CONFIG['databases']['postgres']
POSTGRES_USE_SOCKET = os.environ.get('SAARCTF_POSTGRES_USE_SOCKET', 'False').lower() == 'true'
REDIS: Dict = CONFIG['databases']['redis']
RABBITMQ: Dict = CONFIG['databases']['rabbitmq'] if 'rabbitmq' in CONFIG['databases'] else None

SCOREBOARD_PATH: str = CONFIG['scoreboard_path']
CHECKER_PACKAGES_PATH: str = CONFIG['checker_packages_path'].rstrip('/')
CHECKER_PACKAGES_LFS: Optional[str] = CHECKER_PACKAGES_PATH + '/lfs' if os.name != 'nt' else None
FLOWER_URL: str = CONFIG['flower_url']
FLOWER_INTERNAL_URL: str = CONFIG.get('flower_internal_url', FLOWER_URL)
FLOWER_AJAX_URL: str = CONFIG.get('flower_ajax_url', FLOWER_URL)
CODER_URL: Optional[str] = CONFIG.get('coder_url', False) or None
SCOREBOARD_URL: Optional[str] = CONFIG.get('scoreboard_url', False) or None
GRAFANA_URL: Optional[str] = CONFIG.get('grafana_url', False) or None

SECRET_FLAG_KEY: bytes = binascii.unhexlify(CONFIG['secret_flags'])
FLAG_ROUNDS_VALID: int = CONFIG['flags_rounds_valid']
NOP_TEAM_ID: int = CONFIG['nop_team_id']

EXTERNAL_TIMER: bool = 'external_timer' in CONFIG and CONFIG['external_timer']

# --- IPs ---

vulnbox_ip: List[Tuple[int, int, int]] = \
	[tuple(component) if type(component) is list else (1, 1, component) for component in CONFIG['network']['vulnbox_ip']]  # type: ignore
gateway_ip: List[Tuple[int, int, int]] = \
	[tuple(component) if type(component) is list else (1, 1, component) for component in CONFIG['network']['gateway_ip']]  # type: ignore
testbox_ip: List[Tuple[int, int, int]] = \
	[tuple(component) if type(component) is list else (1, 1, component) for component in CONFIG['network']['testbox_ip']]  # type: ignore
network_ip: List[Tuple[int, int, int]] = \
	[tuple(component) if type(component) is list else (1, 1, component) for component in CONFIG['network']['team_range'][:4]]  # type: ignore
vpn_peer_ip: List[Tuple[int, int, int]] = \
	[tuple(component) if type(component) is list else (1, 1, component) for component in CONFIG['network']['vpn_peer_ips']]  # type: ignore
network_size = CONFIG['network']['team_range'][4]
assert network_size in (8, 16, 24, 32), 'Team network size unsupported'


def team_id_to_vulnbox_ip(id: int) -> str:
	"""
	Calculates the IP of the vulnbox of a team.
	:param id:
	:return:
	"""
	global vulnbox_ip
	return '.'.join([str(((id // a) % b) + c) for a, b, c in vulnbox_ip])


def team_id_to_gateway_ip(id: int) -> str:
	"""
	Calculates the IP of the gateway of a team.
	:param id:
	:return:
	"""
	global gateway_ip
	return '.'.join([str(((id // a) % b) + c) for a, b, c in gateway_ip])


def team_id_to_testbox_ip(id: int) -> str:
	"""
	Calculates the IP of the testbox of a team.
	:param id:
	:return:
	"""
	global testbox_ip
	return '.'.join([str(((id // a) % b) + c) for a, b, c in testbox_ip])


def team_id_to_network_range(id: int) -> str:
	global network_ip, network_size
	return '.'.join([str(((id // a) % b) + c) for a, b, c in network_ip]) + '/' + str(network_size)


def team_id_to_vpn_peers(id: int) -> Tuple[str, str]:
	global vpn_peer_ip
	vpn_peer_ip_2 = list(vpn_peer_ip)
	a, b, c = vpn_peer_ip_2[-1]
	vpn_peer_ip_2[-1] = (a, b, c + 1)
	return (
		'.'.join([str(((id // a) % b) + c) for a, b, c in vpn_peer_ip]),
		'.'.join([str(((id // a) % b) + c) for a, b, c in vpn_peer_ip_2])
	)


def network_ip_to_id(ip: str) -> Optional[int]:
	#     id/ai%bi + ci = di
	# <=> id/ai%bi = di - ci
	# <=> id/ai = di-ci + ki*bi
	# <=> id >= (di-ci + ki*bi)*ai  &&  id < (di-ci + ki*bi)*(a1+1)
	# --> Intervals: offset (d-c)*a, size a, interval a*b
	ip_split = ip.split('.')
	a = []
	b = []
	pos = []
	for i in range(network_size // 8):
		ai, bi, ci = network_ip[i]
		if bi > 1:
			a.append(ai)
			b.append(bi)
			pos.append((int(ip_split[i]) - ci) * ai)
	while True:
		smallest = max(pos)
		largest = min((pos_i + a_i for pos_i, a_i in zip(pos, a)))
		if smallest >= 0xffff:
			return None
		if smallest < largest:
			return smallest
		for i in range(len(pos)):
			while pos[i] + a[i] <= smallest:
				pos[i] += a[i] * b[i]


# --- Postgresql ---

def postgres_sqlalchemy():
	global POSTGRES_USE_SOCKET
	conn = 'postgresql+psycopg2://'
	if POSTGRES['username']:
		conn += POSTGRES['username']
		if POSTGRES['password']:
			conn += ':' + POSTGRES['password']
		conn += '@'
	if POSTGRES['server'] and not POSTGRES_USE_SOCKET:
		conn += f"{POSTGRES['server']}:{POSTGRES['port']}"
	return conn + '/' + POSTGRES['database']


def postgres_psycopg2():
	conn = "host='{}' port={} dbname='{}'".format(POSTGRES['server'], POSTGRES['port'], POSTGRES['database'])
	if POSTGRES['username']:
		conn += " user='{}'".format(POSTGRES['username'])
		if POSTGRES['password']:
			conn += " password='{}'".format(POSTGRES['password'])
	return conn


# --- Celery connections ---
# Message broker: RabbitMQ (redis fallback), result storage: Redis

def celery_redis_url() -> str:
	if 'password' in REDIS:
		return 'redis://:{}@{}:{}/{}'.format(REDIS['password'], REDIS['host'], REDIS['port'], REDIS['db'] + 1)
	return 'redis://{}:{}/{}'.format(REDIS['host'], REDIS['port'], REDIS['db'] + 1)


def celery_rabbitmq_url() -> str:
	return 'amqp://{}:{}@{}:{}/{}'.format(RABBITMQ['username'], RABBITMQ['password'], RABBITMQ['host'], RABBITMQ['port'], RABBITMQ['vhost'])


def celery_url() -> str:
	if RABBITMQ:
		return celery_rabbitmq_url()
	else:
		return celery_redis_url()


# --- REDIS ---
# (we want our redis connections with client names, that's why we override the default connection class)

class NamedRedisConnection(redis.Connection):
	name = ''

	def on_connect(self):
		redis.Connection.on_connect(self)
		if self.name:
			self.send_command("CLIENT SETNAME", self.name.replace(' ', '_'))
			self.read_response()


def set_redis_clientname(name: str, overwrite: bool = False):
	"""
	Set the name of all future redis connections.
	:param name:
	:param overwrite: Overwrite an already existing name?
	:return:
	"""
	if overwrite or not NamedRedisConnection.name:
		NamedRedisConnection.name = name


redis_default_connection_pool = None


def get_redis_connection() -> redis.StrictRedis:
	"""
	:return: A new Redis connection (possibly from a connection pool). Name is already set.
	"""
	global redis_default_connection_pool
	if not redis_default_connection_pool:
		redis_default_connection_pool = redis.ConnectionPool(connection_class=NamedRedisConnection, **REDIS)
	r = redis.StrictRedis(connection_pool=redis_default_connection_pool)
	return r


if __name__ == '__main__':
	import sys

	# print a config option (can be used in bash scripts etc)
	if sys.argv[1] == 'get':
		x: Any = CONFIG
		for arg in sys.argv[2:]:
			x = x.get(arg)
		print(str(x))
		sys.exit(0)
	else:
		print('Invalid command')
		sys.exit(1)
