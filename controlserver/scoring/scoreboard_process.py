import os
import sys


sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from controlserver.models import init_database
from controlserver.scoring.scoreboard import run_scoreboard_generator
from controlserver.timer import init_slave_timer
from saarctf_commons.config import load_default_config, config
from saarctf_commons.logging_utils import setup_script_logging
from saarctf_commons.redis import NamedRedisConnection

if __name__ == '__main__':
    load_default_config()
    config.set_script()
    setup_script_logging('scoreboard')
    NamedRedisConnection.set_clientname('scoreboard', True)
    init_database()
    init_slave_timer()
    try:
        run_scoreboard_generator()
    except KeyboardInterrupt:
        print('Scoreboard generator terminated')
