import multiprocessing

import amqp

from checker_runner.runner import celery_worker
from controlserver.models import init_database, close_database
from saarctf_commons.config import config
from saarctf_commons.redis import get_redis_connection
from tests.utils.base_cases import DatabaseTestCase


class CeleryTestCase(DatabaseTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        get_redis_connection().flushdb()
        celery_worker.init()

    def setUp(self):
        super().setUp()
        self._purge_queue()
        self.worker = multiprocessing.Process(target=self._run_worker)
        self.worker.start()

    def _purge_queue(self):
        if config.RABBITMQ:
            with amqp.Connection(host=config.RABBITMQ['host'], port=config.RABBITMQ['port'],
                                 userid=config.RABBITMQ['username'], password=config.RABBITMQ['password'],
                                 virtual_host=config.RABBITMQ['vhost']) as connection:
                ch = connection.channel()
                for queue in ['celery', 'broadcast', 'tests']:
                    try:
                        ch.queue_purge(queue)
                    except amqp.exceptions.NotFound:
                        pass
        else:
            get_redis_connection().flushdb()

    def tearDown(self):
        if self.worker.is_alive():
            self.worker.terminate()
            self.worker.join(timeout=1)
        if self.worker.is_alive():
            self.worker.kill()
            self.worker.join()
        super().tearDown()

    def _run_worker(self) -> None:
        init_database()
        celery_worker.app.worker_main(['worker', '-Ofair', '-E', '-Q', 'celery,broadcast,tests', '--concurrency=1'])
