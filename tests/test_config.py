from dataclasses import fields
from pathlib import Path

from saarctf_commons import config
from tests.utils.base_cases import TestCase


class ConfigTest(TestCase):
    def test_network_dict(self) -> None:
        d = config.current_config.NETWORK.to_dict()
        c2 = config.NetworkConfig.from_dict(d)
        self.assertEqual(config.current_config.NETWORK, c2)

    def test_dict(self) -> None:
        d = config.current_config.to_dict()
        self.assertIs(type(d), dict)
        c2 = config.Config.from_dict(config.current_config.CONFIG_FILE, d)
        c2.CONFIG = config.current_config.CONFIG
        for f in fields(config.Config):
            self.assertEqual(getattr(config.current_config, f.name), getattr(c2, f.name), f"Not equal: {f.name}")
        self.assertEqual(config.current_config, c2)

    def test_sample_config_yaml(self) -> None:
        f = Path(__file__).parent.parent / "config.sample.yaml"
        c = config.Config.load_from_file(f, interpolate_env=False)
        self.assertEqual(1, c.SCORING.nop_team_id)
        self.assertEqual(10, c.SCORING.flags_rounds_valid)
        self.assertEqual('SAAR', c.FLAG_PREFIX)
        c.validate()

    def test_legacy_config(self) -> None:
        legacy_config = {
            "databases": {
                "postgres": {"database": "test"},
                "redis": {},
                "rabbitmq": {},
            },
            "scoreboard_path": "/dev/shm/scoreboard",
            "vpnboard_path": "/dev/shm/vpnboard",
            "checker_packages_path": "/dev/shm/packages",
            "logo_input_path": "/dev/shm/logo_input_path",
            "flower_url": "http://localhost:5555/",
            "secret_flags": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "external_timer": False,
            "flags_rounds_valid": 20,  # legacy
            "nop_team_id": 2,  # legacy
            "network": {
                "vulnbox_ip": [127, [200, 256, 32], [1, 200, 0], 2],
                "testbox_ip": [127, [200, 256, 32], [1, 200, 0], 3],
                "gateway_ip": [127, [200, 256, 32], [1, 200, 0], 1],
                "team_range": [127, [200, 256, 32], [1, 200, 0], 0, 24],
                "vpn_peer_ips": [127, [200, 256, 48], [1, 200, 0], 1],
            },
        }
        c = config.Config.from_dict(Path("test"), legacy_config, interpolate_env=False)
        self.assertEqual(2, c.SCORING.nop_team_id)
        self.assertEqual(20, c.SCORING.flags_rounds_valid)

    def test_validation(self) -> None:
        f = Path(__file__).parent.parent / 'config.sample.yaml'
        c = config.Config.load_from_file(f, interpolate_env=False)
        c.SECRET_FLAG_KEY = b""  # assume we forgot to configure it
        with self.assertRaises(ValueError):
            c.validate()
