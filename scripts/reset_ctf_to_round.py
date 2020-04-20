import os
import shutil
import sys

import redis

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.EXTERNAL_TIMER = True
from controlserver.scoring.scoreboard import Scoreboard
from controlserver.scoring.scoring import ScoringCalculation
from sample_files.debug_sql_timing import timing, print_query_stats

"""
ARGUMENT: round
"""


def query_yes_no(question, default="yes") -> bool:
	"""Ask a yes/no question via raw_input() and return their answer.

	https://stackoverflow.com/a/3041990

	"question" is a string that is presented to the user.
	"default" is the presumed answer if the user just hits <Enter>.
		It must be "yes" (the default), "no" or None (meaning
		an answer is required of the user).

	The "answer" return value is True for "yes" or False for "no".
	"""
	valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
	if default is None:
		prompt = " [y/n] "
	elif default == "yes":
		prompt = " [Y/n] "
	elif default == "no":
		prompt = " [y/N] "
	else:
		raise ValueError("invalid default answer: '%s'" % default)

	while True:
		sys.stdout.write(question + prompt)
		choice = input().lower()
		if default is not None and choice == '':
			return valid[default]
		elif choice in valid:
			return valid[choice]
		else:
			sys.stdout.write("Please respond with 'yes' or 'no' (or 'y' or 'n').\n")


def reset_redis(tick: int):
	from saarctf_commons.config import get_redis_connection, celery_redis_url
	redis = get_redis_connection()
	redis.set('timing:currentRound', str(tick))
	redis.publish('timing:currentRound', str(tick))

	wiped = 0
	for key in redis.keys(b'services:*'):
		key_tick = key.split(b':')[3]
		if int(key_tick) > tick:
			redis.delete(key)
			wiped += 1
	print(f'Wiped {wiped} keys.')


def reset_database(tick: int):
	import controlserver.app
	import controlserver.models
	for m in ['TeamPoints', 'TeamRanking', 'CheckerResult']:
		model = getattr(controlserver.models, m)
		count = model.query.filter(model.round > tick).delete()
		print('- dropped {} entries from {}'.format(count, m))
	count = controlserver.models.SubmittedFlag.query.filter(controlserver.models.SubmittedFlag.round_submitted > tick).delete()
	print('- dropped {} entries from SubmittedFlag'.format(count))
	controlserver.models.db.session.commit()


def reset_scoreboard(tick: int):
	from saarctf_commons.config import SCOREBOARD_PATH
	if os.path.exists(os.path.join(SCOREBOARD_PATH, 'api')):
		print('Removing scoreboard data ...')
		for fname in os.listdir(os.path.join(SCOREBOARD_PATH, 'api')):
			if fname.startswith('scoreboard_round_') and fname.endswith('.json'):
				num = int(fname[17:-5])
				if num > tick:
					os.remove(os.path.join(SCOREBOARD_PATH, 'api', fname))
					print('- deleted', os.path.join(SCOREBOARD_PATH, 'api', fname))
		scoreboard = Scoreboard(ScoringCalculation())
		scoreboard_tick = scoreboard.update_round_info()
		scoreboard.update_round_info(min(scoreboard_tick, tick))


def reset_ctf_to_tick():
	config.set_redis_clientname('script-' + os.path.basename(__file__))
	if len(sys.argv) < 2:
		print(f'USAGE: python3 {sys.argv[0]} <tick>')
		return

	tick = int(sys.argv[1])

	if not query_yes_no(f'Do you really want to wipe the whole CTF after round {tick}?', 'no'):
		return

	from controlserver.timer import Timer, CTFState
	if Timer.state == CTFState.RUNNING:
		print('CTF must not be running.')
		return
	if Timer.countMasterTimer() > 0:
		print('Please stop all master timers.')
		return

	print('Wiping redis ...')
	reset_redis(tick)

	print('Wiping database ...')
	reset_database(tick)

	reset_scoreboard(tick)

	print('Done. I suggest restarting other components.')


if __name__ == '__main__':
	reset_ctf_to_tick()
