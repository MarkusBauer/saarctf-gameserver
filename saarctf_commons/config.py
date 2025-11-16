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
from dataclasses import dataclass, field, fields
from os import environ
from pathlib import Path
from typing import Any, Optional, Self

import yaml


def opt_path(s: str | None) -> Path | None:
    if s:
        return Path(s)
    return None


@dataclass
class ConfigSection:
    @classmethod
    def from_dict(cls, d: dict) -> Self:
        for f in fields(cls):
            if f.name in d and issubclass(f.type, ConfigSection):  # type: ignore
                d[f.name] = f.type.from_dict(d[f.name])  # type: ignore
        return cls(**d)

    def to_dict(self) -> dict[str, Any]:
        d = {}
        for f in fields(self):
            if issubclass(f.type, ConfigSection):  # type: ignore
                d[f.name] = getattr(self, f.name).to_dict()
            else:
                d[f.name] = getattr(self, f.name)
        return d


@dataclass
class NetworkConfig(ConfigSection):
    vulnbox_ip: list[tuple[int, int, int]]
    gateway_ip: list[tuple[int, int, int]]
    testbox_ip: list[tuple[int, int, int]]
    network_ip: list[tuple[int, int, int]]
    vpn_peer_ip: list[tuple[int, int, int]]
    network_size: int
    gameserver_ip: str | None = None

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
        gameserver_ip = d.get("gameserver_ip", None)
        return NetworkConfig(
            vulnbox_ip=vulnbox_ip,
            gateway_ip=gateway_ip,
            testbox_ip=testbox_ip,
            network_ip=network_ip,
            vpn_peer_ip=vpn_peer_ip,
            network_size=network_size,
            gameserver_ip=gameserver_ip,
        )

    def to_dict(self) -> dict[str, Any]:
        d = {
            "vulnbox_ip": [list(x) for x in self.vulnbox_ip],
            "gateway_ip": [list(x) for x in self.gateway_ip],
            "testbox_ip": [list(x) for x in self.testbox_ip],
            "vpn_peer_ips": [list(x) for x in self.vpn_peer_ip],
            "team_range": [list(x) for x in self.network_ip] + [self.network_size],
        }
        if self.gameserver_ip:
            d["gameserver_ip"] = self.gameserver_ip
        return d

    def team_id_to_vulnbox_ip(self, team_id: int) -> str:
        """
        Calculates the IP of the vulnbox of a team.
        :param id:
        :return:
        """
        return ".".join([str(((team_id // a) % b) + c) for a, b, c in self.vulnbox_ip])

    def team_id_to_gateway_ip(self, team_id: int) -> str:
        """
        Calculates the IP of the gateway of a team.
        :param id:
        :return:
        """
        return ".".join([str(((team_id // a) % b) + c) for a, b, c in self.gateway_ip])

    def team_id_to_testbox_ip(self, team_id: int) -> str:
        """
        Calculates the IP of the testbox of a team.
        :param id:
        :return:
        """
        return ".".join([str(((team_id // a) % b) + c) for a, b, c in self.testbox_ip])

    def team_id_to_network_range(self, team_id: int) -> str:
        return '.'.join([str(((team_id // a) % b) + c) for a, b, c in self.network_ip]) + "/" + str(self.network_size)

    def team_id_to_vpn_peers(self, team_id: int) -> tuple[str, str]:
        vpn_peer_ip_2 = list(self.vpn_peer_ip)
        a, b, c = vpn_peer_ip_2[-1]
        vpn_peer_ip_2[-1] = (a, b, c + 1)
        return (
            ".".join([str(((team_id // a) % b) + c) for a, b, c in self.vpn_peer_ip]),
            ".".join([str(((team_id // a) % b) + c) for a, b, c in vpn_peer_ip_2]),
        )

    def network_ip_to_id(self, ip: str) -> Optional[int]:
        #     id/ai%bi + ci = di
        # <=> id/ai%bi = di - ci
        # <=> id/ai = di-ci + ki*bi
        # <=> id >= (di-ci + ki*bi)*ai  &&  id < (di-ci + ki*bi)*(a1+1)
        # --> Intervals: offset (d-c)*a, size a, interval a*b
        ip_split = ip.split(".")
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
            if smallest >= 0xFFFF:
                return None
            if smallest < largest:
                return smallest
            for i in range(len(pos)):
                while pos[i] + a[i] <= smallest:
                    pos[i] += a[i] * b[i]


@dataclass
class ScoringConfig(ConfigSection):
    flags_rounds_valid: int = 10
    nop_team_id: int = 1
    off_factor: float = 1.0
    def_factor: float = 1.0
    sla_factor: float = 1.0
    # custom algorithms name, if necessary
    algorithm: str = "saarctf:SaarctfScoreAlgorithm"
    firstblood_algorithm: str = "firstblood:DefaultFirstBloodAlgorithm"
    # additional data for custom algorithms
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> "ScoringConfig":
        field_names = {f.name for f in fields(cls)}
        params = {k: v for k, v in d.items() if k in field_names}
        params["data"] = {k: v for k, v in d.items() if k not in field_names}
        return cls(**params)

    def to_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "firstblood_algorithm": self.firstblood_algorithm,
            "flags_rounds_valid": self.flags_rounds_valid,
            "nop_team_id": self.nop_team_id,
            "off_factor": self.off_factor,
            "def_factor": self.def_factor,
            "sla_factor": self.sla_factor,
        } | self.data


@dataclass
class EnoRunnerConfig(ConfigSection):
    check_past_ticks: int = 5
    timeout: float = 15


@dataclass
class RunnerConfig(ConfigSection):
    dispatcher: str = "dispatcher:CeleryDispatcher"
    eno: EnoRunnerConfig = field(default_factory=EnoRunnerConfig)


@dataclass
class WireguardSyncConfig(ConfigSection):
    api_server: str
    api_token: str
    api_base: str = "/api/router/"
    api_concurrency: int = 1


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
    METRICS: dict[str, Any]

    TICK_DURATION_DEFAULT: int
    SCOREBOARD_PATH: Path
    SCOREBOARD_PATH_INTERNAL: Path | None
    VPNBOARD_PATH: Path
    CHECKER_PACKAGES_PATH: Path
    CHECKER_PACKAGES_LFS: Path | None
    SERVICES_PATH: Path
    PATCHES_PATH: Path
    PATCHES_PUBLIC_PATH: Path | None
    FLOWER_URL: str
    FLOWER_INTERNAL_URL: str
    FLOWER_AJAX_URL: str
    CODER_URL: str | None
    SCOREBOARD_URL: str | None
    GRAFANA_URL: str | None
    PATCHES_URL: str | None

    SECRET_FLAG_KEY: bytes
    FLAG_PREFIX: str
    DISPATCHER_CHECK_VPN_STATUS: bool
    SCORING: ScoringConfig
    SERVICE_REMOTES: list[str]

    EXTERNAL_TIMER: bool

    NETWORK: NetworkConfig
    WIREGUARD_SYNC: WireguardSyncConfig | None
    RUNNER: RunnerConfig

    CTFROUTE_NAMESPACE: str
    SCOREBOARD_FREEZE: int | None

    def interpolate_env(self) -> Self:
        """
        Environment variables have precedence over config.yaml entries.
        """
        if "RABBITMQ_HOST" in environ and not self.RABBITMQ:
            self.RABBITMQ = {}
        for d, k, e in [
            (self.POSTGRES, "server", "POSTGRES_SERVER"),
            (self.POSTGRES, "port", "POSTGRES_PORT"),
            (self.POSTGRES, "username", "POSTGRES_USERNAME"),
            (self.POSTGRES, "password", "POSTGRES_PASSWORD"),
            (self.POSTGRES, "database", "POSTGRES_DATABASE"),
            (self.REDIS, "host", "REDIS_HOST"),
            (self.REDIS, "port", "REDIS_PORT"),
            (self.REDIS, "db", "REDIS_DB"),
            (self.REDIS, "password", "REDIS_PASSWORD"),
            (self.RABBITMQ, "host", "RABBITMQ_HOST"),
            (self.RABBITMQ, "vhost", "RABBITMQ_VHOST"),
            (self.RABBITMQ, "port", "RABBITMQ_PORT"),
            (self.RABBITMQ, "username", "RABBITMQ_USERNAME"),
            (self.RABBITMQ, "password", "RABBITMQ_PASSWORD"),
            (self.METRICS, "server", "METRICS_SERVER"),
            (self.METRICS, "port", "METRICS_PORT"),
            (self.METRICS, "username", "METRICS_USERNAME"),
            (self.METRICS, "password", "METRICS_PASSWORD"),
            (self.METRICS, "database", "METRICS_DATABASE"),
        ]:
            if e in environ:
                d[k] = environ[e]  # type: ignore

        if isinstance(self.REDIS["db"], str):
            self.REDIS["db"] = int(self.REDIS["db"])
        if "SECRET_FLAG_KEY" in environ:
            self.SECRET_FLAG_KEY: bytes = binascii.unhexlify(environ["SECRET_FLAG_KEY"])
        if "SCOREBOARD_PATH" in environ:
            self.SCOREBOARD_PATH = Path(environ["SCOREBOARD_PATH"])
        if "SCOREBOARD_PATH_INTERNAL" in environ:
            self.SCOREBOARD_PATH_INTERNAL = Path(environ["SCOREBOARD_PATH_INTERNAL"])
        return self

    @classmethod
    def load_default(cls) -> 'Config':
        if "CONFIG_FILE" in os.environ:  # ECSC stuff, don't ask
            config_file = Path(os.environ["CONFIG_FILE"])
            if not config_file.exists():
                raise ValueError(f"{config_file} does not exist")
            return cls.load_from_file(config_file)
        if 'SAARCTF_CONFIG_DIR' in os.environ:
            basedir = Path(os.environ['SAARCTF_CONFIG_DIR']).absolute()
        else:
            basedir = Path(__file__).absolute().parent.parent
        possible_config_files = [
            basedir / 'config_test.yaml',
            basedir / 'config_test.json',
            basedir / 'config2.yaml',
            basedir / 'config2.json',
            basedir / 'config.yaml',
            basedir / 'config.json'
        ]
        if 'SAARCTF_CONFIG' in os.environ:
            possible_config_files = [Path(os.environ['SAARCTF_CONFIG'])] + possible_config_files
        for configfile in possible_config_files:
            if configfile.exists():
                return cls.load_from_file(configfile)
        raise Exception('No config file found! Candidates: ' + ', '.join(map(str, possible_config_files)))

    @classmethod
    def load_from_file(cls, filename: Path, interpolate_env: bool = True) -> Self:
        with filename.open() as f:
            if filename.suffix == ".json":
                return cls.from_dict(filename, json.load(f), interpolate_env=interpolate_env)
            return cls.from_dict(filename, yaml.safe_load(f), interpolate_env=interpolate_env)

    @classmethod
    def from_dict(cls, filename: Path, initial_config: dict, interpolate_env: bool = True) -> Self:
        cls._clean_comments(initial_config)

        basedir: Path = filename.absolute().parent
        vpn_base_dir = basedir / "vpn"
        cloudconfig_file = basedir / "cloud-status.json"

        postgres: dict = initial_config["databases"]["postgres"] or {}
        postgres_use_socket = os.environ.get("SAARCTF_POSTGRES_USE_SOCKET", "False").lower() == "true"
        redis: dict = initial_config["databases"]["redis"] or {}
        rabbitmq: dict | None = initial_config["databases"]["rabbitmq"] if "rabbitmq" in initial_config["databases"] else None
        metrics: dict = postgres | {"database": postgres["database"] + "_metrics"} | initial_config["databases"].get("metrics", {})

        tick_duration_default = int(initial_config.get("tick_duration_default", 120))
        scoreboard_path: Path = Path(initial_config.get("scoreboard_path", ""))
        scoreboard_path_internal: Path | None = opt_path(initial_config.get("scoreboard_path_internal"))
        vpnboard_path: Path = Path(initial_config.get("vpnboard_path", scoreboard_path))  # type: ignore
        checker_packages_path: Path = Path(initial_config["checker_packages_path"])
        checker_packages_lfs: Path | None = checker_packages_path / "lfs" if os.name != "nt" else None
        patches_path: Path = Path(initial_config.get("patches_path", checker_packages_path / "patches"))
        patches_public_path: Path | None = opt_path(initial_config.get("patches_public_path"))
        services_path: Path = Path(initial_config.get("services_path", checker_packages_path / "services"))
        flower_url: str = initial_config.get("flower_url", "")
        flower_internal_url: str = initial_config.get("flower_internal_url", flower_url)
        flower_ajax_url: str = initial_config.get("flower_ajax_url", flower_url)
        coder_url: Optional[str] = initial_config.get("coder_url", False) or None
        scoreboard_url: Optional[str] = initial_config.get("scoreboard_url", False) or None
        grafana_url: Optional[str] = initial_config.get("grafana_url", False) or None
        patches_url: Optional[str] = initial_config.get("patches_url", False) or scoreboard_url.rstrip("/") + "/patches" if scoreboard_url else None

        flag_prefix: str = initial_config.get("flag_prefix", "SAAR")
        secret_flag_key: bytes = binascii.unhexlify(initial_config.get("secret_flags", ""))
        dispatcher_check_vpn_status: bool = initial_config.get("dispatcher_check_vpn_status", False)
        scoring = initial_config.get("scoring", {})
        if "nop_team_id" in initial_config and "nop_team_id" not in scoring:
            scoring["nop_team_id"] = initial_config["nop_team_id"]
        if "flags_rounds_valid" in initial_config and "flags_rounds_valid" not in scoring:
            scoring["flags_rounds_valid"] = initial_config["flags_rounds_valid"]

        service_remotes: list[str] = initial_config.get("service_remotes", [])

        external_timer: bool = "external_timer" in initial_config and initial_config["external_timer"]

        network: NetworkConfig = NetworkConfig.from_dict(initial_config["network"])
        wireguard_sync = (
            WireguardSyncConfig.from_dict(initial_config["wireguard_sync"])
            if initial_config.get("wireguard_sync", None) is not None
            else None
        )
        ctfroute_namespace = initial_config.get("ctfroute_namespace", "")
        runner: RunnerConfig = RunnerConfig.from_dict(initial_config.get("runner", {}))

        scoreboard_freeze = initial_config["scoreboard_freeze"] if "scoreboard_freeze" in initial_config else None

        result = cls(
            basedir=basedir,
            VPN_BASE_DIR=vpn_base_dir,
            CLOUDCONFIG_FILE=cloudconfig_file,
            CONFIG=initial_config,
            CONFIG_FILE=filename,
            POSTGRES=postgres,
            POSTGRES_USE_SOCKET=postgres_use_socket,
            REDIS=redis,
            RABBITMQ=rabbitmq,
            METRICS=metrics,
            TICK_DURATION_DEFAULT=tick_duration_default,
            VPNBOARD_PATH=vpnboard_path,
            CHECKER_PACKAGES_PATH=checker_packages_path,
            CHECKER_PACKAGES_LFS=checker_packages_lfs,
            SERVICES_PATH=services_path,
            PATCHES_PATH=patches_path,
            PATCHES_PUBLIC_PATH=patches_public_path,
            FLOWER_URL=flower_url,
            FLOWER_INTERNAL_URL=flower_internal_url,
            FLOWER_AJAX_URL=flower_ajax_url,
            CODER_URL=coder_url,
            SCOREBOARD_URL=scoreboard_url,
            GRAFANA_URL=grafana_url,
            PATCHES_URL=patches_url,
            SECRET_FLAG_KEY=secret_flag_key,
            FLAG_PREFIX=flag_prefix,
            SCORING=ScoringConfig.from_dict(scoring),
            SERVICE_REMOTES=service_remotes,
            DISPATCHER_CHECK_VPN_STATUS=dispatcher_check_vpn_status,
            EXTERNAL_TIMER=external_timer,
            NETWORK=network,
            WIREGUARD_SYNC=wireguard_sync,
            RUNNER=runner,
            SCOREBOARD_FREEZE=scoreboard_freeze,
            SCOREBOARD_PATH=scoreboard_path,
            SCOREBOARD_PATH_INTERNAL=scoreboard_path_internal,
            CTFROUTE_NAMESPACE=ctfroute_namespace,
        )
        if interpolate_env:
            result = result.interpolate_env()
        return result

    def to_dict(self) -> dict[str, Any]:
        return self.CONFIG | {
            "databases": self.CONFIG["databases"]
                         | {
                             "postgres": self.POSTGRES,
                             "redis": self.REDIS,
                             "rabbitmq": self.RABBITMQ,
                             "metrics": self.METRICS,
                         },
            "tick_duration_default": self.TICK_DURATION_DEFAULT,
            "vpnboard_path": str(self.VPNBOARD_PATH),
            "checker_packages_path": str(self.CHECKER_PACKAGES_PATH),
            "services_path": str(self.SERVICES_PATH),
            "patches_path": str(self.PATCHES_PATH),
            "patches_public_path": str(self.PATCHES_PUBLIC_PATH) if self.PATCHES_PUBLIC_PATH else None,
            "flower_url": self.FLOWER_URL,
            "flower_internal_url": self.FLOWER_INTERNAL_URL,
            "flower_ajax_url": self.FLOWER_AJAX_URL,
            "coder_url": self.CODER_URL,
            "scoreboard_url": self.SCOREBOARD_URL,
            "grafana_url": self.GRAFANA_URL,
            "patches_url": self.PATCHES_URL,
            "secret_flags": binascii.hexlify(self.SECRET_FLAG_KEY).decode("ascii"),
            "flag_prefix": self.FLAG_PREFIX,
            "scoring": self.SCORING.to_dict(),
            "service_remotes": self.SERVICE_REMOTES,
            "dispatcher_check_vpn_status": self.DISPATCHER_CHECK_VPN_STATUS,
            "external_timer": self.EXTERNAL_TIMER,
            "network": self.NETWORK.to_dict(),
            "wireguard_sync": self.WIREGUARD_SYNC.to_dict() if self.WIREGUARD_SYNC else None,
            "runner": self.RUNNER.to_dict(),
            "scoreboard_freeze": self.SCOREBOARD_FREEZE,
            "scoreboard_path": str(self.SCOREBOARD_PATH),
            "scoreboard_path_internal": str(self.SCOREBOARD_PATH_INTERNAL) if self.SCOREBOARD_PATH_INTERNAL else None,
            "ctfroute_namespace": self.CTFROUTE_NAMESPACE,
        }

    @classmethod
    def _clean_comments(cls, d: dict) -> None:
        for k, v in list(d.items()):
            if k.startswith("__"):
                del d[k]
            elif isinstance(v, dict):
                cls._clean_comments(v)

    def postgres_sqlalchemy(self) -> str:
        conn = "postgresql+psycopg2://"
        if self.POSTGRES["username"]:
            conn += self.POSTGRES["username"]
            if self.POSTGRES["password"]:
                conn += ":" + self.POSTGRES["password"]
            conn += "@"
        if self.POSTGRES["server"] and not self.POSTGRES_USE_SOCKET:
            conn += f"{self.POSTGRES['server']}:{self.POSTGRES['port']}"
        return conn + "/" + self.POSTGRES["database"]

    def postgres_psycopg2(self) -> str:
        db_host = self.POSTGRES["server"]
        db_port = self.POSTGRES["port"]
        db_name = self.POSTGRES["database"]
        conn = f"host='{db_host}' port={db_port} dbname='{db_name}'"
        if db_username := self.POSTGRES["username"]:
            conn += f" user='{db_username}'"
            if db_password := self.POSTGRES["password"]:
                conn += f" password='{db_password}'"
        return conn

    # --- Celery connections ---
    # Message broker: RabbitMQ (redis fallback), result storage: Redis
    # Celery is in redis DB +1 (so we have separated DBs for celery and gameserver)

    def celery_redis_url(self) -> str:
        redis_host = self.REDIS["host"]
        redis_port = self.REDIS["port"]
        redis_db = self.REDIS["db"] + 1  # db = gameserver, db+1 = celery
        if "password" in self.REDIS:
            redis_password = self.REDIS["password"]
            return f"redis://:{redis_password}@{redis_host}:{redis_port}/{redis_db}"
        return f"redis://{redis_host}:{redis_port}/{redis_db}"

    def celery_rabbitmq_url(self) -> str:
        if not self.RABBITMQ:
            raise ValueError("RabbitMQ not configured")
        rabbitmq_username = self.RABBITMQ["username"]
        rabbitmq_password = self.RABBITMQ["password"]
        rabbitmq_host = self.RABBITMQ["host"]
        rabbitmq_port = self.RABBITMQ["port"]
        rabbitmq_vhost = self.RABBITMQ["vhost"]
        return f"amqp://{rabbitmq_username}:{rabbitmq_password}@{rabbitmq_host}:{rabbitmq_port}/{rabbitmq_vhost}"

    def celery_url(self) -> str:
        if self.RABBITMQ:
            return self.celery_rabbitmq_url()
        return self.celery_redis_url()

    def set_script(self) -> None:
        """We're currently in a script instance, disable some features"""
        self.EXTERNAL_TIMER = False

    def validate(self) -> None:
        """Check for the most severe fuckups that you might have."""
        if not self.SCOREBOARD_PATH.name:
            raise ValueError("SCOREBOARD_PATH not configured")
        if len(self.SECRET_FLAG_KEY) < 16:
            raise ValueError("SECRET_FLAG_KEY not configured or too short")
        if len(self.FLAG_PREFIX) != 4:
            raise ValueError("FLAG_PREFIX must be exactly 4 characters long")


class CurrentConfigProxy:
    def __getattr__(self, item: str) -> Any:
        global current_config
        if not current_config:
            raise ValueError("Config not initialized")
        return getattr(current_config, item)

    def __setattr__(self, key: str, value: Any) -> None:
        global current_config
        if not current_config:
            raise ValueError("Config not initialized")
        setattr(current_config, key, value)


config: Config = CurrentConfigProxy()  # type: ignore
current_config: Config = None  # type: ignore


def load_default_config() -> None:
    global current_config
    current_config = Config.load_default()


def load_default_config_file(filename: Path, additional: dict[str, Any] | None = None) -> None:
    global current_config
    with filename.open("rb") as f:
        if f.name.endswith(".json"):
            d: dict[str, Any] = json.load(f)  # type: ignore
        else:
            d = yaml.safe_load(f)
    if additional:
        d = d | additional
    current_config = Config.from_dict(filename, d)


def get_by_names(config: Any, names: list[str]) -> Any:
    for name in names:
        if isinstance(config, dict):
            config = config.get(name)
        elif isinstance(config, Config) or isinstance(config, ConfigSection):
            if name.upper() in config.__dict__:
                config = getattr(config, name.upper())
            elif name.lower() in config.__dict__:
                config = getattr(config, name.lower())
            elif hasattr(config, name):
                config = getattr(config, name)
            elif isinstance(config, Config) and name in config.CONFIG:
                config = config.CONFIG[name]
            else:
                raise KeyError(name)
        else:
            raise ValueError(f"Invalid config type: {type(config)} {config}")
        if callable(config):
            config = config()
    return config


if __name__ == "__main__":
    import sys

    # print a config option (can be used in bash scripts etc)
    if sys.argv[1] == "get":
        load_default_config()
        x = get_by_names(current_config, sys.argv[2:])
        print(str(x))
        sys.exit(0)
    else:
        print("Invalid command")
        sys.exit(1)
