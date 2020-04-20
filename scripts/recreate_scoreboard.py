import os
import sys
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.EXTERNAL_TIMER = True
from controlserver.scoring.scoreboard import Scoreboard
from controlserver.scoring.scoring import ScoringCalculation
from sample_files.debug_sql_timing import timing, print_query_stats

"""
ARGUMENTS: start_round end_round (both optional)
"""


def recreate_scoreboard(round_start: int, round_end: Optional[int]):
	# noinspection PyUnresolvedReferences
	import controlserver.app
	from controlserver.timer import Timer, CTFState
	scoring = ScoringCalculation()
	scoreboard = Scoreboard(scoring)
	scoreboard.check_scoreboard_prepared(force_recreate=True)
	scoreboard.update_team_info()
	rn = round_start
	round_end_game = Timer.currentRound if Timer.state != CTFState.RUNNING else Timer.currentRound - 1
	scoreboard.create_scoreboard(0, False, False)
	if round_start <= 1 and round_end_game > 0:
		scoreboard.create_scoreboard(0, True, False)
	while rn <= (round_end or round_end_game):
		scoreboard.create_scoreboard(rn, Timer.state != CTFState.STOPPED, rn == round_end_game)
		print(f'- Scoreboard for round {rn} created')
		rn += 1
		round_end_game = Timer.currentRound if Timer.state != CTFState.RUNNING else Timer.currentRound - 1


if __name__ == '__main__':
	config.set_redis_clientname('script-' + os.path.basename(__file__))
	if len(sys.argv) <= 2:
		round_start = 1
		round_end = None
	else:
		round_start = int(sys.argv[1])
		round_end = int(sys.argv[2]) if sys.argv[2] != 'current' else None
	timing()
	recreate_scoreboard(round_start, round_end)
	timing('Scoreboard')
	print('Done.')
	if '--stats' in sys.argv:
		print_query_stats()
