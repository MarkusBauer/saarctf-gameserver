"""
Events like "Start CTF", "New round", ....
Everything is based on CTFEvents interface (in timer.py). Events are emitted by the Timer.
"""

import threading
import time

from controlserver.dispatcher import Dispatcher
from controlserver.logger import log, logResultOfExecution
from controlserver.models import LogMessage
from controlserver.scoring.scoreboard import Scoreboard
from controlserver.scoring.scoring import ScoringCalculation
from controlserver.events import CTFEvents
from controlserver.vpncontrol import VPNControl


class LogCTFEvents(CTFEvents):
	"""
	Create log entries for the events
	"""

	def onStartRound(self, roundnumber: int):
		log('timer', 'New round: {}'.format(roundnumber), level=LogMessage.IMPORTANT)

	def onStartCtf(self):
		log('timer', 'CTF starts', level=LogMessage.IMPORTANT)

	def onSuspendCtf(self):
		log('timer', 'CTF suspended', level=LogMessage.IMPORTANT)

	def onEndCtf(self):
		log('timer', 'CTF stopped', level=LogMessage.IMPORTANT)


class DeferredCTFEvents(CTFEvents):
	"""
	Dispatcher, Scoring, Scoreboard - process them in seperate threads at round start / end.
	"""

	def __init__(self):
		self.dispatcher = Dispatcher.default
		self.scoring = ScoringCalculation()
		self.scoreboard = Scoreboard(self.scoring, publish=True)

	def onStartRound(self, roundnumber: int):
		thread = threading.Thread(name='startround', target=self.__onStartRoundDeferred, args=(roundnumber,), daemon=False)
		thread.start()

	def onEndRound(self, roundnumber: int):
		thread = threading.Thread(name='endround', target=self.__onEndRoundDeferred, args=(roundnumber,), daemon=False)
		thread.start()

	def __onStartRoundDeferred(self, roundnumber: int):
		logResultOfExecution('dispatcher', self.dispatcher.dispatch_checker_scripts, args=(roundnumber,),
							 success='Checker scripts dispatched, took {:.3f} sec',
							 error='Couldn\'t start checker scripts: {} {}')
		if roundnumber == 1:
			logResultOfExecution('scoring',
								 self.scoreboard.create_scoreboard, args=(roundnumber - 1, True, True),
								 success='Scoreboard generated, took {:.1f} sec',
								 error='Scoreboard failed: {} {}')

	def __onEndRoundDeferred(self, roundnumber: int):
		time.sleep(1)
		logResultOfExecution('dispatcher', self.dispatcher.revoke_checker_scripts, args=(roundnumber,),
							 error='Couldn\'t revoke checker scripts: {} {}', reraise=False)
		logResultOfExecution('dispatcher', self.dispatcher.collect_checker_results, args=(roundnumber,),
							 success='Collected checker script results, took {:.3f} sec',
							 error='Couldn\'t collect checker script results: {} {}')
		logResultOfExecution('scoring',
							 self.scoring.scoring_and_ranking, args=(roundnumber,),
							 success='Ranking calculated, took {:.3f} sec',
							 error='Ranking calculation failed: {} {}')
		logResultOfExecution('scoring',
							 self.scoreboard.create_scoreboard, args=(roundnumber, True, True),
							 success='Scoreboard generated, took {:.1f} sec',
							 error='Scoreboard failed: {} {}')

	def onStartCtf(self):
		logResultOfExecution('scoring',
							 self.scoreboard.update_round_info, args=(),
							 error='Cloudn\'t create initial scoreboard: {} {}')

	def onUpdateTimes(self):
		logResultOfExecution('scoring',
							 self.scoreboard.update_round_info, args=(),
							 error='Cloudn\'t create updated scoreboard: {} {}')


class VPNCTFEvents(CTFEvents):
	def __init__(self):
		self.vpn = VPNControl()

	def onStartRound(self, roundnumber: int):
		self.vpn.unban_for_tick(roundnumber)

	def onStartCtf(self):
		self.vpn.set_state(True)

	def onEndCtf(self):
		self.vpn.set_state(False)
