import time
from unittest.mock import Mock, patch

from controlserver.dispatcher import Dispatcher
from controlserver.models import Team, db_session, Service, CheckerResult
from tests.utils.celery import CeleryTestCase


class DispatcherTestCase(CeleryTestCase):
    def _prepare_db(self) -> None:
        self.demo_team_services()
        self.team: Team = Team.query.get(1)  # type: ignore
        self.team.vpn_connected = True
        db_session().commit()

    def test_dispatch_test_script(self) -> None:
        self._prepare_db()
        dispatcher = Dispatcher()
        task, result = dispatcher.dispatch_test_script(self.team, Service.query.get(1), -1, None)  # type: ignore[arg-type]
        task_result = task.get(timeout=3)
        self.assertEqual('SUCCESS', task_result)
        result = CheckerResult.query.get(result.id)  # type: ignore[assignment]
        self.assertEqual(task.id, result.celery_id)
        self.assertEqual('SUCCESS', result.status)
        self.assertIsNotNone(result.finished)
        # self.assertTrue(result.integrity)
        # self.assertTrue(result.stored)
        # self.assertTrue(result.retrieved)
        self.assertIsNotNone(result.output)
        self.assertIn('----- check_integrity -----', result.output)  # type: ignore

    def test_dispatch_tick(self) -> None:
        self._prepare_db()
        dispatcher = Dispatcher()
        with patch('pathlib.Path.write_text') as write_text_mock:  # called by "attack.json" writer
            dispatcher.dispatch_checker_scripts(1)
            write_text_mock.assert_called_once()

        time.sleep(3.5)

        dispatcher.revoke_checker_scripts(1)
        dispatcher.collect_checker_results(1)
        results = dispatcher.get_checker_results(1)
        results.sort(key=lambda r: (r.team_id, r.service_id))
        # for result in results:
        #     print(result)
        # check all results are there
        self.assertEqual(3, len(results))
        self.assertEqual(1, results[0].team_id)
        self.assertEqual(1, results[0].service_id)
        self.assertEqual(1, results[1].team_id)
        self.assertEqual(2, results[1].service_id)
        self.assertEqual(1, results[2].team_id)
        self.assertEqual(3, results[2].service_id)

        # check final status
        self.assertEqual('SUCCESS', results[0].status)
        self.assertEqual('FLAGMISSING', results[1].status)
        self.assertEqual('TIMEOUT', results[2].status)

        self.print_logs()
        self.assert_in_logs('Worker close to overload')
