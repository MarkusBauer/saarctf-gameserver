import asyncio
import base64
import hashlib
import hmac
import random
import struct
import traceback
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import ClassVar, Any

import jsons
from aiohttp.client import ClientSession, ClientTimeout
from enochecker_core import CheckerTaskMessage, CheckerResultMessage, CheckerMethod, CheckerTaskResult, CheckerInfoMessage

from saarctf_commons.config import config
from saarctf_commons.redis import get_redis_connection
from checker_runner.checker_execution import CheckerRunner, CheckerRunOutput
from gamelib import MAC_LENGTH, FLAG_REGEX


class AsyncCheckerRunner(CheckerRunner, ABC):
    def execute_checker(self, team_id: int, tick: int) -> CheckerRunOutput:
        return asyncio.run(self.execute_checker_async(team_id, tick))

    @abstractmethod
    async def execute_checker_async(self, team_id: int, tick: int) -> CheckerRunOutput:
        raise NotImplementedError


class EnoCheckerRunner(AsyncCheckerRunner):
    def __init__(self, service_id: int, package: str, script: str, cfg: dict | None) -> None:
        super().__init__(service_id, package, script, cfg)
        self.url = self.cfg['url']
        self.custom_results: dict[str | int, Any] = {}
        self.output: list[str] = []
        self.messages: set[str] = set()
        self.status: str = "SUCCESS"  # TODO convert to enum in the future

    def reset(self) -> None:
        self.custom_results = {}
        self.output = []
        self.messages = set()
        self.status = "SUCCESS"

    _service_info_cache: ClassVar[dict[str, CheckerInfoMessage]] = {}

    async def get_service_info(self) -> CheckerInfoMessage:
        if self.url in self._service_info_cache:
            return self._service_info_cache[self.url]
        async with self._session() as session, session.get(self.url + '/service') as response:
            if response.status != 200:
                raise Exception(f'Info request {response.url} returned {response.status}')
            cim: CheckerInfoMessage = jsons.loads(await response.text(), CheckerInfoMessage, key_transformer=jsons.KEY_TRANSFORMER_SNAKECASE,
                                                  strict=True)
        self._service_info_cache[self.url] = cim
        return cim

    @staticmethod
    @lru_cache()
    def get_tick_duration(tick: int) -> int:
        with get_redis_connection() as conn:
            v = conn.get(f'round:{tick}:time')
            if not v:
                raise ValueError()
            return int(v.decode())

    @staticmethod
    def get_fresh_task_id() -> int:
        with get_redis_connection() as conn:
            return conn.incr('runner:eno:task_id', 1)

    def get_flag(self, team_id: int, tick: int, payload: int = 0) -> str:
        data = struct.pack('<HHHH', tick & 0xffff, team_id, self.service_id, payload)
        mac = hmac.new(config.SECRET_FLAG_KEY, data, hashlib.sha256).digest()[:MAC_LENGTH]
        flag = base64.b64encode(data + mac).replace(b'+', b'-').replace(b'/', b'_')
        return 'SAAR{' + flag.decode('utf-8') + '}'

    def set_flag_id(self, team_id: int, tick: int, index: int, value: str) -> None:
        with get_redis_connection() as redis_conn:
            redis_conn.set(f'custom_flag_ids:{self.service_id}:{tick}:{team_id}:{index}', value)

    def get_flag_id(self, team_id: int, tick: int, index: int) -> str | None:
        with get_redis_connection() as redis_conn:
            value = redis_conn.get(f'custom_flag_ids:{self.service_id}:{tick}:{team_id}:{index}')
            return value.decode() if value is not None else None

    def _session(self) -> ClientSession:
        return ClientSession(timeout=ClientTimeout(total=20))

    async def _query(self, session: ClientSession, msg: CheckerTaskMessage) -> CheckerResultMessage:
        try:
            json_msg = jsons.dumps(msg, use_enum_name=False, key_transformer=jsons.KEY_TRANSFORMER_CAMELCASE)
            async with session.post(self.url, data=json_msg, headers={'Content-Type': 'application/json'},
                                    timeout=ClientTimeout(msg.timeout / 1000 + 1)) as response:
                if response.status != 200:
                    raise Exception(f'Request to {response.url} returned with code {response.status}')
                json_response = await response.text()
                result: CheckerResultMessage = jsons.loads(json_response, CheckerResultMessage,
                                                           key_transformer=jsons.KEY_TRANSFORMER_SNAKECASE, strict=True)
                # TODO scoring: you can record stuff here to self.custom_result
                if msg.method == CheckerMethod.GETFLAG:
                    self.custom_results[msg.related_round_id] = result.result.value
                return result
        except TimeoutError:
            return CheckerResultMessage(CheckerTaskResult.INTERNAL_ERROR, message="TIMEOUT")
        except:
            self.output.append(traceback.format_exc())
            return CheckerResultMessage(CheckerTaskResult.INTERNAL_ERROR, message=None)

    def _handle_result(self, msg: CheckerTaskMessage, result: CheckerResultMessage) -> None:
        if result.message:
            self.messages.add(result.message)
        if result.result == CheckerTaskResult.INTERNAL_ERROR:
            self.status = "CRASHED" if result.message != 'TIMEOUT' else "TIMEOUT"
        elif self.status in ("SUCCESS", "RECOVERING") and result.result != CheckerTaskResult.OK and msg.current_round_id != msg.related_round_id:
            self.status = "RECOVERING"
        elif self.status in ("SUCCESS", "RECOVERING") and result.result == CheckerTaskResult.MUMBLE:
            self.status = "MUMBLE"
        elif self.status in ("SUCCESS", "RECOVERING") and result.result == CheckerTaskResult.OFFLINE:
            self.status = "OFFLINE"

        # store flag IDs / attack info
        if msg.method == CheckerMethod.PUTFLAG and result.attack_info is not None:
            self.set_flag_id(msg.team_id, msg.current_round_id, msg.variant_id, result.attack_info)

        # for the record
        # TODO timestamp
        self.output.append(f'{msg.method:8s} #{msg.variant_id} for tick {msg.related_round_id} => {result.result}')

    def _message(self, team_id: int, tick: int, method: CheckerMethod, *,
                 variant_id: int = 0, related_tick: int | None = None) -> CheckerTaskMessage:
        try:
            tick_length = self.get_tick_duration(tick)
        except ValueError:
            tick_length = 60
        msg = CheckerTaskMessage(
            task_id=self.get_fresh_task_id(),
            method=method,
            address=config.NETWORK.team_id_to_vulnbox_ip(team_id),
            team_id=team_id,
            team_name=f'#{team_id}',
            current_round_id=tick,
            related_round_id=related_tick or tick,
            variant_id=variant_id,
            timeout=int(config.RUNNER.eno.timeout * 1000),
            round_length=tick_length * 1000,

            # unused, set later
            flag=None,
            task_chain_id=''
        )
        match method:
            case CheckerMethod.PUTFLAG | CheckerMethod.GETFLAG:
                msg.task_chain_id = f"flag_s{self.service_id}_r{tick}_t{team_id}_i{variant_id}"
                msg.flag = self.get_flag(team_id, tick, variant_id)
            case CheckerMethod.PUTNOISE | CheckerMethod.GETNOISE:
                msg.task_chain_id = f"noise_s{self.service_id}_r{tick}_t{team_id}_i{variant_id}"
            case CheckerMethod.HAVOC:
                msg.task_chain_id = f"havoc_s{self.service_id}_r{tick}_t{team_id}_i{variant_id}"
            case CheckerMethod.EXPLOIT:
                msg.flag_hash = hashlib.sha256(self.get_flag(team_id, tick, variant_id).encode()).hexdigest()
                msg.flag_regex = FLAG_REGEX.pattern
                msg.attack_info = self.get_flag_id(team_id, tick, variant_id)

        return msg

    async def execute_checker_async(self, team_id: int, tick: int) -> CheckerRunOutput:
        self.reset()
        info = await self.get_service_info()

        tasks = []

        async with self._session() as session:
            for variant_id in range(info.flag_variants):
                tasks.append(self._process_message_with_jitter(
                    session,
                    self._message(team_id, tick, CheckerMethod.PUTFLAG, variant_id=variant_id),
                    random.random() * 15
                ))
                tasks.append(self._process_message_with_jitter(
                    session,
                    self._message(team_id, tick, CheckerMethod.GETFLAG, variant_id=variant_id),
                    30 + random.random() * 10
                ))
                for i in range(1, config.RUNNER.eno.check_past_ticks):
                    if tick - i <= 0:
                        break
                    tasks.append(self._process_message_with_jitter(
                        session,
                        self._message(team_id, tick, CheckerMethod.GETFLAG, variant_id=variant_id, related_tick=tick - i),
                        random.random() * 40
                    ))

            for variant_id in range(info.noise_variants):
                tasks.append(self._process_message_with_jitter(
                    session,
                    self._message(team_id, tick, CheckerMethod.PUTNOISE, variant_id=variant_id),
                    random.random() * 15
                ))
                tasks.append(self._process_message_with_jitter(
                    session,
                    self._message(team_id, tick, CheckerMethod.GETNOISE, variant_id=variant_id),
                    30 + random.random() * 10
                ))

            for variant_id in range(info.havoc_variants):
                tasks.append(self._process_message_with_jitter(
                    session,
                    self._message(team_id, tick, CheckerMethod.HAVOC, variant_id=variant_id),
                    random.random() * 40
                ))

            await asyncio.gather(*tasks)

        return CheckerRunOutput(self.status, message='\n'.join(self.messages), output='\n'.join(self.output), data=self.custom_results)

    async def _process_message_with_jitter(self, session: ClientSession, msg: CheckerTaskMessage, delay: float) -> None:
        await asyncio.sleep(delay)
        result = await self._query(session, msg)
        self._handle_result(msg, result)
