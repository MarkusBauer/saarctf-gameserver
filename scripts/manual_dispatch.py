import os
import sys
import time

from saarctf_commons import config

config.set_redis_clientname('script-' + os.path.basename(__file__))
config.EXTERNAL_TIMER = True
from controlserver.dispatcher import Dispatcher

"""
ARGUMENTS: round (optional)
"""

if __name__ == '__main__':
	# config.set_redis_clientname(os.path.basename(__file__))
	if len(sys.argv) <= 1:
		from controlserver.timer import Timer

		roundnumber = Timer.currentRound
	else:
		roundnumber = int(sys.argv[1])

	import controlserver.app

	t = time.time()
	dispatcher = Dispatcher()
	dispatcher.dispatch_checker_scripts(roundnumber)
	print('Checker scripts for round {} dispatched. Took {:.1f} sec'.format(roundnumber, time.time() - t))
