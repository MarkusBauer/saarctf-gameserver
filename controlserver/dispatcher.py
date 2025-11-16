"""
- Dispatches the checker scripts (into the message queue)
- Revoke pending checker script at the end of the tick
- Collect checker script results (in case of failure / timeout) and stores them in the database


For each tick, a single "Task Group" is created, which can be used to manage all tasks of one tick together.

"""

import itertools
import json
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import TypeAlias, Any

from billiard.exceptions import WorkerLostError
from celery import group, states, Task
from celery.canvas import Signature
from celery.result import GroupResult, AsyncResult
from sqlalchemy import func
from sqlalchemy.orm import Session

from checker_runner.runner import celery_worker
from controlserver.flag_id_file import FlagIDFileGenerator
from controlserver.logger import log
from controlserver.models import Team, Service, LogMessage, CheckerResult, db_session, db_session_2
from controlserver.utils.import_factory import ImportFactory
from saarctf_commons.config import config
from saarctf_commons.redis import get_redis_connection

DispatchRef: TypeAlias = str
Tick: TypeAlias = int
TeamID: TypeAlias = int
ServiceID: TypeAlias = int


class GenericDispatcher(ABC):
    @abstractmethod
    def _dispatch(self, combinations: list[tuple[Team, Service, Tick]], **overrides: Any) -> DispatchRef:
        raise NotImplementedError()

    @abstractmethod
    def _revoke(self, ref: DispatchRef) -> None:
        raise NotImplementedError()

    @abstractmethod
    def _collect(self, ref: DispatchRef, combinations: list[tuple[TeamID, ServiceID, Tick]]) -> None:
        raise NotImplementedError()

    def dispatch_checker_scripts(self, tick: Tick) -> None:
        with db_session_2() as session:
            with get_redis_connection() as redis:
                if config.DISPATCHER_CHECK_VPN_STATUS:
                    teams = session.query(Team) \
                        .filter((Team.vpn_connected == True) | (Team.vpn2_connected == True) | (Team.wg_vulnbox_connected == True)) \
                        .all()
                else:
                    teams = session.query(Team).all()
                services = session.query(Service).order_by(Service.id).filter(Service.checker_enabled == True).all()
                combinations = [(t, s, tick) for t, s in itertools.product(teams, services)]
                if len(combinations) > 0:
                    random.shuffle(combinations)
                    ref = self._dispatch(combinations)
                    combination_ids = [(team.id, service.id, tick) for team, service, tick in combinations]
                    redis.set(f'dispatcher:order:{tick}', json.dumps(combination_ids))
                    redis.set(f'dispatcher:ref:{tick}', ref)
                    FlagIDFileGenerator().generate_and_save(teams, services, tick)

    def dispatch_test_script(self, team: Team, service: Service, tick: Tick, package: str | None = None) -> tuple[DispatchRef, CheckerResult]:
        session = db_session()  # operation called from cp only
        # cleanup database
        session.query(CheckerResult) \
            .filter(CheckerResult.team_id == team.id, CheckerResult.service_id == service.id, CheckerResult.tick == tick) \
            .delete()
        result = CheckerResult(team_id=team.id, service_id=service.id, tick=tick, status='PENDING')
        session.add(result)
        # dispatch
        ref = self._dispatch([(team, service, tick)], package=package, route=service.checker_route or 'tests')
        result.celery_id = ref
        session.commit()
        return ref, result

    def dispatch_test_script_many(self, team: Team, service: Service, ticks: list[Tick], *,
                                  package: str | None = None, route: str | None = None) -> DispatchRef:
        return self._dispatch([(team, service, tick) for tick in ticks], package=package, route=route)

    def get_checker_results(self, tick: Tick) -> list[CheckerResult]:
        """
        :param tick:
        :return: All the results of a given tick
        """
        return CheckerResult.query.filter(CheckerResult.tick == tick).all()

    def get_tick_combinations(self, tick: Tick) -> list[tuple[TeamID, ServiceID]]:
        with get_redis_connection() as redis:
            data = redis.get(f'dispatcher:order:{tick}')
            if data:
                return [(t, s) for t, s, _ in json.loads(data)]
            return []

    def revoke_checker_scripts(self, tick: Tick) -> None:
        with get_redis_connection() as redis:
            ref: bytes | None = redis.get(f'dispatcher:ref:{tick}')
        if ref:
            self._revoke(ref.decode())

    def collect_checker_results(self, tick: Tick) -> None:
        if tick <= 0:
            return

        with get_redis_connection() as redis:
            ref: bytes | None = redis.get(f'dispatcher:ref:{tick}')
            data = redis.get(f'dispatcher:order:{tick}')
            combinations = json.loads(data) if data else []

        if ref:
            self._collect(ref.decode(), combinations)

        with db_session_2() as session:
            # Log checker script errors
            # print(stats)
            crashed = session.query(CheckerResult.service_id, func.count()) \
                .filter(CheckerResult.tick == tick).filter(CheckerResult.status == 'CRASHED') \
                .group_by(CheckerResult.service_id).all()
            for service_id, count in crashed:
                service = session.query(Service).filter(Service.id == service_id).first()
                log('dispatcher', f'Checker scripts for {service.name if service else service_id} produced {count} errors in tick {tick}',
                    level=LogMessage.ERROR)

    def collect_test_results_many(self, team: Team, service: Service, ticks: list[Tick], ref: DispatchRef) -> None:
        if ref:
            self._collect(ref, [(team.id, service.id, tick) for tick in ticks])


class CeleryDispatcher(GenericDispatcher):
    def _dispatch(self, combinations: list[tuple[Team, Service, Tick]], **overrides: Any) -> DispatchRef:
        taskgroup_sig: Signature = group([self._create_celery_task(team, service, tick, **overrides) for team, service, tick in combinations])
        taskgroup: GroupResult = taskgroup_sig.apply_async()
        taskgroup.save()
        return taskgroup.id

    def _create_celery_task(self, team: Team, service: Service, tick: int, package: str | None = None, route: str | None = None, **kwargs: Any) -> Task:
        if service.checker_subprocess:
            run_func = celery_worker.run_checkerscript_external
            timeout = service.checker_timeout + 5
        else:
            run_func = celery_worker.run_checkerscript
            timeout = service.checker_timeout
        return run_func.signature(
            (
                service.checker_runner,
                service.package if not package else package,
                service.checker_script,
                service.id,
                team.id,
                tick,
                service.runner_config,
            ),
            time_limit=timeout + 5, soft_time_limit=timeout,
            countdown=150 if service.checker_script == 'pendingtest' else None,
            queue=route or service.checker_route or 'celery',
            **kwargs
        )

    def _ref_to_group(self, ref: DispatchRef) -> GroupResult:
        return GroupResult.restore(ref, app=celery_worker.app)

    def _revoke(self, ref: DispatchRef) -> None:
        self._ref_to_group(ref).revoke()
        time.sleep(0.5)

    def _collect(self, ref: DispatchRef, combinations: list[tuple[TeamID, ServiceID, Tick]]) -> None:
        collect_time = time.time()
        taskgroup = self._ref_to_group(ref)

        with db_session_2() as session:
            stats = {states.SUCCESS: 0, states.STARTED: 0, states.REVOKED: 0, states.FAILURE: 0}
            if taskgroup and combinations:
                for (team_id, service_id, tick), result in zip(combinations, taskgroup.results):
                    status = self._handle_celery_result(session, team_id, service_id, tick, result)
                    stats[status] += 1
                session.commit()

                if combinations[0][2] >= 0:
                    self._issue_warnings(session, stats, combinations[0][2], collect_time)

    def _issue_warnings(self, session: Session, stats: dict, tick: Tick, collect_time: float) -> float:
        total = sum(stats.values())
        # Warning if time runs out
        if stats[states.REVOKED] > 0:
            log('dispatcher',
                'Not all checker scripts have been executed. {} / {} revoked, {} / {} still active'.format(
                    stats[states.REVOKED], total, stats[states.STARTED], total),
                level=LogMessage.WARNING)
        elif stats[states.STARTED] > 0:
            log('dispatcher', 'Not all checker scripts finished in time: {} / {} still active'.format(
                stats[states.STARTED], total), level=LogMessage.WARNING)
        else:
            last_finished = session.query(func.max(CheckerResult.finished)).filter(CheckerResult.tick == tick).scalar()
            if last_finished and collect_time - last_finished.timestamp() <= 3.5:
                log('dispatcher', 'Worker close to overload: Last checker script finished {:.1f} sec before deadline'.format(
                    collect_time - last_finished.timestamp()), level=LogMessage.WARNING)
            return collect_time - last_finished.timestamp()
        return 0.0

    def _handle_celery_result(self, session: Session, team_id: int, service_id: int, tick: Tick, result: AsyncResult) -> str:
        try:
            status = result.status
        except WorkerLostError:
            status = states.FAILURE
        if status == states.RETRY or status == states.PENDING:
            status = states.REVOKED
        if status == states.FAILURE:
            # timeout or critical (exception)
            r = result.get(propagate=False)
            is_timeout = isinstance(r, Exception) and 'TimeLimitExceeded' in repr(type(r))
            db_result = CheckerResult(tick=tick, service_id=service_id, team_id=team_id, celery_id=result.id)
            if is_timeout:
                db_result.status = 'TIMEOUT'
            else:
                db_result.status = 'CRASHED'
                old_result = session.query(CheckerResult) \
                    .filter(CheckerResult.tick == tick, CheckerResult.service_id == service_id, CheckerResult.team_id == team_id) \
                    .first()
                if old_result and old_result.output:
                    db_result.output = old_result.output + '\n' + repr(type(r)) + ' ' + repr(r)
                else:
                    db_result.output = repr(type(r)) + ' ' + repr(r)
            session.execute(CheckerResult.upsert().values(db_result.props_dict()))
        elif status == states.STARTED:
            # result is here too late
            db_result = CheckerResult(tick=tick, service_id=service_id, team_id=team_id, celery_id=result.id)
            db_result.status = 'TIMEOUT'
            db_result.message = 'Service not checked completely'
            db_result.output = 'Still running after tick end...'
            db_result.run_over_time = True
            session.execute(CheckerResult.upsert().values(db_result.props_dict()))
        elif status == states.REVOKED:
            # never tried to run this task
            db_result = CheckerResult(tick=tick, service_id=service_id, team_id=team_id, celery_id=result.id)
            db_result.status = 'REVOKED'
            db_result.message = 'Service not checked'
            db_result.output = 'Not started before the tick ended'
            session.execute(CheckerResult.upsert().values(db_result.props_dict()))
        elif status == states.SUCCESS:
            result.forget()
        return status


class DelayingCeleryDispatcher(CeleryDispatcher):
    def _dispatch(self, combinations: list[tuple[Team, Service, Tick]], **overrides: Any) -> DispatchRef:
        # special handling only if all combinations are from one tick
        ticks = set(t for _, _, t in combinations)
        if len(ticks) != 1 or (tick := next(iter(ticks))) < 0:
            return super()._dispatch(combinations, **overrides)

        # ... and this tick has times, and we're in this tick atm
        from controlserver.timer import Timer
        now = time.time()
        if tick != Timer.current_tick or Timer.tick_start is None or Timer.tick_end is None or not (Timer.tick_start <= now < Timer.tick_end):
            return super()._dispatch(combinations, **overrides)
        # sanity check: we should not delay things for too long
        if Timer.tick_end - now >= 900:
            return super()._dispatch(combinations, **overrides)

        # get the "spreading" right
        counts: dict[int, int] = {}  # ID => # elements
        factors: dict[int, int] = {}  # ID => max delay time
        for _, service, _ in combinations:
            counts[service.id] = counts.get(service.id, 0) + 1
            if service.id not in factors:
                factors[service.id] = Timer.tick_end - Timer.tick_start - service.checker_timeout - (15 if service.checker_subprocess else 10)

        # build tasks with delay
        tasks = []
        seen = {k: 0 for k in counts.keys()}
        start = datetime.fromtimestamp(Timer.tick_start, timezone.utc)
        for team, service, tick in combinations:
            delay = factors[service.id] * seen[service.id] / counts[service.id]
            if delay < 3:
                delay = 0
            tasks.append(self._create_celery_task(team, service, tick, eta=start + timedelta(seconds=delay), **overrides))
            seen[service.id] += 1

        # task to taskgroup, as usual
        taskgroup_sig: Signature = group(tasks)
        taskgroup: GroupResult = taskgroup_sig.apply_async()
        taskgroup.save()
        return taskgroup.id


class DispatcherFactory(ImportFactory[GenericDispatcher]):
    base_class = GenericDispatcher
    _singletons: dict[str, GenericDispatcher] = {}

    @classmethod
    def build(cls, name: str) -> GenericDispatcher:
        if name not in cls._singletons:
            cls._singletons[name] = cls.get_class(name)()
        return cls._singletons[name]
