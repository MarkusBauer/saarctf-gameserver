import os
import sys
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.timer import init_slave_timer, CTFState
from controlserver.models import init_database
from saarctf_commons.redis import NamedRedisConnection
from saarctf_commons.config import config, load_default_config
from controlserver.scoring.scoreboard import Scoreboard
from controlserver.scoring.scoring import ScoringCalculation

"""
ARGUMENTS: start_round end_round (both optional)
"""


def export_ctftime_scoreboard(fname: Optional[str]) -> None:
    init_database()
    init_slave_timer()
    from controlserver.timer import Timer
    scoring = ScoringCalculation(config.SCORING)
    scoreboard = Scoreboard(scoring)
    roundnumber = Timer.currentRound if Timer.state != CTFState.RUNNING else Timer.currentRound - 1
    data = scoreboard.create_ctftime_json(roundnumber)
    if fname:
        fname = os.path.abspath(fname)
        with open(fname, 'w') as f:
            f.write(data)
        print(f'Saved scoreboard to "{fname}".')
    else:
        print(data)


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))
    export_ctftime_scoreboard(sys.argv[1] if len(sys.argv) > 1 else None)
