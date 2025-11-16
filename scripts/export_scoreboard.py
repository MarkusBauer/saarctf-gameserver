import argparse
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.timer import init_slave_timer, CTFState
from controlserver.models import init_database
from saarctf_commons.redis import NamedRedisConnection
from saarctf_commons.config import config, load_default_config
from controlserver.scoring.scoreboard import Scoreboard
from controlserver.scoring.filtered_scoring import FilteredScoringCalculation

"""
ARGUMENTS: filename (default: stdout)
--exclude 1,2,3  (default: none)
--subtract-nop
"""


def export_scoreboard(fname: str, exclude: set[int], subtract_nop: bool = False) -> None:
    init_database()
    init_slave_timer()
    from controlserver.timer import Timer

    output = Path(fname)
    output.mkdir(exist_ok=True, parents=True)

    scoring = FilteredScoringCalculation(config.SCORING, exclude_team_ids=exclude, subtract_nop_points=subtract_nop)
    scoreboard = Scoreboard(scoring, output=output, public=False)

    scoreboard.check_scoreboard_prepared(force_recreate=True)
    scoreboard.update_team_info()
    # allow hosting under any path
    html = (output / 'index.html').read_text('utf-8')
    html = html.replace('<base href="/">', '')
    (output / 'index.html').write_text(html, 'utf-8')

    tick_end_game = Timer.current_tick if Timer.state != CTFState.RUNNING else Timer.current_tick - 1
    print(f'last tick: {tick_end_game}')
    # tick "-1"
    scoreboard.create_scoreboard(0, False, False)
    # tick "0"
    scoreboard.create_scoreboard(0, True, False)
    # tick "1"..n
    for rn in range(1, tick_end_game + 1):
        scoreboard.create_scoreboard(
            rn, Timer.state != CTFState.STOPPED, rn == tick_end_game
        )
        print(f"- Scoreboard for tick {rn} created")
        rn += 1
        tick_end_game = (
            Timer.current_tick
            if Timer.state != CTFState.RUNNING
            else Timer.current_tick - 1
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser('Scoreboard Export')
    parser.add_argument('--exclude', type=str, default='',
                        help='Exclude some teams (by ID), comma-separated')
    parser.add_argument('--subtract-nop', action='store_true', help='Subtract NOP team\'s points')
    parser.add_argument('output', type=str)
    args = parser.parse_args()

    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname("script-" + os.path.basename(__file__))
    exclude = set(int(x.strip()) for x in args.exclude.split(',') if x.strip())
    export_scoreboard(args.output, exclude, subtract_nop=args.subtract_nop)
