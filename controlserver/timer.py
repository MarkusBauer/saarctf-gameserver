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
import time
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import List, Optional

from redis import StrictRedis, client, Redis

from checker_runner.runner import celery_worker
from controlserver.models import init_database
from controlserver.events import *
from controlserver.logger import logException
from saarctf_commons.config import config, load_default_config
from saarctf_commons.redis import NamedRedisConnection, get_redis_connection


class CTFState(IntEnum):
    STOPPED = 1
    SUSPENDED = 2
    RUNNING = 3


def to_int(x: int | str | bytes | None) -> Optional[int]:
    if not x or x == b'None':
        return None
    return int(x)


def redis_set_and_publish(key: str, value: str | bytes | int | None, redis: StrictRedis | None = None) -> None:
    if value is None:
        value = b'None'
    elif isinstance(value, int):
        value = str(value)
    redis = redis or get_redis_connection()
    redis.set(key, value)
    redis.publish(key, value)


class CTFTimerBase(ABC):
    def __init__(self) -> None:
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

    @roundTime.setter
    def roundTime(self, roundTime: int) -> None:
        if self._roundTime != roundTime:
            self._roundTime = roundTime
            if self.roundStart:
                self._roundEnd = self.roundStart + self._roundTime
            self.onUpdateTimes()

    @property
    def stopAfterRound(self) -> Optional[int]:
        return self._stopAfterRound

    @stopAfterRound.setter
    def stopAfterRound(self, lastRound: Optional[int]) -> None:
        if self._stopAfterRound != lastRound:
            self._stopAfterRound = lastRound
            self.onUpdateTimes()

    @property
    def startAt(self) -> Optional[int]:
        return self._startAt

    @startAt.setter
    def startAt(self, timestamp: Optional[int]) -> None:
        if self._startAt != timestamp:
            self._startAt = timestamp
            self.onUpdateTimes()

    @abstractmethod
    def onUpdateTimes(self) -> None:
        raise NotImplementedError

    def init(self,
             state: str | bytes,
             desiredState: str | bytes,
             currentRound: int | str | bytes | None,
             roundStart: int | str | bytes | None,
             roundEnd: int | str | bytes | None,
             roundTime: int | str | bytes | None,
             stopAfterRound: int | str | bytes | None = None,
             startAt: int | str | bytes | None = None
             ) -> None:
        if state is None:
            return
        self.state = CTFState[state.decode('utf-8') if isinstance(state, bytes) else state]
        self.desiredState = CTFState[desiredState.decode('utf-8') if isinstance(desiredState, bytes) else desiredState]
        self._currentRound = to_int(currentRound) or 0
        self._roundStart = to_int(roundStart)
        self._roundEnd = to_int(roundEnd)
        self._roundTime = int(roundTime or self._roundTime)
        self._stopAfterRound = to_int(stopAfterRound)
        self._startAt = to_int(startAt)

    def init_from_redis(self) -> None:
        redis = get_redis_connection()
        self.init(
            state=redis.get('timing:state'),  # type: ignore
            desiredState=redis.get('timing:desiredState'),  # type: ignore
            currentRound=redis.get('timing:currentRound'),
            roundStart=redis.get('timing:roundStart'),
            roundEnd=redis.get('timing:roundEnd'),
            roundTime=redis.get('timing:roundTime'),
            stopAfterRound=redis.get('timing:stopAfterRound'),
            startAt=redis.get('timing:startAt')
        )

    def __listen_for_redis_events(self) -> None:
        for item in self.redis_pubsub.listen():  # type: ignore
            if item['type'] == 'message':
                # print('Redis message:', item)
                if item['channel'] == b'timing:state':
                    self.state = CTFState[item['data'].decode('utf-8')]
                elif item['channel'] == b'timing:desiredState':
                    self.desiredState = CTFState[item['data'].decode('utf-8')]
                elif item['channel'] == b'timing:currentRound':
                    self._currentRound = int(item['data'])
                elif item['channel'] == b'timing:roundStart':
                    self._roundStart = to_int(item['data'])
                elif item['channel'] == b'timing:roundEnd':
                    self._roundEnd = to_int(item['data'])
                elif item['channel'] == b'timing:roundTime':
                    self._roundTime = int(item['data']) or self._roundTime
                elif item['channel'] == b'timing:stopAfterRound':
                    self._stopAfterRound = to_int(item['data'])
                elif item['channel'] == b'timing:startAt':
                    self._startAt = to_int(item['data'])

    def bind_to_redis(self) -> None:
        redis: StrictRedis = get_redis_connection()
        self.redis_pubsub = redis.pubsub()
        self.redis_pubsub.subscribe(
            'timing:state', 'timing:desiredState', 'timing:currentRound', 'timing:roundStart', 'timing:roundEnd',
            'timing:roundTime',
            'timing:stopAfterRound', 'timing:startAt')
        thread = threading.Thread(target=self.__listen_for_redis_events, name='Timer-Redis-Listener', daemon=True)
        thread.start()

    def countMasterTimer(self) -> int:
        return get_redis_connection().pubsub_numsub('timing:master')[0][1]

    def startCtf(self) -> None:
        raise Exception('Not implemented')

    def suspendCtfAfterRound(self) -> None:
        raise Exception('Not implemented')

    def stopCtfAfterRound(self) -> None:
        raise Exception('Not implemented')

    def checkTime(self) -> None:
        pass


class CTFTimer(CTFTimerBase):
    def __init__(self) -> None:
        super().__init__()

    def bind_to_redis(self) -> None:
        CTFTimerBase.bind_to_redis(self)
        self.redis_pubsub.subscribe('timing:master')  # type: ignore

    def checkTime(self) -> None:
        """
        Called periodically (typically once per second)
        :return:
        """
        t: int = int(time.time())
        if self.state == CTFState.RUNNING and self._roundEnd and t >= self._roundEnd:
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

    def startCtf(self) -> None:
        """
        Start the CTF now
        :return:
        """
        self.desiredState = CTFState.RUNNING
        if self.state != CTFState.RUNNING:
            self._currentRound += 1
            self._roundStart = int(time.time())
            self._roundEnd = self._roundStart + self._roundTime
            old_state = self.state
            self.state = CTFState.RUNNING
            if old_state == CTFState.STOPPED:
                self.onStartCtf()
            self.onStartRound(self._currentRound)
            self.onUpdateTimes()

    def suspendCtfAfterRound(self) -> None:
        """
        Pause the CTF after the current round finished
        :return:
        """
        self.desiredState = CTFState.SUSPENDED
        self.onUpdateTimes()

    def stopCtfAfterRound(self) -> None:
        """
        Stop the CTF after the current round finished
        :return:
        """
        self.desiredState = CTFState.STOPPED
        self.onUpdateTimes()

    def onStartRound(self, roundnumber: int) -> None:
        if self._stopAfterRound and self._stopAfterRound == roundnumber:
            self.desiredState = CTFState.STOPPED
            self._stopAfterRound = None
        for l in self.listener:
            l.onStartRound(roundnumber)

    def onEndRound(self, roundnumber: int) -> None:
        for l in self.listener:
            l.onEndRound(roundnumber)

    def onStartCtf(self) -> None:
        self.updateRoundTimes()
        for l in self.listener:
            l.onStartCtf()

    def onSuspendCtf(self) -> None:
        for l in self.listener:
            l.onSuspendCtf()

    def onEndCtf(self) -> None:
        self.updateRoundTimes()
        for l in self.listener:
            l.onEndCtf()

    def onUpdateTimes(self) -> None:
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

    def updateRoundTimes(self, redis: Redis | None = None) -> None:
        if self.state == CTFState.RUNNING:
            redis = redis or get_redis_connection()
            redis.set('round:{}:start'.format(self._currentRound), self._roundStart)  # type: ignore
            redis.set('round:{}:end'.format(self._currentRound), self._roundEnd)  # type: ignore
            redis.set('round:{}:time'.format(self._currentRound), self._roundTime)  # type: ignore


class CTFTimerSlave(CTFTimerBase):
    def __init__(self) -> None:
        super().__init__()
        self.redis = get_redis_connection()

    @property
    def roundTime(self) -> int:
        return self._roundTime

    @roundTime.setter
    def roundTime(self, roundTime: int) -> None:
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
    def stopAfterRound(self, lastRound: Optional[int]) -> None:
        if self._stopAfterRound != lastRound:
            self._stopAfterRound = lastRound
            redis_set_and_publish('timing:stopAfterRound', self._stopAfterRound)

    @property
    def startAt(self) -> Optional[int]:
        return self._startAt

    @startAt.setter
    def startAt(self, timestamp: Optional[int]) -> None:
        if self._startAt != timestamp:
            self._startAt = timestamp
            redis_set_and_publish('timing:startAt', self._startAt)

    def startCtf(self) -> None:
        """
        Start the CTF now
        :return:
        """
        self.desiredState = CTFState.RUNNING
        redis_set_and_publish('timing:desiredState', self.desiredState.name)

    def suspendCtfAfterRound(self) -> None:
        """
        Pause the CTF after the current round finished
        :return:
        """
        self.desiredState = CTFState.SUSPENDED
        redis_set_and_publish('timing:desiredState', self.desiredState.name)

    def stopCtfAfterRound(self) -> None:
        self.desiredState = CTFState.STOPPED
        redis_set_and_publish('timing:desiredState', self.desiredState.name)

    def onUpdateTimes(self) -> None:
        raise NotImplementedError


class CTFTimerMock(CTFTimerBase):
    @property
    def currentRound(self) -> int:
        return self._currentRound

    @currentRound.setter
    def currentRound(self, tick: int) -> None:
        self._currentRound = tick
        redis_set_and_publish('timing:currentRound', self._currentRound)

    def onUpdateTimes(self) -> None:
        pass

    def updateRedis(self) -> None:
        redis_set_and_publish('timing:state', self.state.name)
        redis_set_and_publish('timing:desiredState', self.desiredState.name)
        redis_set_and_publish('timing:currentRound', self._currentRound)


# Singleton CTFTimer instance, and default listeners (either master=self-counting or slave=getting state from redis)
Timer: CTFTimerBase


def init_timer(master_timer: bool) -> None:
    global Timer
    Timer = CTFTimer() if master_timer else CTFTimerSlave()
    Timer.init_from_redis()
    Timer.bind_to_redis()
    if master_timer:
        Timer.listener.append(ConsoleCTFEvents())


def init_cp_timer() -> None:
    master_timer: bool = not config.EXTERNAL_TIMER
    init_timer(master_timer)


def init_slave_timer() -> None:
    init_timer(False)


def init_mock_timer() -> CTFTimerMock:
    global Timer
    Timer = CTFTimerMock()
    return Timer


def run_master_timer() -> None:
    """
    Run "master" timer
    :return:
    """
    global Timer
    from controlserver.events_impl import LogCTFEvents, DeferredCTFEvents, VPNCTFEvents
    Timer.listener.append(LogCTFEvents())
    Timer.listener.append(DeferredCTFEvents())
    Timer.listener.append(VPNCTFEvents())
    Timer.initialized = True
    print('Timer active...')
    try:
        while True:
            try:
                Timer.checkTime()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                logException('timer', e)
                raise
            time.sleep(1.0 - (time.time() % 1.0))
    except KeyboardInterrupt:
        print('Timer stopped.')


__all__ = ['CTFTimer', 'CTFState', 'Timer', 'run_master_timer', 'init_slave_timer', 'init_cp_timer', 'run_master_timer']
