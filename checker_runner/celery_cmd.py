from saarctf_commons.config import load_default_config
from saarctf_commons.redis import NamedRedisConnection
from controlserver.models import init_database
from checker_runner.runner import celery_worker

load_default_config()
NamedRedisConnection.set_clientname('worker')
init_database()
celery_worker.init()
celery = celery_worker.app
