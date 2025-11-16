import argparse
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.timer import init_slave_timer, CTFState
from controlserver.models import init_database
from saarctf_commons.redis import NamedRedisConnection
from saarctf_commons.config import config, load_default_config
from controlserver.scoring.scoreboard import Scoreboard
from controlserver.scoring.filtered_scoring import FilteredScoringCalculation

"""
ARGUMENTS: filename (default: stdout)
--exclude 1,2,3  (default: NOP team)
--subtract-nop
"""


def export_ctftime_scoreboard(fname: str | None, exclude: set[int], subtract_nop: bool = False) -> None:
    init_database()
    init_slave_timer()
    from controlserver.timer import Timer

    exclude.add(config.SCORING.nop_team_id)  # always exclude NOP team
    scoring = FilteredScoringCalculation(config.SCORING, exclude_team_ids=exclude, subtract_nop_points=subtract_nop)
    scoreboard = Scoreboard(scoring, config.SCOREBOARD_PATH, public=False)
    tick = (
        Timer.current_tick
        if Timer.state != CTFState.RUNNING
        else Timer.current_tick - 1
    )
    data = scoreboard.create_ctftime_json(tick)
    if fname:
        fname = os.path.abspath(fname)
        with open(fname, "w") as f:
            f.write(data)
        print(f'Saved scoreboard to "{fname}".')
    else:
        print(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser('CTFTime Scoreboard Export')
    parser.add_argument('--exclude', type=str, default='',
                        help='Exclude some teams (by ID) in addition to NOP team, comma-separated')
    parser.add_argument('--subtract-nop', action='store_true', help='Subtract NOP team\'s points')
    parser.add_argument('output', nargs='?', type=str, default='-')
    args = parser.parse_args()

    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname("script-" + os.path.basename(__file__))
    exclude = set(int(x.strip()) for x in args.exclude.split(',') if x.strip())
    export_ctftime_scoreboard(args.output if args.output != '-' else None, exclude, subtract_nop=args.subtract_nop)
