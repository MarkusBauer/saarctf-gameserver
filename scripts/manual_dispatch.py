import os
import sys
import time

from checker_runner.runner import celery_worker
from controlserver.models import init_database
from saarctf_commons.config import config, load_default_config
from saarctf_commons.redis import NamedRedisConnection
from controlserver.dispatcher import Dispatcher

"""
ARGUMENTS: tick (optional)
"""

if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))
    celery_worker.init()

    # config.set_redis_clientname(os.path.basename(__file__))
    if len(sys.argv) <= 1:
        from controlserver.timer import Timer, init_slave_timer
        init_slave_timer()

        tick = Timer.current_tick
    else:
        tick = int(sys.argv[1])

    init_database()

    t = time.time()
    dispatcher = Dispatcher()
    dispatcher.dispatch_checker_scripts(tick)
    print('Checker scripts for tick {} dispatched. Took {:.1f} sec'.format(tick, time.time() - t))
