import os
import sys
import time

from checker_runner.runner import celery_worker
from controlserver.models import init_database
from saarctf_commons.config import config, load_default_config
from controlserver.dispatcher import Dispatcher
from saarctf_commons.redis import NamedRedisConnection

"""
ARGUMENTS: round (optional)
"""

if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))
    celery_worker.init()

    if len(sys.argv) <= 1:
        from controlserver.timer import Timer, init_slave_timer
        init_slave_timer()

        roundnumber = Timer.currentRound
    else:
        roundnumber = int(sys.argv[1])

    init_database()

    t = time.time()
    dispatcher = Dispatcher()
    dispatcher.collect_checker_results(roundnumber)
    print('Collected checker scripts for round {}. Took {:.1f} sec'.format(roundnumber, time.time() - t))
