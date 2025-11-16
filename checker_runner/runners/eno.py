import asyncio
import base64
import hashlib
import hmac
import random
import struct
import traceback
from abc import ABC, abstractmethod
from enum import Enum
from functools import lru_cache
from typing import Any, ClassVar

from aiohttp.client import ClientSession, ClientTimeout
from enochecker_core import (
    CheckerInfoMessage,
    CheckerMethod,
    CheckerResultMessage,
    CheckerTaskMessage,
    CheckerTaskResult,
)

from checker_runner.checker_execution import CheckerRunner, CheckerRunOutput
from gamelib import MAC_LENGTH, get_flag_regex
from saarctf_commons.config import config
from saarctf_commons.redis import get_redis_connection


class SlotType(Enum):
    EARLY = 1
    UNCONSTRAINED = 2
    LATE = 3


class TaggedIntervalEntry:
    def __init__(self, entry_type: SlotType, offset: float, idx: int):
        self.entry_type = entry_type
        self.offset = offset
        self.idx = idx

    def __repr__(self) -> str:
        return f"TaggedIntervalEntry {{.entry_type = {self.entry_type}, .offset = {self.offset:6.3f}, .idx = {self.idx}}}"


class AsyncCheckerRunner(CheckerRunner, ABC):
    def execute_checker(self, team_id: int, tick: int) -> CheckerRunOutput:
        return asyncio.run(self.execute_checker_async(team_id, tick))
        # try:
        #     loop = asyncio.get_running_loop()
        #     return asyncio.run_coroutine_threadsafe(
        #         self.execute_checker_async(team_id, tick), loop
        #     ).result(60)

        # except RuntimeError:
        #     loop = asyncio.new_event_loop()
        #     return loop.run_until_complete(self.execute_checker_async(team_id, tick))

    @abstractmethod
    async def execute_checker_async(self, team_id: int, tick: int) -> CheckerRunOutput:
        raise NotImplementedError


class EnoCheckerRunner(AsyncCheckerRunner):
    TIME_BUFFER = 5

    def __init__(
        self, service_id: int, package: str, script: str, cfg: dict | None
    ) -> None:
        super().__init__(service_id, package, script, cfg)
        self.url = self.cfg["url"]
        self.custom_results: dict[str, Any] = {}
        self.output: list[str] = []
        self.messages: dict[str, str] = {}
        self.recovery_messages: dict[str, str] = {}
        self.status: str = "SUCCESS"  # TODO convert to enum in the future

    def reset(self) -> None:
        self.custom_results = {}
        self.output = []
        self.messages = {}
        self.recovery_messages = {}
        self.status = "SUCCESS"

    _service_info_cache: ClassVar[dict[str, CheckerInfoMessage]] = {}

    async def get_service_info(self) -> CheckerInfoMessage:
        if self.url in self._service_info_cache:
            return self._service_info_cache[self.url]
        async with (
            self._session() as session,
            session.get(self.url + "/service") as response,
        ):
            if response.status != 200:
                raise Exception(
                    f"Info request {response.url} returned {response.status}"
                )
            cim = CheckerInfoMessage.model_validate_json(await response.text())
        self._service_info_cache[self.url] = cim
        return cim

    @staticmethod
    @lru_cache()
    def get_tick_duration(tick: int) -> int:
        with get_redis_connection() as conn:
            v = conn.get(f"round:{tick}:time")
            if not v:
                raise ValueError()
            return int(v.decode())

    @staticmethod
    def get_fresh_task_id() -> int:
        with get_redis_connection() as conn:
            return conn.incr("runner:eno:task_id", 1)

    def get_flag(self, team_id: int, tick: int, payload: int = 0) -> str:
        data = struct.pack("<HHHH", tick & 0xFFFF, team_id, self.service_id, payload)
        mac = hmac.new(config.SECRET_FLAG_KEY, data, hashlib.sha256).digest()[
            :MAC_LENGTH
        ]
        flag = base64.b64encode(data + mac).replace(b"+", b"-").replace(b"/", b"_")
        return config.FLAG_PREFIX + "{" + flag.decode("utf-8") + "}"

    def set_flag_id(self, team_id: int, tick: int, index: int, value: str) -> None:
        with get_redis_connection() as redis_conn:
            redis_conn.set(
                f"custom_flag_ids:{self.service_id}:{tick}:{team_id}:{index}", value
            )

    def get_flag_id(self, team_id: int, tick: int, index: int) -> str | None:
        with get_redis_connection() as redis_conn:
            value = redis_conn.get(
                f"custom_flag_ids:{self.service_id}:{tick}:{team_id}:{index}"
            )
            return value.decode() if value is not None else None

    def _session(self) -> ClientSession:
        return ClientSession(timeout=ClientTimeout(total=20))

    async def _query(
        self, session: ClientSession, msg: CheckerTaskMessage
    ) -> CheckerResultMessage:
        try:
            json_msg = msg.model_dump_json()
            async with session.post(
                self.url,
                data=json_msg,
                headers={"Content-Type": "application/json"},
                timeout=ClientTimeout(msg.timeout / 1000 + 1),
            ) as response:
                if response.status != 200:
                    raise Exception(
                        f"Request to {response.url} returned with code {response.status}"
                    )
                result = CheckerResultMessage.model_validate_json(await response.text())
                if msg.method == CheckerMethod.GETFLAG:
                    self.custom_results[f"{msg.related_round_id}_{msg.variant_id}"] = (
                        result.result
                    )
                return result
        except TimeoutError:
            return CheckerResultMessage(
                result=CheckerTaskResult.INTERNAL_ERROR, message="TIMEOUT"
            )
        except Exception:
            self.output.append(traceback.format_exc())
            return CheckerResultMessage(
                result=CheckerTaskResult.INTERNAL_ERROR, message=None
            )

    def _task_chain_msg_write(self, messages: dict, key: str, msg: CheckerResultMessage):
        # We only show the first message returned from each task chain,
        # since this is the most likely culprit of the error. If one of
        # the messages is OFFLINE, we show that instead since it is
        # more accurate.
        if msg.result == CheckerTaskResult.OFFLINE:
            messages[key] = msg.message
        else:
            messages[key] = messages.get(key, msg.message)

    def _handle_result(
        self, msg: CheckerTaskMessage, result: CheckerResultMessage
    ) -> None:
        if result.message:
            if msg.current_round_id == msg.related_round_id:
                self._task_chain_msg_write(self.messages, msg.task_chain_id, result)
            else:
                self._task_chain_msg_write(self.recovery_messages, msg.task_chain_id, result)

        if result.result == CheckerTaskResult.INTERNAL_ERROR:
            self.status = "CRASHED" if result.message != "TIMEOUT" else "TIMEOUT"
        elif (
            self.status in ("SUCCESS", "RECOVERING")
            and result.result != CheckerTaskResult.OK
            and msg.current_round_id != msg.related_round_id
        ):
            self.status = "RECOVERING"
        elif (
            self.status in ("SUCCESS", "RECOVERING")
            and result.result == CheckerTaskResult.MUMBLE
        ):
            self.status = "MUMBLE"
        elif (
            self.status in ("SUCCESS", "RECOVERING", "MUMBLE")
            and result.result == CheckerTaskResult.OFFLINE
        ):
            self.status = "OFFLINE"

        # store flag IDs / attack info
        if msg.method == CheckerMethod.PUTFLAG and result.attack_info is not None:
            self.set_flag_id(
                msg.team_id, msg.current_round_id, msg.variant_id, result.attack_info
            )

        # for the record
        # TODO timestamp
        self.output.append(
            f"{msg.method:8s} #{msg.variant_id} for tick {msg.related_round_id} => {result.result}"
        )

    def _message(
        self,
        team_id: int,
        tick: int,
        method: CheckerMethod,
        *,
        variant_id: int = 0,
        related_tick: int | None = None,
    ) -> CheckerTaskMessage:
        try:
            tick_length = self.get_tick_duration(tick)
        except ValueError:
            tick_length = 60
        msg = CheckerTaskMessage(
            task_id=self.get_fresh_task_id(),
            method=method,
            address=config.NETWORK.team_id_to_vulnbox_ip(team_id),
            team_id=team_id,
            team_name=f"#{team_id}",
            current_round_id=tick,
            related_round_id=related_tick or tick,
            variant_id=variant_id,
            timeout=int(config.RUNNER.eno.timeout * 1000),
            round_length=tick_length * 1000,
            # unused, set later
            flag=None,
            task_chain_id="",
        )
        match method:
            case CheckerMethod.PUTFLAG | CheckerMethod.GETFLAG:
                msg.task_chain_id = f"flag_s{self.service_id}_r{msg.related_round_id}_t{team_id}_i{variant_id}"
                msg.flag = self.get_flag(team_id, msg.related_round_id, variant_id)
            case CheckerMethod.PUTNOISE | CheckerMethod.GETNOISE:
                msg.task_chain_id = f"noise_s{self.service_id}_r{msg.related_round_id}_t{team_id}_i{variant_id}"
            case CheckerMethod.HAVOC:
                msg.task_chain_id = f"havoc_s{self.service_id}_r{msg.related_round_id}_t{team_id}_i{variant_id}"
            case CheckerMethod.EXPLOIT:
                msg.flag_hash = hashlib.sha256(
                    self.get_flag(team_id, tick, variant_id).encode()
                ).hexdigest()
                msg.flag_regex = get_flag_regex().pattern
                msg.attack_info = self.get_flag_id(team_id, tick, variant_id)

        return msg

    @staticmethod
    def gen_timeslots_flat(
        tick_length, checker_info, task_timeout_s
    ) -> tuple[list[float], list[float], list[float]]:
        total_tasks_count = (
            2 + config.RUNNER.eno.check_past_ticks
        ) * checker_info.flag_variants
        total_tasks_count += (
            2 * checker_info.noise_variants + checker_info.havoc_variants
        )
        constrained_task_count = (
            checker_info.flag_variants + checker_info.noise_variants
        )

        last_possible_start_offset = (
            tick_length - EnoCheckerRunner.TIME_BUFFER - task_timeout_s
        )

        task_start_interval = last_possible_start_offset / float(total_tasks_count)
        # print(f"[DBG] task_start_interval: {task_start_interval}")
        task_interval_start_offsets = [
            task_start_interval * i for i in range(total_tasks_count)
        ]

        # print("[DBG]", task_interval_start_offsets)
        # print("[DBG] Latest interval start (expected):", last_possible_start_offset - task_start_interval)
        # print("[DBG] Latest interval start (actual):", task_interval_start_offsets[-1])

        # Last task interval starts at last_possible_start_offset - task_start_interval
        # To be able to safely choose a slot the last early task has to be chosen in a interval
        # (task_timeout + task_start_interval) before
        latest_early_task_start_offset = (
            last_possible_start_offset - 2 * task_start_interval - task_timeout_s
        )
        earliest_late_task_start_offset = task_timeout_s + task_start_interval

        early_task_slots = task_interval_start_offsets[:constrained_task_count]
        late_task_slots = task_interval_start_offsets[-constrained_task_count:]
        unconstrained_slots = task_interval_start_offsets[
            constrained_task_count:-constrained_task_count
        ]

        assert latest_early_task_start_offset >= early_task_slots[-1]
        assert earliest_late_task_start_offset <= late_task_slots[0]
        assert (
            early_task_slots[0] + task_timeout_s + task_start_interval
            <= late_task_slots[0]
        )

        # print("[DBG] early_task_slots:", early_task_slots)
        # print("[DBG] unconstrained_slots:", unconstrained_slots)
        # print("[DBG] late_task_slots:", late_task_slots)

        EARLY_TASKS_TAGGED = [
            TaggedIntervalEntry(SlotType.EARLY, val, idx)
            for idx, val in enumerate(early_task_slots)
        ]
        UNCONSTRAINED_TAGGED = [
            TaggedIntervalEntry(SlotType.UNCONSTRAINED, val, idx)
            for idx, val in enumerate(unconstrained_slots)
        ]
        LATE_TASKS_TAGGED = [
            TaggedIntervalEntry(SlotType.LATE, val, idx)
            for idx, val in enumerate(late_task_slots)
        ]

        tagged_task_slots = (
            EARLY_TASKS_TAGGED + UNCONSTRAINED_TAGGED + LATE_TASKS_TAGGED
        )
        clearence_threshhold = task_timeout_s + task_start_interval

        def _valid_clearance(early_task, late_task):
            # print(early_task, late_task, late_task.offset - early_task.offset >= clearence_threshhold)
            return late_task.offset - early_task.offset >= clearence_threshhold

        def _try_perform_swap(
            current: TaggedIntervalEntry, swap_target: TaggedIntervalEntry
        ):
            if swap_target.entry_type is SlotType.UNCONSTRAINED:
                current.offset, swap_target.offset = swap_target.offset, current.offset

            if swap_target.entry_type is SlotType.EARLY:
                swap_target_late = LATE_TASKS_TAGGED[swap_target.idx]
                if _valid_clearance(current, swap_target_late):
                    current.offset, swap_target.offset = (
                        swap_target.offset,
                        current.offset,
                    )

            if swap_target.entry_type is SlotType.LATE:
                swap_target_early = EARLY_TASKS_TAGGED[swap_target.idx]
                if _valid_clearance(swap_target_early, current):
                    current.offset, swap_target.offset = (
                        swap_target.offset,
                        current.offset,
                    )

        for _ in range(20):
            for constrained_task_idx in range(constrained_task_count):
                early_task = EARLY_TASKS_TAGGED[constrained_task_idx]
                current_late_task = LATE_TASKS_TAGGED[early_task.idx]
                swap_late_task = random.choice(tagged_task_slots)

                # 1: Is this even a valid swap target?
                if _valid_clearance(early_task, swap_late_task):
                    _try_perform_swap(current_late_task, swap_late_task)

                late_task = LATE_TASKS_TAGGED[-constrained_task_idx - 1]
                current_early_task = EARLY_TASKS_TAGGED[late_task.idx]
                swap_early_task = random.choice(tagged_task_slots)
                if _valid_clearance(swap_early_task, late_task):
                    _try_perform_swap(current_early_task, swap_early_task)

        # print(f"[DBG] early_task_slots:", *EARLY_TASKS_TAGGED, sep="\n    ")
        # print(f"[DBG] unconstrained_slots:", *UNCONSTRAINED_TAGGED, sep="\n    ")
        # print(f"[DBG] late_task_slots:", *LATE_TASKS_TAGGED, sep="\n    ")

        early_late_task_slots = [
            (early.offset, late.offset)
            for early, late in zip(EARLY_TASKS_TAGGED, LATE_TASKS_TAGGED)
        ]
        unconstrained_start_offsets = [
            unconstrained.offset for unconstrained in UNCONSTRAINED_TAGGED
        ]

        # Shuffle the slots to start each task at a random
        random.shuffle(early_late_task_slots)
        random.shuffle(unconstrained_start_offsets)

        early_task_slots = [x[0] for x in early_late_task_slots]
        late_task_slots = [x[1] for x in early_late_task_slots]

        # Add jitter within the interval to each task
        early_task_delays = [
            random.random() * task_start_interval + i for i in early_task_slots
        ]
        late_task_delays = [
            random.random() * task_start_interval + i for i in late_task_slots
        ]
        unconstrained_task_delays = [
            random.random() * task_start_interval + i
            for i in unconstrained_start_offsets
        ]

        return (early_task_delays, late_task_delays, unconstrained_task_delays)

    @staticmethod
    def gen_timeslots_fallback(
        tick_length, checker_info, task_timeout_s
    ) -> tuple[list[float], list[float], list[float]]:
        unconstrained_task_count = (
            config.RUNNER.eno.check_past_ticks
        ) * checker_info.flag_variants + checker_info.havoc_variants
        constrained_task_count = (
            checker_info.flag_variants + checker_info.noise_variants
        )

        early_task_delays = [
            random.random() * 15 for _ in range(constrained_task_count)
        ]
        late_task_delays = [
            30 + random.random() * 10 for _ in range(constrained_task_count)
        ]
        unconstrained_task_delays = [
            random.random() * 40 for _ in range(unconstrained_task_count)
        ]

        return (early_task_delays, late_task_delays, unconstrained_task_delays)

    @staticmethod
    def gen_timeslots(
        tick, checker_info, task_timeout_s
    ) -> tuple[list[float], list[float], list[float]]:
        try:
            tick_length = EnoCheckerRunner.get_tick_duration(tick)
        except ValueError:
            tick_length = 60

        try:
            return EnoCheckerRunner.gen_timeslots_flat(
                tick_length, checker_info, task_timeout_s
            )
        except AssertionError:
            return EnoCheckerRunner.gen_timeslots_fallback(
                tick_length, checker_info, task_timeout_s
            )

    async def execute_checker_async(self, team_id: int, tick: int) -> CheckerRunOutput:
        self.reset()
        info = await self.get_service_info()

        tasks = []
        timeslots = self.gen_timeslots(tick, info, 15)
        early_slots, late_slots, unconstrained_slots = timeslots
        early_slots_iter = iter(early_slots)
        late_slots_iter = iter(late_slots)
        unconstrained_slots_iter = iter(unconstrained_slots)

        async with self._session() as session:
            for variant_id in range(info.flag_variants):
                tasks.append(
                    self._process_message_with_jitter(
                        session,
                        self._message(
                            team_id, tick, CheckerMethod.PUTFLAG, variant_id=variant_id
                        ),
                        next(early_slots_iter),
                    )
                )
                tasks.append(
                    self._process_message_with_jitter(
                        session,
                        self._message(
                            team_id, tick, CheckerMethod.GETFLAG, variant_id=variant_id
                        ),
                        next(late_slots_iter),
                    )
                )
                for i in range(1, config.RUNNER.eno.check_past_ticks + 1):
                    # We start at tick 1, don't allow OOB accesses!
                    if tick - i <= 0:
                        break
                    tasks.append(
                        self._process_message_with_jitter(
                            session,
                            self._message(
                                team_id,
                                tick,
                                CheckerMethod.GETFLAG,
                                variant_id=variant_id,
                                related_tick=tick - i,
                            ),
                            next(unconstrained_slots_iter),
                        )
                    )

            for variant_id in range(info.noise_variants):
                tasks.append(
                    self._process_message_with_jitter(
                        session,
                        self._message(
                            team_id, tick, CheckerMethod.PUTNOISE, variant_id=variant_id
                        ),
                        next(early_slots_iter),
                    )
                )
                tasks.append(
                    self._process_message_with_jitter(
                        session,
                        self._message(
                            team_id, tick, CheckerMethod.GETNOISE, variant_id=variant_id
                        ),
                        next(late_slots_iter),
                    )
                )

            for variant_id in range(info.havoc_variants):
                tasks.append(
                    self._process_message_with_jitter(
                        session,
                        self._message(
                            team_id, tick, CheckerMethod.HAVOC, variant_id=variant_id
                        ),
                        next(unconstrained_slots_iter),
                    )
                )

            await asyncio.gather(*tasks)

        messages = (
            self.messages.values() if self.messages else self.recovery_messages.values()
        )
        self.output.sort()
        return CheckerRunOutput(
            self.status,
            message="\n".join(set(messages)),
            output="\n".join(self.output),
            data=self.custom_results,
        )

    async def _process_message_with_jitter(
        self, session: ClientSession, msg: CheckerTaskMessage, delay: float
    ) -> None:
        await asyncio.sleep(delay)
        result = await self._query(session, msg)
        self._handle_result(msg, result)
