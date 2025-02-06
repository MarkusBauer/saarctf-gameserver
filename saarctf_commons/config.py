"""
This module loads the configuration file and exposes it with a nicer interface.
The configuration file is a yaml/json file, to get the format see the examples in the repository root.

The file is looked up in this order, the first match is loaded:
- $SAARCTF_CONFIG
- $SAARCTF_CONFIG_DIR/config_test.yaml
- $SAARCTF_CONFIG_DIR/config2.yaml
- $SAARCTF_CONFIG_DIR/config.yaml
- $SAARCTF_CONFIG_DIR/config_test.json
- $SAARCTF_CONFIG_DIR/config2.json
- $SAARCTF_CONFIG_DIR/config.json
- <repo-root>/config_test.json
- <repo-root>/config2.json
- <repo-root>/config.json
- <repo-root>/config_test.yaml
- <repo-root>/config2.yaml
- <repo-root>/config.yaml

"""

import binascii
import json
import os
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional, Any

import yaml


@dataclass
class NetworkConfig:
    vulnbox_ip: list[tuple[int, int, int]]
    gateway_ip: list[tuple[int, int, int]]
    testbox_ip: list[tuple[int, int, int]]
    network_ip: list[tuple[int, int, int]]
    vpn_peer_ip: list[tuple[int, int, int]]
    network_size: int

    @classmethod
    def parse_network_def(cls, x: list[Any]) -> list[tuple[int, int, int]]:
        return [tuple(component) if type(component) is list else (1, 1, component) for component in x]  # type: ignore

    @classmethod
    def from_dict(cls, d: dict) -> 'NetworkConfig':
        vulnbox_ip: list[tuple[int, int, int]] = cls.parse_network_def(d['vulnbox_ip'])
        gateway_ip: list[tuple[int, int, int]] = cls.parse_network_def(d['gateway_ip'])
        testbox_ip: list[tuple[int, int, int]] = cls.parse_network_def(d['testbox_ip'])
        network_ip: list[tuple[int, int, int]] = cls.parse_network_def(d['team_range'][:4])
        vpn_peer_ip: list[tuple[int, int, int]] = cls.parse_network_def(d['vpn_peer_ips'])
        network_size: int = d['team_range'][4]
        if network_size not in (8, 16, 24, 32):
            raise ValueError(f'Team network size {network_size} unsupported')
        return NetworkConfig(
            vulnbox_ip=vulnbox_ip,
            gateway_ip=gateway_ip,
            testbox_ip=testbox_ip,
            network_ip=network_ip,
            vpn_peer_ip=vpn_peer_ip,
            network_size=network_size
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            'vulnbox_ip': [list(x) for x in self.vulnbox_ip],
            'gateway_ip': [list(x) for x in self.gateway_ip],
            'testbox_ip': [list(x) for x in self.testbox_ip],
            'vpn_peer_ips': [list(x) for x in self.vpn_peer_ip],
            'team_range': [list(x) for x in self.network_ip] + [self.network_size]
        }

    def team_id_to_vulnbox_ip(self, id: int) -> str:
        """
        Calculates the IP of the vulnbox of a team.
        :param id:
        :return:
        """
        return '.'.join([str(((id // a) % b) + c) for a, b, c in self.vulnbox_ip])

    def team_id_to_gateway_ip(self, id: int) -> str:
        """
        Calculates the IP of the gateway of a team.
        :param id:
        :return:
        """
        return '.'.join([str(((id // a) % b) + c) for a, b, c in self.gateway_ip])

    def team_id_to_testbox_ip(self, id: int) -> str:
        """
        Calculates the IP of the testbox of a team.
        :param id:
        :return:
        """
        global testbox_ip
        return '.'.join([str(((id // a) % b) + c) for a, b, c in self.testbox_ip])

    def team_id_to_network_range(self, id: int) -> str:
        return '.'.join([str(((id // a) % b) + c) for a, b, c in self.network_ip]) + '/' + str(self.network_size)

    def team_id_to_vpn_peers(self, id: int) -> tuple[str, str]:
        vpn_peer_ip_2 = list(self.vpn_peer_ip)
        a, b, c = vpn_peer_ip_2[-1]
        vpn_peer_ip_2[-1] = (a, b, c + 1)
        return (
            '.'.join([str(((id // a) % b) + c) for a, b, c in self.vpn_peer_ip]),
            '.'.join([str(((id // a) % b) + c) for a, b, c in vpn_peer_ip_2])
        )

    def network_ip_to_id(self, ip: str) -> Optional[int]:
        #     id/ai%bi + ci = di
        # <=> id/ai%bi = di - ci
        # <=> id/ai = di-ci + ki*bi
        # <=> id >= (di-ci + ki*bi)*ai  &&  id < (di-ci + ki*bi)*(a1+1)
        # --> Intervals: offset (d-c)*a, size a, interval a*b
        ip_split = ip.split('.')
        a = []
        b = []
        pos = []
        for i in range(self.network_size // 8):
            ai, bi, ci = self.network_ip[i]
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


@dataclass
class ScoringConfig:
    flags_rounds_valid: int = 10
    nop_team_id: int = 1
    off_factor: float = 1.0
    def_factor: float = 1.0
    sla_factor: float = 1.0

    @classmethod
    def from_dict(cls, d: dict) -> 'ScoringConfig':
        return cls(**d)

    def to_dict(self) -> dict:
        return {
            'flags_rounds_valid': self.flags_rounds_valid,
            'nop_team_id': self.nop_team_id,
            'off_factor': self.off_factor,
            'def_factor': self.def_factor,
            'sla_factor': self.sla_factor,
        }


@dataclass
class WireguardSyncConfig:
    api_server: str
    api_token: str
    api_base: str = "/api/router/"
    api_concurrency: int = 1

    @classmethod
    def from_dict(cls, d: dict) -> 'WireguardSyncConfig':
        return cls(**d)

    def to_dict(self) -> dict:
        return {
            'api_server': self.api_server,
            'api_token': self.api_token,
            'api_base': self.api_base,
            'api_concurrency': self.api_concurrency,
        }


@dataclass
class Config:
    basedir: Path
    VPN_BASE_DIR: Path
    CLOUDCONFIG_FILE: Path
    CONFIG: dict[str, Any]
    CONFIG_FILE: Path

    POSTGRES: dict[str, Any]
    POSTGRES_USE_SOCKET: bool
    REDIS: dict
    RABBITMQ: dict | None

    SCOREBOARD_PATH: Path
    VPNBOARD_PATH: Path
    CHECKER_PACKAGES_PATH: Path
    CHECKER_PACKAGES_LFS: Path | None
    SERVICES_PATH: Path
    PATCHES_PATH: Path
    PATCHES_PUBLIC_PATH: Path
    FLOWER_URL: str
    FLOWER_INTERNAL_URL: str
    FLOWER_AJAX_URL: str
    CODER_URL: str | None
    SCOREBOARD_URL: str | None
    GRAFANA_URL: str | None
    PATCHES_URL: str | None

    SECRET_FLAG_KEY: bytes
    DISPATCHER_CHECK_VPN_STATUS: bool
    SCORING: ScoringConfig
    SERVICE_REMOTES: list[str]

    EXTERNAL_TIMER: bool

    NETWORK: NetworkConfig
    WIREGUARD_SYNC: WireguardSyncConfig | None

    @classmethod
    def load_default(cls) -> 'Config':
        if 'SAARCTF_CONFIG_DIR' in os.environ:
            basedir = os.path.abspath(os.environ['SAARCTF_CONFIG_DIR'])
        else:
            basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        possible_config_files = [
            basedir + '/config_test.yaml',
            basedir + '/config_test.json',
            basedir + '/config2.yaml',
            basedir + '/config2.json',
            basedir + '/config.yaml',
            basedir + '/config.json'
        ]
        if 'SAARCTF_CONFIG' in os.environ:
            possible_config_files = [os.environ['SAARCTF_CONFIG']] + possible_config_files
        for configfile in possible_config_files:
            if os.path.exists(configfile):
                return cls.load_from_file(configfile)
        raise Exception('No config file found! Candidates: ' + ', '.join(possible_config_files))

    @classmethod
    def load_from_file(cls, filename: str | Path) -> 'Config':
        with open(filename, 'r') as f:
            if Path(filename).suffix == '.json':
                return cls.from_dict(filename, json.load(f))
            else:
                return cls.from_dict(filename, yaml.safe_load(f))

    @classmethod
    def from_dict(cls, filename: str | Path, CONFIG: dict) -> 'Config':
        cls._clean_comments(CONFIG)

        filename = Path(filename)
        basedir: Path = filename.absolute().parent
        VPN_BASE_DIR = basedir / 'vpn'
        CLOUDCONFIG_FILE = basedir / 'cloud-status.json'

        POSTGRES: dict = CONFIG['databases']['postgres']
        POSTGRES_USE_SOCKET = os.environ.get('SAARCTF_POSTGRES_USE_SOCKET', 'False').lower() == 'true'
        REDIS: dict = CONFIG['databases']['redis']
        RABBITMQ: dict | None = CONFIG['databases']['rabbitmq'] if 'rabbitmq' in CONFIG['databases'] else None

        SCOREBOARD_PATH: Path = Path(CONFIG['scoreboard_path'])
        VPNBOARD_PATH: Path = Path(CONFIG.get('vpnboard_path', SCOREBOARD_PATH))
        CHECKER_PACKAGES_PATH: Path = Path(CONFIG['checker_packages_path'])
        CHECKER_PACKAGES_LFS: Path | None = CHECKER_PACKAGES_PATH / 'lfs' if os.name != 'nt' else None
        PATCHES_PATH: Path = Path(CONFIG.get('patches_path', CHECKER_PACKAGES_PATH / 'patches'))
        PATCHES_PUBLIC_PATH: Path = Path(CONFIG.get('patches_public_path', SCOREBOARD_PATH / 'patches'))
        SERVICES_PATH: Path = Path(CONFIG.get('services_path', CHECKER_PACKAGES_PATH / 'services'))
        FLOWER_URL: str = CONFIG['flower_url']
        FLOWER_INTERNAL_URL: str = CONFIG.get('flower_internal_url', FLOWER_URL)
        FLOWER_AJAX_URL: str = CONFIG.get('flower_ajax_url', FLOWER_URL)
        CODER_URL: Optional[str] = CONFIG.get('coder_url', False) or None
        SCOREBOARD_URL: Optional[str] = CONFIG.get('scoreboard_url', False) or None
        GRAFANA_URL: Optional[str] = CONFIG.get('grafana_url', False) or None
        PATCHES_URL: Optional[str] = CONFIG.get('patches_url', False) or (SCOREBOARD_URL.rstrip('/') + '/patches' if SCOREBOARD_URL else None)

        SECRET_FLAG_KEY: bytes = binascii.unhexlify(CONFIG['secret_flags'])
        DISPATCHER_CHECK_VPN_STATUS: bool = CONFIG.get('dispatcher_check_vpn_status', False)
        SCORING = CONFIG.get('scoring', {})
        if 'nop_team_id' in CONFIG and 'nop_team_id' not in SCORING:
            SCORING['nop_team_id'] = CONFIG['nop_team_id']
        if 'flags_rounds_valid' in CONFIG and 'flags_rounds_valid' not in SCORING:
            SCORING['flags_rounds_valid'] = CONFIG['flags_rounds_valid']

        SERVICE_REMOTES: list[str] = CONFIG.get('service_remotes', [])

        EXTERNAL_TIMER: bool = 'external_timer' in CONFIG and CONFIG['external_timer']

        NETWORK: NetworkConfig = NetworkConfig.from_dict(CONFIG['network'])
        WIREGUARD_SYNC = WireguardSyncConfig.from_dict(CONFIG['wireguard_sync']) if CONFIG.get('wireguard_sync', None) is not None else None

        return Config(
            basedir=basedir,
            VPN_BASE_DIR=VPN_BASE_DIR,
            CLOUDCONFIG_FILE=CLOUDCONFIG_FILE,
            CONFIG=CONFIG,
            CONFIG_FILE=filename,
            POSTGRES=POSTGRES,
            POSTGRES_USE_SOCKET=POSTGRES_USE_SOCKET,
            REDIS=REDIS,
            RABBITMQ=RABBITMQ,
            SCOREBOARD_PATH=SCOREBOARD_PATH,
            VPNBOARD_PATH=VPNBOARD_PATH,
            CHECKER_PACKAGES_PATH=CHECKER_PACKAGES_PATH,
            CHECKER_PACKAGES_LFS=CHECKER_PACKAGES_LFS,
            SERVICES_PATH=SERVICES_PATH,
            PATCHES_PATH=PATCHES_PATH,
            PATCHES_PUBLIC_PATH=PATCHES_PUBLIC_PATH,
            FLOWER_URL=FLOWER_URL,
            FLOWER_INTERNAL_URL=FLOWER_INTERNAL_URL,
            FLOWER_AJAX_URL=FLOWER_AJAX_URL,
            CODER_URL=CODER_URL,
            SCOREBOARD_URL=SCOREBOARD_URL,
            GRAFANA_URL=GRAFANA_URL,
            PATCHES_URL=PATCHES_URL,
            SECRET_FLAG_KEY=SECRET_FLAG_KEY,
            SCORING=ScoringConfig.from_dict(SCORING),
            SERVICE_REMOTES=SERVICE_REMOTES,
            DISPATCHER_CHECK_VPN_STATUS=DISPATCHER_CHECK_VPN_STATUS,
            EXTERNAL_TIMER=EXTERNAL_TIMER,
            NETWORK=NETWORK,
            WIREGUARD_SYNC=WIREGUARD_SYNC,
        )

    def to_dict(self) -> dict[str, Any]:
        return self.CONFIG | {
            'databases': self.CONFIG['databases'] | {
                'postgres': self.POSTGRES,
                'redis': self.REDIS,
                'rabbitmq': self.RABBITMQ,
            },
            'scoreboard_path': str(self.SCOREBOARD_PATH),
            'vpnboard_path': str(self.VPNBOARD_PATH),
            'checker_packages_path': str(self.CHECKER_PACKAGES_PATH),
            'services_path': str(self.SERVICES_PATH),
            'patches_path': str(self.PATCHES_PATH),
            'patches_public_path': str(self.PATCHES_PUBLIC_PATH),
            'flower_url': self.FLOWER_URL,
            'flower_internal_url': self.FLOWER_INTERNAL_URL,
            'flower_ajax_url': self.FLOWER_AJAX_URL,
            'coder_url': self.CODER_URL,
            'scoreboard_url': self.SCOREBOARD_URL,
            'grafana_url': self.GRAFANA_URL,
            'patches_url': self.PATCHES_URL,
            'secret_flags': binascii.hexlify(self.SECRET_FLAG_KEY).decode('ascii'),
            'scoring': self.SCORING.to_dict(),
            'service_remotes': self.SERVICE_REMOTES,
            'dispatcher_check_vpn_status': self.DISPATCHER_CHECK_VPN_STATUS,
            'external_timer': self.EXTERNAL_TIMER,
            'network': self.NETWORK.to_dict(),
            'wireguard_sync': self.WIREGUARD_SYNC.to_dict() if self.WIREGUARD_SYNC else None,
        }

    @classmethod
    def _clean_comments(cls, d: dict) -> None:
        for k, v in list(d.items()):
            if k.startswith("__"):
                del d[k]
            elif type(v) is dict:
                cls._clean_comments(v)

    def postgres_sqlalchemy(self) -> str:
        conn = 'postgresql+psycopg2://'
        if self.POSTGRES['username']:
            conn += self.POSTGRES['username']
            if self.POSTGRES['password']:
                conn += ':' + self.POSTGRES['password']
            conn += '@'
        if self.POSTGRES['server'] and not self.POSTGRES_USE_SOCKET:
            conn += f"{self.POSTGRES['server']}:{self.POSTGRES['port']}"
        return conn + '/' + self.POSTGRES['database']

    def postgres_psycopg2(self) -> str:
        conn = "host='{}' port={} dbname='{}'".format(self.POSTGRES['server'], self.POSTGRES['port'],
                                                      self.POSTGRES['database'])
        if self.POSTGRES['username']:
            conn += " user='{}'".format(self.POSTGRES['username'])
            if self.POSTGRES['password']:
                conn += " password='{}'".format(self.POSTGRES['password'])
        return conn

    # --- Celery connections ---
    # Message broker: RabbitMQ (redis fallback), result storage: Redis

    def celery_redis_url(self) -> str:
        if 'password' in self.REDIS:
            return 'redis://:{}@{}:{}/{}'.format(self.REDIS['password'], self.REDIS['host'], self.REDIS['port'],
                                                 self.REDIS['db'] + 1)
        return 'redis://{}:{}/{}'.format(self.REDIS['host'], self.REDIS['port'], self.REDIS['db'] + 1)

    def celery_rabbitmq_url(self) -> str:
        if not self.RABBITMQ:
            raise ValueError('RabbitMQ not configured')
        return 'amqp://{}:{}@{}:{}/{}'.format(self.RABBITMQ['username'], self.RABBITMQ['password'],
                                              self.RABBITMQ['host'], self.RABBITMQ['port'],
                                              self.RABBITMQ['vhost'])

    def celery_url(self) -> str:
        if self.RABBITMQ:
            return self.celery_rabbitmq_url()
        else:
            return self.celery_redis_url()

    def set_script(self) -> None:
        """We're currently in a script instance, disable some features"""
        self.EXTERNAL_TIMER = False


class CurrentConfigProxy:
    def __getattr__(self, item: str) -> Any:
        global current_config
        if not current_config:
            raise Exception('Config not initialized')
        return getattr(current_config, item)

    def __setattr__(self, key: str, value: Any) -> None:
        global current_config
        if not current_config:
            raise Exception('Config not initialized')
        setattr(current_config, key, value)


config: Config = CurrentConfigProxy()  # type: ignore
current_config: Config = None  # type: ignore


def load_default_config() -> None:
    global current_config
    current_config = Config.load_default()


def load_default_config_file(filename: str | Path, additional: dict[str, Any] | None = None) -> None:
    global current_config
    with open(filename, 'r') as f:
        d: dict[str, Any] = json.loads(f.read())  # type: ignore
    if additional:
        d = d | additional
    current_config = Config.from_dict(filename, d)


if __name__ == '__main__':
    import sys

    # print a config option (can be used in bash scripts etc)
    if sys.argv[1] == 'get':
        load_default_config()
        x: Any = config.CONFIG
        for arg in sys.argv[2:]:
            x = x.get(arg)
        print(str(x))
        sys.exit(0)
    else:
        print('Invalid command')
        sys.exit(1)
