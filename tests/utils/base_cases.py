import json
import os
import unittest
from pathlib import Path

import saarctf_commons
from controlserver.models import init_database, db_session, Team, Service, close_database, meta, Database, \
    SubmittedFlag, CheckerFilesystem, TeamLogo, \
    LogMessage, db_session_2
from saarctf_commons.config import config, Config, load_default_config_file

config_basis = {
    "scoreboard_path": "/dev/shm/scoreboard",
    "vpnboard_path": "/dev/shm/vpnboard",
    "checker_packages_path": "/dev/shm/packages",
    "logo_input_path": "/dev/shm/logo_input_path",
    "flower_url": "http://localhost:5555/",
    "secret_flags": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "external_timer": False,
    "scoring": {
        "flags_rounds_valid": 10,
        "nop_team_id": 1
    },
    "network": {
        "game": "127.0.0.0/16",
        "__ip_syntax": ["number", "or list", ["a", "b", "c"], "= ((team_id / a) mod b) + c"],
        "vulnbox_ip": [127, [200, 256, 32], [1, 200, 0], 2],
        "testbox_ip": [127, [200, 256, 32], [1, 200, 0], 3],
        "gateway_ip": [127, [200, 256, 32], [1, 200, 0], 1],
        "__range_syntax": ["number", "or list", ["a", "b", "c"], "= ((team_id / a) mod b) + c", "/range"],
        "team_range": [127, [200, 256, 32], [1, 200, 0], 0, 24],
        "gameserver_ip": "10.13.0.2",
        "vpn_host": "10.13.0.1",
        "vpn_peer_ips": [127, [200, 256, 48], [1, 200, 0], 1],
        "gameserver_range": "10.32.250.0/24"
    }
}
config_file: Path = Path(__file__).absolute().parent.parent.parent / 'config.test.json'
os.environ['SAARCTF_CONFIG'] = str(config_file)


class TestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        load_default_config_file(config_file, config_basis)
        assert config.CONFIG_FILE.name == 'config.test.json'


class DatabaseTestCase(TestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        init_database()
        meta.drop_all(bind=Database.db_engine)
        meta.create_all(bind=Database.db_engine)

    def setUp(self):
        session = db_session()
        Team.query.delete()
        TeamLogo.query.delete()
        Service.query.delete()
        SubmittedFlag.query.delete()
        CheckerFilesystem.query.delete()
        LogMessage.query.delete()
        session.commit()

    def tearDown(self):
        db_session().close()

    @classmethod
    def tearDownClass(cls):
        meta.drop_all(bind=Database.db_engine)
        Database.db_engine.execute("DROP TABLE IF EXISTS alembic_version;")
        close_database()

    def demo_team_services(self) -> None:
        with db_session_2() as session:
            session.add(Team(id=1, name='NOP'))
            session.add(Team(id=2, name='Team2'))
            session.add(Team(id=3, name='Team3'))
            session.add(Team(id=4, name='Team4'))
            session.add(Service(
                id=1, name='Service1',
                checker_script='checker_runner.demo_checker:WorkingService', checker_timeout=1,
                num_payloads=0, flags_per_tick=1
            ))  # type: ignore[misc]
            session.add(Service(
                id=2, name='Service2',
                checker_script='checker_runner.demo_checker:FlagNotFoundService', checker_timeout=1,
                num_payloads=0, flags_per_tick=1
            ))  # type: ignore[misc]
            session.add(Service(
                id=3, name='Service3',
                checker_script='checker_runner.demo_checker:TimeoutService', checker_timeout=1,
                num_payloads=2, flags_per_tick=2
            ))  # type: ignore[misc]
            session.commit()

    def get_logs(self) -> list[LogMessage]:
        return list(LogMessage.query.order_by('created', 'id'))

    def print_logs(self) -> None:
        for log in self.get_logs():
            print(f'- {log.level} [{log.component}] {log.title} ({log.text})')

    def assert_in_logs(self, title: str) -> None:
        for log in self.get_logs():
            if log.title and title in log.title:
                return
        raise AssertionError(f'Title {repr(title)} not found in logs')
