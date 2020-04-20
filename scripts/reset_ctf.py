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
NO ARGUMENTS
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


def reset_redis():
	from saarctf_commons.config import get_redis_connection, celery_redis_url
	get_redis_connection().flushdb()
	conn = redis.StrictRedis.from_url(celery_redis_url())
	conn.flushdb()

	from controlserver.timer import CTFTimer
	timer = CTFTimer()
	timer.onUpdateTimes()  # update without init - write default values


def reset_broker():
	from saarctf_commons.config import celery_url
	url = celery_url()
	if (url.startswith('redis:')):
		redis.StrictRedis.from_url(url).flushdb()
	else:
		# import kombu.connection
		# import kombu.transport.pyamqp
		# connection: kombu.transport.pyamqp.Connection = kombu.connection.Connection(url).connect()
		# print(type(connection))
		# connection.close()
		pass


def reset_database(include_storage=False):
	# we keep services and teams
	import controlserver.app
	import controlserver.models
	for m in ['TeamPoints', 'TeamRanking', 'SubmittedFlag', 'CheckerResult', 'LogMessage']:
		count = getattr(controlserver.models, m).query.delete()
		print('- dropped {} entries from {}'.format(count, m))
	if include_storage:
		for m in ['CheckerFile', 'CheckerFilesystem']:
			count = getattr(controlserver.models, m).query.delete()
			print('- dropped {} entries from {}'.format(count, m))
		controlserver.models.Service.query.update({controlserver.models.Service.package: None})
	controlserver.models.db.session.commit()


def reset_scoreboard():
	from saarctf_commons.config import SCOREBOARD_PATH
	if os.path.exists(os.path.join(SCOREBOARD_PATH, 'api')):
		print('Removing scoreboard data ...')
		shutil.rmtree(os.path.join(SCOREBOARD_PATH, 'api'))


def reset_ctf():
	config.set_redis_clientname('script-' + os.path.basename(__file__))

	if not query_yes_no('Do you really want to wipe the whole CTF?', 'no'):
		return

	print('Wiping redis ...')
	reset_redis()

	print('Wiping broker ...')
	reset_broker()

	print('Wiping database ...')
	reset_database()

	reset_scoreboard()

	print('Done. I suggest restarting other components.')


if __name__ == '__main__':
	reset_ctf()
