import os
import sys
import time
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.timer import init_slave_timer, CTFState
from controlserver.models import init_database, db_session
from saarctf_commons.redis import NamedRedisConnection
from saarctf_commons.config import config, load_default_config

"""
ARGUMENTS: start_tick end_tick (inclusive, optional)
--scoreboard: Recreate scoreboard after update
"""


def recreate_ranking(tick_start: int, tick_end: Optional[int], refresh_scoreboard: bool) -> int:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    init_database()
    init_slave_timer()
    from controlserver.timer import Timer
    from controlserver.models import TeamRanking, TeamPoints
    from controlserver.scoring.scoring import ScoringCalculation
    from saarctf_commons.debug_sql_timing import print_query_stats
    from controlserver.scoring.scoreboard import Scoreboard

    # Recreate points / ranking from checker results and submitted_flags
    scoring = ScoringCalculation(config.SCORING)
    scoreboard = Scoreboard(scoring)
    rn = tick_start
    tick_end_game = Timer.current_tick if Timer.state != CTFState.RUNNING else Timer.current_tick - 1
    if refresh_scoreboard and tick_start <= 1 and tick_end_game > 0:
        scoreboard.create_scoreboard(0, False, False)
        scoreboard.create_scoreboard(0, True, False)
    while rn <= (tick_end or tick_end_game):
        ts = time.time()
        # Remove old points/ranking from DB
        TeamPoints.query.filter(TeamPoints.tick == rn).delete()
        TeamRanking.query.filter(TeamRanking.tick == rn).delete()
        db_session().commit()

        scoring.calculate_scoring_for_tick(rn)
        scoring.calculate_ranking_per_tick(rn)
        if refresh_scoreboard:
            tick_end_game = Timer.current_tick if Timer.state != CTFState.RUNNING else Timer.current_tick - 1
            scoreboard.create_scoreboard(rn, Timer.state != CTFState.STOPPED, rn == tick_end_game)
        ts = time.time() - ts
        print(f'- Round {rn} recalculated in {ts:.2f} seconds')
        rn += 1
    print_query_stats()
    return rn - 1


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))

    if len(sys.argv) <= 2:
        tick_start = 1
        tick_end = None
    else:
        tick_start = int(sys.argv[1])
        tick_end = int(sys.argv[2]) if sys.argv[2] != 'current' else None
    scoreboard = '--scoreboard' in sys.argv
    t = time.time()
    print('Recreating ranking from tick {} to tick {}...'.format(tick_start, tick_end or '<current>'))
    tick = recreate_ranking(tick_start, tick_end, scoreboard)
    print('Done, took {:.1f} sec.'.format(time.time() - t))
    if not scoreboard:
        print('Suggestion: > python ' + sys.argv[0].replace('recreate_ranking.py', 'recreate_scoreboard.py'))
