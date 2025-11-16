from saarctf_commons.config import load_default_config, config
from saarctf_commons.redis import NamedRedisConnection
from controlserver.models import init_database
from checker_runner.user_agents import init_celery_environment
from checker_runner.runner import celery_worker

load_default_config()
config.validate()
NamedRedisConnection.set_clientname("worker")
init_database()
init_celery_environment()
celery_worker.init()
celery = celery_worker.app
