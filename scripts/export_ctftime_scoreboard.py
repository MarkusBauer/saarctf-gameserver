import os
import sys
from typing import Optional

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.EXTERNAL_TIMER = True
from controlserver.scoring.scoreboard import Scoreboard
from controlserver.scoring.scoring import ScoringCalculation

"""
ARGUMENTS: start_round end_round (both optional)
"""


def export_ctftime_scoreboard(fname: Optional[str]):
	import controlserver.app
	from controlserver.timer import Timer, CTFState
	scoring = ScoringCalculation()
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
	config.set_redis_clientname('script-' + os.path.basename(__file__))
	export_ctftime_scoreboard(sys.argv[1] if len(sys.argv) > 1 else None)
