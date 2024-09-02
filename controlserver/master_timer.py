if __name__ == '__main__':
    import sys
    import os

    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from checker_runner.runner import celery_worker
from controlserver.models import init_database
from controlserver.timer import init_timer, run_master_timer
from saarctf_commons.config import load_default_config
from saarctf_commons.redis import NamedRedisConnection

if __name__ == '__main__':
    load_default_config()
    NamedRedisConnection.set_clientname('timer', True)

if __name__ == '__main__':
    init_database()
    init_timer(True)
    celery_worker.init()
    run_master_timer()