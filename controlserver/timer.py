"""
Central pace-keeping unit of the CTF. Starts and ends ticks, start/stop/pause the game and more.
Timer is a singleton: .Timer in this file. Do not use class CTFTimer directly.

Timer can be in master- or slave-mode:
- Master mode: Actual clock that triggers events and new ticks
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

from redis import Redis, StrictRedis, client

from controlserver.events import *
from controlserver.events_impl import DatabaseTickRecording
from controlserver.logger import log_exception
from saarctf_commons.config import config
from saarctf_commons.redis import get_redis_connection


class CTFState(IntEnum):
    STOPPED = 1
    SUSPENDED = 2
    RUNNING = 3


def to_int(x: int | str | bytes | None) -> int | None:
    if not x or x == b"None":
        return None
    return int(x)


def redis_set_and_publish(key: str, value: str | bytes | int | None, redis: StrictRedis | None = None) -> None:
    if value is None:
        value = b"None"
    elif isinstance(value, int):
        value = str(value)
    redis = redis or get_redis_connection()
    redis.set(key, value)
    redis.publish(key, value)


class CTFTimerBase(ABC):
    def __init__(self) -> None:
        self.initialized = False
        self.state: CTFState = CTFState.STOPPED
        self.desired_state: CTFState = CTFState.STOPPED
        self._current_tick: int = 0
        self._tick_start: int | None = None
        self._tick_end: int | None = None
        self._tick_time: int = config.TICK_DURATION_DEFAULT
        self._stop_after_tick: int | None = None
        self._start_at: int | None = None  # timestamp in SECONDS after epoch
        self._open_vulnbox_access_at: int | None = None
        self.redis_pubsub: client.PubSub | None = None
        self.listener: list[CTFEvents] = []

    @property
    def current_tick(self) -> int:
        return self._current_tick

    @property
    def tick_start(self) -> int | None:
        return self._tick_start

    @property
    def tick_end(self) -> int | None:
        return self._tick_end

    @property
    def tick_time(self) -> int:
        return self._tick_time

    @tick_time.setter
    def tick_time(self, tick_time: int) -> None:
        if self._tick_time != tick_time:
            self._tick_time = tick_time
            if self.tick_start:
                self._tick_end = self.tick_start + self._tick_time
            self.on_update_times()

    @property
    def stop_after_tick(self) -> int | None:
        return self._stop_after_tick

    @stop_after_tick.setter
    def stop_after_tick(self, last_tick: int | None) -> None:
        if self._stop_after_tick != last_tick:
            self._stop_after_tick = last_tick
            self.on_update_times()

    @property
    def start_at(self) -> int | None:
        return self._start_at

    @start_at.setter
    def start_at(self, timestamp: int | None) -> None:
        if self._start_at != timestamp:
            self._start_at = timestamp
            self.on_update_times()

    @property
    def open_vulnbox_access_at(self) -> int | None:
        return self._open_vulnbox_access_at

    @open_vulnbox_access_at.setter
    def open_vulnbox_access_at(self, timestamp: int | None) -> None:
        if self._open_vulnbox_access_at != timestamp:
            self._open_vulnbox_access_at = timestamp
            self.on_update_times()

    @abstractmethod
    def on_update_times(self) -> None:
        raise NotImplementedError

    def init(
        self,
        state: str | bytes,
        desired_state: str | bytes,
        current_tick: int | str | bytes | None,
        tick_start: int | str | bytes | None,
        tick_end: int | str | bytes | None,
        tick_time: int | str | bytes | None,
        stop_after_tick: int | str | bytes | None = None,
        start_at: int | str | bytes | None = None,
        open_vulnbox_access_at: int | str | bytes | None = None,
    ) -> None:
        if state is None:
            return
        self.state = CTFState[state.decode('utf-8') if isinstance(state, bytes) else state]
        self.desired_state = CTFState[desired_state.decode('utf-8') if isinstance(desired_state, bytes) else desired_state]
        self._current_tick = to_int(current_tick) or 0
        self._tick_start = to_int(tick_start)
        self._tick_end = to_int(tick_end)
        self._tick_time = int(tick_time or self._tick_time)
        self._stop_after_tick = to_int(stop_after_tick)
        self._start_at = to_int(start_at)
        self._open_vulnbox_access_at = to_int(open_vulnbox_access_at)

    def init_from_redis(self) -> None:
        redis = get_redis_connection()
        self.init(
            state=redis.get("timing:state"),  # type: ignore
            desired_state=redis.get("timing:desiredState"),  # type: ignore
            current_tick=redis.get("timing:currentRound"),
            tick_start=redis.get("timing:roundStart"),
            tick_end=redis.get("timing:roundEnd"),
            tick_time=redis.get("timing:roundTime"),
            stop_after_tick=redis.get("timing:stopAfterRound"),
            start_at=redis.get("timing:startAt"),
            open_vulnbox_access_at=redis.get("timing:openVulnboxAccessAt"),
        )

    def __listen_for_redis_events(self) -> None:
        for item in self.redis_pubsub.listen():  # type: ignore
            if item["type"] == "message":
                # print('Redis message:', item)
                if item["channel"] == b"timing:state":
                    self.state = CTFState[item["data"].decode("utf-8")]
                elif item["channel"] == b"timing:desiredState":
                    self.desired_state = CTFState[item["data"].decode("utf-8")]
                elif item["channel"] == b"timing:currentRound":
                    self._current_tick = int(item["data"])
                elif item["channel"] == b"timing:roundStart":
                    self._tick_start = to_int(item["data"])
                elif item["channel"] == b"timing:roundEnd":
                    self._tick_end = to_int(item["data"])
                elif item["channel"] == b"timing:roundTime":
                    self._tick_time = int(item["data"]) or self._tick_time
                elif item["channel"] == b"timing:stopAfterRound":
                    self._stop_after_tick = to_int(item["data"])
                elif item["channel"] == b"timing:startAt":
                    self._start_at = to_int(item["data"])
                elif item["channel"] == b"timing:openVulnboxAccessAt":
                    self._open_vulnbox_access_at = to_int(item["data"])

    def bind_to_redis(self) -> None:
        redis: StrictRedis = get_redis_connection()
        self.redis_pubsub = redis.pubsub()
        self.redis_pubsub.subscribe(
            "timing:state",
            "timing:desiredState",
            "timing:currentRound",
            "timing:roundStart",
            "timing:roundEnd",
            "timing:roundTime",
            "timing:stopAfterRound",
            "timing:startAt",
            "timing:openVulnboxAccessAt",
        )
        thread = threading.Thread(
            target=self.__listen_for_redis_events,
            name="Timer-Redis-Listener",
            daemon=True,
        )
        thread.start()

    def count_master_timer(self) -> int:
        return get_redis_connection().pubsub_numsub("timing:master")[0][1]

    def start_ctf(self) -> None:
        raise Exception("Not implemented")

    def suspend_ctf_after_tick(self) -> None:
        raise Exception("Not implemented")

    def stop_ctf_after_tick(self) -> None:
        raise Exception("Not implemented")

    def check_time(self) -> None:
        pass


class CTFTimer(CTFTimerBase):
    def __init__(self) -> None:
        super().__init__()

    @override
    def bind_to_redis(self) -> None:
        CTFTimerBase.bind_to_redis(self)
        self.redis_pubsub.subscribe("timing:master")  # type: ignore

    @override
    def check_time(self) -> None:
        """
        Called periodically (typically once per second)
        :return:
        """
        t: int = int(time.time())
        if self.state == CTFState.RUNNING and self._tick_end and t >= self._tick_end:
            # current tick ends
            self.on_end_tick(self._current_tick)
            if self.desired_state == CTFState.RUNNING:
                # start a new tick
                self._current_tick += 1
                self._tick_start = t if t > self._tick_end + 1 else self._tick_end
                self._tick_end = self._tick_start + self._tick_time
                self.on_start_tick(self._current_tick)
            else:
                # suspend or stop after this tick
                self.state = self.desired_state
                if self.state == CTFState.SUSPENDED:
                    self.on_suspend_ctf()
                else:
                    self.on_end_ctf()
            self.on_update_times()
        elif self.state != CTFState.RUNNING and self.desired_state == CTFState.RUNNING:
            self.start_ctf()
        elif self.state != CTFState.RUNNING and self.start_at and self.start_at <= t <= self.start_at + 4:
            self._start_at = None
            self.start_ctf()
        elif self.state != CTFState.RUNNING and self._open_vulnbox_access_at and self._open_vulnbox_access_at <= t <= self._open_vulnbox_access_at + 4:
            self._open_vulnbox_access_at = None
            self.on_open_vulnbox_access()
            self.on_update_times()

    @override
    def start_ctf(self) -> None:
        """
        Start the CTF now
        :return:
        """
        self.desired_state = CTFState.RUNNING
        if self.state != CTFState.RUNNING:
            self._current_tick += 1
            self._tick_start = int(time.time())
            self._tick_end = self._tick_start + self._tick_time
            old_state = self.state
            self.state = CTFState.RUNNING
            if old_state == CTFState.STOPPED:
                self.on_start_ctf()
            self.on_start_tick(self._current_tick)
            self.on_update_times()

    @override
    def suspend_ctf_after_tick(self) -> None:
        """
        Pause the CTF after the current tick finished
        :return:
        """
        self.desired_state = CTFState.SUSPENDED
        self.on_update_times()

    @override
    def stop_ctf_after_tick(self) -> None:
        """
        Stop the CTF after the current tick finished
        :return:
        """
        self.desired_state = CTFState.STOPPED
        self.on_update_times()

    def on_start_tick(self, tick: int) -> None:
        dt = datetime.datetime.now(tz=datetime.timezone.utc).replace(microsecond=0)
        if self._stop_after_tick and self._stop_after_tick == tick:
            self.desired_state = CTFState.STOPPED
            self._stop_after_tick = None
        for l in self.listener:
            l.on_start_tick(tick, dt)

    def on_end_tick(self, tick: int) -> None:
        dt = datetime.datetime.now(tz=datetime.timezone.utc).replace(microsecond=0)
        for l in self.listener:
            l.on_end_tick(tick, dt)

    def on_start_ctf(self) -> None:
        self.update_tick_times()
        for l in self.listener:
            l.on_start_ctf()

    def on_suspend_ctf(self) -> None:
        for l in self.listener:
            l.on_suspend_ctf()

    def on_end_ctf(self) -> None:
        self.update_tick_times()
        for l in self.listener:
            l.on_end_ctf()

    def on_open_vulnbox_access(self) -> None:
        self.update_tick_times()
        for l in self.listener:
            l.on_open_vulnbox_access()

    @override
    def on_update_times(self) -> None:
        redis = get_redis_connection()
        redis_set_and_publish("timing:state", self.state.name, redis)
        redis_set_and_publish("timing:desiredState", self.desired_state.name, redis)
        redis_set_and_publish("timing:currentRound", self._current_tick, redis)
        redis_set_and_publish("timing:roundStart", self._tick_start, redis)
        redis_set_and_publish("timing:roundEnd", self._tick_end, redis)
        redis_set_and_publish("timing:roundTime", self._tick_time, redis)
        redis_set_and_publish("timing:stopAfterRound", self._stop_after_tick, redis)
        redis_set_and_publish("timing:startAt", self._start_at, redis)
        redis_set_and_publish("timing:openVulnboxAccessAt", self._open_vulnbox_access_at, redis)
        self.update_tick_times(redis)
        for l in self.listener:
            l.on_update_times()

    def update_tick_times(self, redis: Redis | None = None) -> None:
        if self.state == CTFState.RUNNING:
            redis = redis or get_redis_connection()
            redis.set("round:{}:start".format(self._current_tick), self._tick_start)  # type: ignore
            redis.set("round:{}:end".format(self._current_tick), self._tick_end)  # type: ignore
            redis.set("round:{}:time".format(self._current_tick), self._tick_time)  # type: ignore


class CTFTimerSlave(CTFTimerBase):
    def __init__(self) -> None:
        super().__init__()
        self.redis = get_redis_connection()

    @property
    def tick_time(self) -> int:
        return self._tick_time

    @tick_time.setter
    def tick_time(self, tick_time: int) -> None:
        if self._tick_time != tick_time:
            self._tick_time = tick_time
            if self.tick_start:
                self._tick_end = self.tick_start + self._tick_time
                redis_set_and_publish("timing:roundEnd", self._tick_end)
            redis_set_and_publish("timing:roundTime", self._tick_time)

    @property
    def stop_after_tick(self) -> int | None:
        return self._stop_after_tick

    @stop_after_tick.setter
    def stop_after_tick(self, last_tick: int | None) -> None:
        if self._stop_after_tick != last_tick:
            self._stop_after_tick = last_tick
            redis_set_and_publish("timing:stopAfterRound", self._stop_after_tick)

    @property
    def start_at(self) -> int | None:
        return self._start_at

    @start_at.setter
    def start_at(self, timestamp: int | None) -> None:
        if self._start_at != timestamp:
            self._start_at = timestamp
            redis_set_and_publish("timing:startAt", self._start_at)

    @property
    def open_vulnbox_access_at(self) -> int | None:
        return self._open_vulnbox_access_at

    @open_vulnbox_access_at.setter
    def open_vulnbox_access_at(self, timestamp: int | None) -> None:
        if self._open_vulnbox_access_at != timestamp:
            self._open_vulnbox_access_at = timestamp
            redis_set_and_publish("timing:openVulnboxAccessAt", self._open_vulnbox_access_at)

    @override
    def start_ctf(self) -> None:
        """
        Start the CTF now
        :return:
        """
        self.desired_state = CTFState.RUNNING
        redis_set_and_publish("timing:desiredState", self.desired_state.name)

    @override
    def suspend_ctf_after_tick(self) -> None:
        """
        Pause the CTF after the current tick finished
        :return:
        """
        self.desired_state = CTFState.SUSPENDED
        redis_set_and_publish("timing:desiredState", self.desired_state.name)

    @override
    def stop_ctf_after_tick(self) -> None:
        self.desired_state = CTFState.STOPPED
        redis_set_and_publish("timing:desiredState", self.desired_state.name)

    @override
    def on_update_times(self) -> None:
        raise NotImplementedError


class CTFTimerMock(CTFTimerBase):
    @property
    def current_tick(self) -> int:
        return self._current_tick

    @current_tick.setter
    def current_tick(self, tick: int) -> None:
        self._current_tick = tick
        redis_set_and_publish("timing:currentRound", self._current_tick)

    @override
    def on_update_times(self) -> None:
        pass

    def update_redis(self) -> None:
        redis_set_and_publish("timing:state", self.state.name)
        redis_set_and_publish("timing:desiredState", self.desired_state.name)
        redis_set_and_publish("timing:currentRound", self._current_tick)


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
    from controlserver.events_impl import DeferredCTFEvents, LogCTFEvents, VPNCTFEvents

    Timer.listener.append(LogCTFEvents())
    Timer.listener.append(DeferredCTFEvents())
    Timer.listener.append(VPNCTFEvents())
    Timer.listener.append(DatabaseTickRecording())
    Timer.initialized = True
    print("Timer active...")
    try:
        while True:
            try:
                Timer.check_time()
            except KeyboardInterrupt:
                raise
            except Exception as e:
                log_exception("timer", e)
                raise
            time.sleep(1.0 - (time.time() % 1.0))
    except KeyboardInterrupt:
        print("Timer stopped.")


__all__ = [
    "CTFTimer",
    "CTFState",
    "Timer",
    "init_slave_timer",
    "init_cp_timer",
    "run_master_timer",
]
