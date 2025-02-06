import os
import sys
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.timer import init_slave_timer
from controlserver.models import init_database
from saarctf_commons.redis import NamedRedisConnection
from saarctf_commons.config import config, load_default_config
from controlserver.scoring.scoreboard import Scoreboard
from controlserver.scoring.scoring import ScoringCalculation
from saarctf_commons.debug_sql_timing import timing, print_query_stats

"""
ARGUMENTS: start_tick end_tick (both optional)
"""


def recreate_scoreboard(tick_start: int, tick_end: Optional[int]) -> None:
    init_database()
    from controlserver.timer import Timer, CTFState
    scoring = ScoringCalculation(config.SCORING)
    scoreboard = Scoreboard(scoring)
    scoreboard.check_scoreboard_prepared(force_recreate=True)
    scoreboard.update_team_info()
    rn = tick_start
    tick_end_game = Timer.current_tick if Timer.state != CTFState.RUNNING else Timer.current_tick - 1
    if tick_end is None:
        tick_end = tick_end_game
    else:
        tick_end = min(tick_end, tick_end_game)
    if tick_start <= 1:
        # tick "-1"
        scoreboard.create_scoreboard(0, False, False)
    if tick_start <= 1 and tick_end_game > 0:
        # tick "0"
        scoreboard.create_scoreboard(0, True, False)
    if rn < 1:
        rn = 1
    while rn <= tick_end:
        scoreboard.create_scoreboard(rn, Timer.state != CTFState.STOPPED, rn == tick_end_game)
        print(f'- Scoreboard for tick {rn} created')
        rn += 1
        tick_end_game = Timer.current_tick if Timer.state != CTFState.RUNNING else Timer.current_tick - 1


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))
    init_slave_timer()

    if len(sys.argv) <= 2:
        tick_start = 1
        tick_end = None
    else:
        tick_start = int(sys.argv[1])
        tick_end = int(sys.argv[2]) if sys.argv[2] != 'current' else None
    timing()
    recreate_scoreboard(tick_start, tick_end)
    timing('Scoreboard')
    print('Done.')
    if '--stats' in sys.argv:
        print_query_stats()
