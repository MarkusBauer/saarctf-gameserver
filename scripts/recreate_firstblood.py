import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.models import init_database
from saarctf_commons.redis import NamedRedisConnection
from saarctf_commons.config import config, load_default_config
from controlserver.scoring.scoring import ScoringCalculation
from saarctf_commons.debug_sql_timing import timing, print_query_stats

"""
ARGUMENTS: none
"""

if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))
    init_database()
    timing()
    scoring = ScoringCalculation(config.SCORING)
    print('Recomputing first blood flags now, might take some time ...')
    scoring.recompute_first_blood_flags()
    timing('First Blood')
    print('Done.')
    if '--stats' in sys.argv:
        print_query_stats()
