import os
import sys
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.EXTERNAL_TIMER = True
from controlserver.scoring.scoring import ScoringCalculation
from sample_files.debug_sql_timing import timing, print_query_stats

"""
ARGUMENTS: none
"""

if __name__ == '__main__':
	# noinspection PyUnresolvedReferences
	from controlserver import app as app
	config.set_redis_clientname('script-' + os.path.basename(__file__))
	timing()
	scoring = ScoringCalculation()
	print('Recomputing first blood flags now, might take some time ...')
	scoring.recompute_first_blood_flags()
	timing('First Blood')
	print('Done.')
	if '--stats' in sys.argv:
		print_query_stats()
