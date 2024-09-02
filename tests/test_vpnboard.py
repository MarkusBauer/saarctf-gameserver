import os
from pathlib import Path
from tempfile import TemporaryDirectory

from controlserver.models import db_session, Team
from saarctf_commons import config
from tests.utils.base_cases import DatabaseTestCase
from tests.utils.scriptrunner import ScriptRunner
from vpnboard.vpn_board import VpnBoard


class VpnBoardTests(DatabaseTestCase):
    def test_vpnboard_creation(self) -> None:
        self.demo_team_services()
        with TemporaryDirectory() as directory:
            config.current_config.VPNBOARD_PATH = Path(directory)
            board = VpnBoard(use_nping=False)
            board.build_vpn_board(False, set())
            self._assert_valid_vpnboard(config.current_config.VPNBOARD_PATH)

    def _assert_valid_vpnboard(self, d: Path) -> None:
        files = os.listdir(d)
        self.assertIn('vpn.html', files)
        self.assertIn('favicon.png', files)
        self.assertIn('index.css', files)
        self.assertIn('all_teams.json', files)
        self.assertIn('available_teams.json', files)
        vpn: str = (d / 'vpn.html').read_text()
        self.assertLessEqual(vpn.count('label-warning'), 1)
        self.assertLessEqual(vpn.count('label-danger'), 1)

    def test_vpnboard_script(self) -> None:
        self.demo_team_services()
        session = db_session()
        team: Team = session.query(Team).get(1)  # type: ignore[assignment]
        team.vpn_connected = True
        session.commit()

        with TemporaryDirectory() as directory:
            config.current_config.VPNBOARD_PATH = Path(directory)
            result = ScriptRunner.run_script('vpnboard/vpn_board.py', ['--system-ping'])
            ScriptRunner.assert_no_exception(result)
            self.assertIn(b'Created VPN board', result.stderr)
            self._assert_valid_vpnboard(config.current_config.VPNBOARD_PATH)

            influx_data = ScriptRunner.parse_influx_format(result.stdout.decode('utf-8'))
            self.assertEqual(len(influx_data['vpn_connection']), 4)
            self.assertEqual(len(influx_data['vpn_board']), 1)
            for entry in influx_data['vpn_board']:
                self.assertEqual(entry['router_up'], '1i')
                self.assertEqual(entry['testbox_up'], '1i')
                self.assertEqual(entry['testbox_ok'], '1i')
                self.assertIn('router_ping_ms', entry)
                self.assertIn('testbox_ping_ms', entry)
