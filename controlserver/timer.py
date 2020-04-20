"""
Central pace-keeping unit of the CTF. Starts and ends round, start/stop/pause the game and more.
Timer is a singleton: .Timer in this file. Do not use class CTFTimer directly.

Timer can be in master- or slave-mode:
- Master mode: Actual clock that triggers events and new rounds
- Slave mode: Replicates the state of the master clock using Redis, but is still allowed to send commands ("desiredState", "roundTime", ...)
There must always be exactly one master clock. Run this file to get a single master clock.

You can listen to all events emitted by this timer using:
- CTFEvents interface (events.py)
- Redis messages (subscribe "timing:*")

"""
import threading
from enum import IntEnum
import time
from typing import List, Union, Optional

from redis import StrictRedis, client

from controlserver.events import *
from saarctf_commons.config import get_redis_connection, set_redis_clientname, EXTERNAL_TIMER
from controlserver.logger import logException

if __name__ == '__main__':
	set_redis_clientname('timer', True)


class CTFState(IntEnum):
	STOPPED = 1
	SUSPENDED = 2
	RUNNING = 3


def to_int(x: Union[str, bytes]) -> Optional[int]:
	if not x or x == b'None':
		return None
	return int(x)


def redis_set_and_publish(key: str, value, redis: StrictRedis = None):
	if value is None:
		value = b'None'
	redis = redis or get_redis_connection()
	redis.set(key, value)
	redis.publish(key, value)


class CTFTimerBase:
	def __init__(self):
		self.initialized = False
		self.state: CTFState = CTFState.STOPPED
		self.desiredState: CTFState = CTFState.STOPPED
		self._currentRound: int = 0
		self._roundStart: Optional[int] = None
		self._roundEnd: Optional[int] = None
		self._roundTime: int = 120
		self._stopAfterRound: Optional[int] = None
		self._startAt: Optional[int] = None  # timestamp in SECONDS after epoch
		self.redis_pubsub: Optional[client.PubSub] = None
		self.listener: List[CTFEvents] = []

	@property
	def currentRound(self) -> int:
		return self._currentRound

	@property
	def roundStart(self) -> Optional[int]:
		return self._roundStart

	@property
	def roundEnd(self) -> Optional[int]:
		return self._roundEnd

	@property
	def roundTime(self) -> int:
		return self._roundTime

	@property
	def stopAfterRound(self) -> Optional[int]:
		return self._stopAfterRound

	@property
	def startAt(self) -> Optional[int]:
		return self._startAt

	def init(self, state: bytes, desiredState: bytes, currentRound, roundStart, roundEnd, roundTime, stopAfterRound=None, startAt=None):
		if state is None:
			return
		self.state = CTFState[state.decode('utf-8')]
		self.desiredState = CTFState[desiredState.decode('utf-8')]
		self._currentRound = int(currentRound)
		self._roundStart = to_int(roundStart)
		self._roundEnd = to_int(roundEnd)
		self._roundTime = int(roundTime)
		self._stopAfterRound = to_int(stopAfterRound)
		self._startAt = to_int(startAt)

	def init_from_redis(self):
		redis = get_redis_connection()
		self.init(
			redis.get('timing:state'),
			redis.get('timing:desiredState'),
			redis.get('timing:currentRound'),
			redis.get('timing:roundStart'),
			redis.get('timing:roundEnd'),
			redis.get('timing:roundTime'),
			redis.get('timing:stopAfterRound'),
			redis.get('timing:startAt')
		)

	def __listen_for_redis_events(self):
		for item in self.redis_pubsub.listen():
			if item['type'] == 'message':
				# print('Redis message:', item)
				if item['channel'] == b'timing:state':
					self.state = CTFState[item['data'].decode('utf-8')]
				elif item['channel'] == b'timing:desiredState':
					self.desiredState = CTFState[item['data'].decode('utf-8')]
				elif item['channel'] == b'timing:currentRound':
					self._currentRound = to_int(item['data'])
				elif item['channel'] == b'timing:roundStart':
					self._roundStart = to_int(item['data'])
				elif item['channel'] == b'timing:roundEnd':
					self._roundEnd = to_int(item['data'])
				elif item['channel'] == b'timing:roundTime':
					self._roundTime = int(item['data'])
				elif item['channel'] == b'timing:stopAfterRound':
					self._stopAfterRound = to_int(item['data'])
				elif item['channel'] == b'timing:startAt':
					self._startAt = to_int(item['data'])

	def bind_to_redis(self):
		redis: StrictRedis = get_redis_connection()
		self.redis_pubsub = redis.pubsub()
		self.redis_pubsub.subscribe(
			'timing:state', 'timing:desiredState', 'timing:currentRound', 'timing:roundStart', 'timing:roundEnd', 'timing:roundTime',
			'timing:stopAfterRound', 'timing:startAt')
		thread = threading.Thread(target=self.__listen_for_redis_events, name='Timer-Redis-Listener', daemon=True)
		thread.start()

	def countMasterTimer(self) -> int:
		return get_redis_connection().pubsub_numsub('timing:master')[0][1]

	def startCtf(self):
		raise Exception('Not implemented')

	def suspendCtfAfterRound(self):
		raise Exception('Not implemented')

	def stopCtfAfterRound(self):
		raise Exception('Not implemented')

	def checkTime(self):
		pass


class CTFTimer(CTFTimerBase):
	def __init__(self):
		super().__init__()

	@property
	def roundTime(self) -> int:
		return self._roundTime

	@roundTime.setter
	def roundTime(self, roundTime: int):
		if self._roundTime != roundTime:
			self._roundTime = roundTime
			if self.roundStart:
				self._roundEnd = self.roundStart + self._roundTime
			self.onUpdateTimes()

	@property
	def stopAfterRound(self) -> Optional[int]:
		return self._stopAfterRound

	@stopAfterRound.setter
	def stopAfterRound(self, lastRound: Optional[int]):
		if self._stopAfterRound != lastRound:
			self._stopAfterRound = lastRound
			self.onUpdateTimes()

	@property
	def startAt(self) -> Optional[int]:
		return self._startAt

	@startAt.setter
	def startAt(self, timestamp: Optional[int]):
		if self._startAt != timestamp:
			self._startAt = timestamp
			self.onUpdateTimes()

	def bind_to_redis(self):
		CTFTimerBase.bind_to_redis(self)
		self.redis_pubsub.subscribe('timing:master')

	def checkTime(self):
		"""
		Called periodically (typically once per second)
		:return:
		"""
		t: int = int(time.time())
		if self.state == CTFState.RUNNING and t >= self._roundEnd:
			# current round ends
			self.onEndRound(self._currentRound)
			if self.desiredState == CTFState.RUNNING:
				# start a new round
				self._currentRound += 1
				self._roundStart = t if t > self._roundEnd + 1 else self._roundEnd
				self._roundEnd = self._roundStart + self._roundTime
				self.onStartRound(self._currentRound)
			else:
				# suspend or stop after this round
				self.state = self.desiredState
				if self.state == CTFState.SUSPENDED:
					self.onSuspendCtf()
				else:
					self.onEndCtf()
			self.onUpdateTimes()
		elif self.state != CTFState.RUNNING and self.desiredState == CTFState.RUNNING:
			self.startCtf()
		elif self.state != CTFState.RUNNING and self.startAt and self.startAt <= t <= self.startAt + 4:
			self._startAt = None
			self.startCtf()

	def startCtf(self):
		"""
		Start the CTF now
		:return:
		"""
		self.desiredState = CTFState.RUNNING
		if self.state != CTFState.RUNNING:
			self._currentRound += 1
			self._roundStart = int(time.time())
			self._roundEnd = self._roundStart + self._roundTime
			if self.state == CTFState.STOPPED:
				self.onStartCtf()
			self.state = CTFState.RUNNING
			self.onStartRound(self._currentRound)
			self.onUpdateTimes()

	def suspendCtfAfterRound(self):
		"""
		Pause the CTF after the current round finished
		:return:
		"""
		self.desiredState = CTFState.SUSPENDED
		self.onUpdateTimes()

	def stopCtfAfterRound(self):
		"""
		Stop the CTF after the current round finished
		:return:
		"""
		self.desiredState = CTFState.STOPPED
		self.onUpdateTimes()

	def onStartRound(self, roundnumber: int):
		if self._stopAfterRound and self._stopAfterRound == roundnumber:
			self.desiredState = CTFState.STOPPED
			self._stopAfterRound = None
		for l in self.listener:
			l.onStartRound(roundnumber)

	def onEndRound(self, roundnumber: int):
		for l in self.listener:
			l.onEndRound(roundnumber)

	def onStartCtf(self):
		self.updateRoundTimes()
		for l in self.listener:
			l.onStartCtf()

	def onSuspendCtf(self):
		for l in self.listener:
			l.onSuspendCtf()

	def onEndCtf(self):
		self.updateRoundTimes()
		for l in self.listener:
			l.onEndCtf()

	def onUpdateTimes(self):
		redis = get_redis_connection()
		redis_set_and_publish('timing:state', self.state.name, redis)
		redis_set_and_publish('timing:desiredState', self.desiredState.name, redis)
		redis_set_and_publish('timing:currentRound', self._currentRound, redis)
		redis_set_and_publish('timing:roundStart', self._roundStart, redis)
		redis_set_and_publish('timing:roundEnd', self._roundEnd, redis)
		redis_set_and_publish('timing:roundTime', self._roundTime, redis)
		redis_set_and_publish('timing:stopAfterRound', self._stopAfterRound, redis)
		redis_set_and_publish('timing:startAt', self._startAt, redis)
		self.updateRoundTimes(redis)
		for l in self.listener:
			l.onUpdateTimes()

	def updateRoundTimes(self, redis=None):
		if self.state == CTFState.RUNNING:
			redis = redis or get_redis_connection()
			redis.set('round:{}:start'.format(self._currentRound), self._roundStart)
			redis.set('round:{}:end'.format(self._currentRound), self._roundEnd)
			redis.set('round:{}:time'.format(self._currentRound), self._roundTime)


class CTFTimerSlave(CTFTimerBase):
	def __init__(self):
		super().__init__()
		self.redis = get_redis_connection()

	@property
	def roundTime(self) -> int:
		return self._roundTime

	@roundTime.setter
	def roundTime(self, roundTime: int):
		if self._roundTime != roundTime:
			self._roundTime = roundTime
			if self.roundStart:
				self._roundEnd = self.roundStart + self._roundTime
				redis_set_and_publish('timing:roundEnd', self._roundEnd)
			redis_set_and_publish('timing:roundTime', self._roundTime)

	@property
	def stopAfterRound(self) -> Optional[int]:
		return self._stopAfterRound

	@stopAfterRound.setter
	def stopAfterRound(self, lastRound: Optional[int]):
		if self._stopAfterRound != lastRound:
			self._stopAfterRound = lastRound
			redis_set_and_publish('timing:stopAfterRound', self._stopAfterRound)

	@property
	def startAt(self) -> Optional[int]:
		return self._startAt

	@startAt.setter
	def startAt(self, timestamp: Optional[int]):
		if self._startAt != timestamp:
			self._startAt = timestamp
			redis_set_and_publish('timing:startAt', self._startAt)

	def startCtf(self):
		"""
		Start the CTF now
		:return:
		"""
		self.desiredState = CTFState.RUNNING
		redis_set_and_publish('timing:desiredState', self.desiredState.name)

	def suspendCtfAfterRound(self):
		"""
		Pause the CTF after the current round finished
		:return:
		"""
		self.desiredState = CTFState.SUSPENDED
		redis_set_and_publish('timing:desiredState', self.desiredState.name)

	def stopCtfAfterRound(self):
		self.desiredState = CTFState.STOPPED
		redis_set_and_publish('timing:desiredState', self.desiredState.name)


# Singleton CTFTimer instance, and default listeners (either master=self-counting or slave=getting state from redis)
master_timer: bool = not EXTERNAL_TIMER or __name__ == '__main__'
Timer: CTFTimerBase = CTFTimer() if master_timer else CTFTimerSlave()
Timer.init_from_redis()
Timer.bind_to_redis()
if master_timer:
	Timer.listener.append(ConsoleCTFEvents())


def notify():
	"""
	Called from outside (app.py)
	:return:
	"""
	try:
		Timer.checkTime()
	except Exception as e:
		logException('timer', e)
		raise


__all__ = ['CTFTimer', 'CTFState', 'Timer', 'notify']


def main():
	"""
	Run "master" timer
	:return:
	"""
	from controlserver.events_impl import LogCTFEvents, DeferredCTFEvents, VPNCTFEvents
	Timer.listener.append(LogCTFEvents())
	Timer.listener.append(DeferredCTFEvents())
	Timer.listener.append(VPNCTFEvents())
	print('Timer active...')
	try:
		while True:
			notify()
			time.sleep(1.0 - (time.time() % 1.0))
	except KeyboardInterrupt:
		print('Timer stopped.')


if __name__ == '__main__':
	main()
