import os
from pathlib import Path
from tempfile import TemporaryDirectory

from controlserver.timer import init_mock_timer, CTFState
from saarctf_commons import config
from tests.utils.base_cases import DatabaseTestCase
from tests.utils.scriptrunner import ScriptRunner


class ScriptsTests(DatabaseTestCase):
    def test_reset_ctf(self) -> None:
        self.demo_team_services()
        result = ScriptRunner.run_script('scripts/reset_ctf.py', ['--force'])
        ScriptRunner.assert_no_exception(result)
        self.assertIn(b'Done.', result.stdout)

    def test_reset_ctf_to_round(self) -> None:
        self.demo_team_services()
        result = ScriptRunner.run_script('scripts/reset_ctf_to_round.py', ['0', '--force'])
        ScriptRunner.assert_no_exception(result)
        self.assertIn(b'Done.', result.stdout)

    def test_recreate_scoreboard(self) -> None:
        timer = init_mock_timer()
        timer.state = CTFState.RUNNING
        timer.desired_state = CTFState.RUNNING
        timer.current_tick = 2
        timer.update_redis()
        self.demo_team_services()
        with TemporaryDirectory() as directory:
            config.current_config.SCOREBOARD_PATH = Path(directory)
            result = ScriptRunner.run_script('scripts/recreate_scoreboard.py', [])
            ScriptRunner.assert_no_exception(result)
            self.assertIn(b'Done.', result.stdout)
            self.assertTrue((config.config.SCOREBOARD_PATH / 'api' / 'scoreboard_current.json').exists())

    def test_recreate_ranking(self) -> None:
        timer = init_mock_timer()
        timer.state = CTFState.RUNNING
        timer.desired_state = CTFState.RUNNING
        timer.current_tick = 1
        timer.update_redis()
        self.demo_team_services()
        result = ScriptRunner.run_script('scripts/recreate_ranking.py', [])
        ScriptRunner.assert_no_exception(result)
        self.assertIn(b'Done, took', result.stdout)

    def test_recreate_firstblood(self) -> None:
        timer = init_mock_timer()
        timer.state = CTFState.RUNNING
        timer.desired_state = CTFState.RUNNING
        timer.current_tick = 1
        timer.update_redis()
        self.demo_team_services()
        result = ScriptRunner.run_script('scripts/recreate_firstblood.py', [])
        ScriptRunner.assert_no_exception(result)
        self.assertIn(b'Done.', result.stdout)

    def test_patch(self) -> None:
        self.demo_team_services()
        with TemporaryDirectory() as directory:
            base = Path(directory)
            config.current_config.PATCHES_PATH = base / 'private'
            config.current_config.PATCHES_PUBLIC_PATH = base / 'public'
            config.current_config.PATCHES_PATH.mkdir()
            config.current_config.PATCHES_PUBLIC_PATH.mkdir()
            f1 = base / 'testpatch.sh'
            f2 = base / 'additional.txt'
            f1.write_text('#!/bin/sh\necho OK')
            f2.write_text('Hello World')

            result = ScriptRunner.run_script('scripts/patch_prepare.py', [str(f1), str(f2)])
            ScriptRunner.assert_no_exception(result)
            private_files = [p.name for p in (base / 'private').glob('*')]
            public_files = [p.name for p in (base / 'public').glob('*')]
            self.assertIn('hosts_nop.yaml', private_files)
            self.assertIn('hosts.yaml', private_files)
            self.assertEqual([], public_files)

            result = ScriptRunner.run_script('scripts/patch_publish.py', [str(f1), str(f2)])
            ScriptRunner.assert_no_exception(result)
            private_files = [p.name for p in (base / 'private').glob('*')]
            public_files = [p.name for p in (base / 'public').glob('*')]
            self.assertIn('hosts_nop.yaml', private_files)
            self.assertIn('hosts.yaml', private_files)
            self.assertIn(f1.name, public_files)
            self.assertIn(f2.name, public_files)

    def test_timer(self) -> None:
        result = ScriptRunner.run_script_for_time('controlserver/master_timer.py', [], duration=2)
        ScriptRunner.assert_no_exception(result)
        self.assertIn(b'Timer active', result.stdout)
        self.assertIn(b'Timer stopped', result.stdout)

    def test_scoreboard_daemon(self) -> None:
        timer = init_mock_timer()
        timer.state = CTFState.RUNNING
        timer.desired_state = CTFState.RUNNING
        timer.current_tick = 2
        timer.update_redis()
        self.demo_team_services()
        with TemporaryDirectory() as directory:
            config.current_config.SCOREBOARD_PATH = Path(directory)
            result = ScriptRunner.run_script_for_time('controlserver/scoring/scoreboard_process.py', [], duration=2)
            ScriptRunner.assert_no_exception(result)
            self.assertIn(b'Prepared scoreboard for tick 1', result.stdout)
            self.assertIn(b'Waiting for new ticks ...', result.stdout)

