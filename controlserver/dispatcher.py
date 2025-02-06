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
from saarctf_commons.config import config
from saarctf_commons.redis import get_redis_connection


class Dispatcher:
    # Singleton (for better cache usage)
    default: 'Dispatcher' = None  # type: ignore[assignment]

    def __init__(self) -> None:
        # caches, also stored in Redis
        self.tick_taskgroups: dict[int, GroupResult] = {}
        self.tick_combination_ids: dict[int, list[tuple[int, int]]] = {}

    def dispatch_checker_scripts(self, tick: int) -> None:
        with db_session_2() as session:
            with get_redis_connection() as redis:
                if config.DISPATCHER_CHECK_VPN_STATUS:
                    teams = session.query(Team) \
                        .filter((Team.vpn_connected == True) | (Team.vpn2_connected == True) | (Team.wg_vulnbox_connected == True)) \
                        .all()
                else:
                    teams = session.query(Team).all()
                services = session.query(Service).order_by(Service.id).filter(Service.checker_enabled == True).all()
                combinations = list(itertools.product(teams, services))
                if len(combinations) > 0:
                    random.shuffle(combinations)
                    taskgroup_sig: Signature = group([self.__prepare_checker_script(team, service, tick) for team, service in combinations])
                    taskgroup: GroupResult = taskgroup_sig.apply_async()
                    taskgroup.save()
                    self.tick_taskgroups[tick] = taskgroup
                    combination_ids = [(team.id, service.id) for team, service in combinations]
                    self.tick_combination_ids[tick] = combination_ids
                    redis.set('dispatcher:taskgroup:{}:order'.format(tick), json.dumps(combination_ids))
                    redis.set('dispatcher:taskgroup:{}:id'.format(tick), taskgroup.id)
                    FlagIDFileGenerator().generate_and_save(teams, services, tick)

    def __prepare_checker_script(self, team: Team, service: Service, tick: int, package: str | None = None, route: str | None = None) -> Task:
        if service.checker_subprocess:
            run_func = celery_worker.run_checkerscript_external
            timeout = service.checker_timeout + 5
        else:
            run_func = celery_worker.run_checkerscript
            timeout = service.checker_timeout
        return run_func.signature(
            (
                service.package if not package else package,
                service.checker_script,
                service.id,
                team.id,
                tick
            ),
            time_limit=timeout + 5, soft_time_limit=timeout,
            countdown=150 if service.checker_script == 'pendingtest' else None,
            queue=route or service.checker_route or 'celery'
        )

    def dispatch_test_script(self, team: Team, service: Service, tick: int, package: str | None = None) -> tuple[AsyncResult, CheckerResult]:
        session = db_session()  # operation called from cp only
        # cleanup database
        session.query(CheckerResult) \
            .filter(CheckerResult.team_id == team.id, CheckerResult.service_id == service.id, CheckerResult.tick == tick) \
            .delete()
        result = CheckerResult(team_id=team.id, service_id=service.id, tick=tick, status='PENDING')
        session.add(result)
        # dispatch
        sig = self.__prepare_checker_script(team, service, tick, package, route=service.checker_route or 'tests')
        task: AsyncResult = sig.apply_async()
        result.celery_id = task.id
        session.commit()
        return task, result

    def dispatch_test_script_many(self, team: Team, service: Service, ticks: list[int], *,
                                  package: str | None = None, route: str | None = None) -> GroupResult:
        taskgroup_sig: Signature = group([self.__prepare_checker_script(team, service, tick, package=package, route=route) for tick in ticks])
        taskgroup: GroupResult = taskgroup_sig.apply_async()
        taskgroup.save()
        return taskgroup

    def get_tick_taskgroup(self, tick: int) -> GroupResult | None:
        if tick not in self.tick_taskgroups:
            redis = get_redis_connection()
            group_id = redis.get(f'dispatcher:taskgroup:{tick}:id')
            if not group_id:
                return None
            self.tick_taskgroups[tick] = GroupResult.restore(group_id, app=celery_worker.app)
        return self.tick_taskgroups[tick]

    def get_tick_combinations(self, tick) -> list[tuple[int, int]] | None:
        """
        :param tick:
        :return: The order in which the tasks have been dispatched in this tick. None if tasks aren't fully dispatched yet.
        """
        if tick not in self.tick_combination_ids:
            redis = get_redis_connection()
            data = redis.get('dispatcher:taskgroup:{}:order'.format(tick))
            if not data:
                return None
            self.tick_combination_ids[tick] = json.loads(data)
        return self.tick_combination_ids[tick]

    def revoke_checker_scripts(self, tick: int) -> None:
        taskgroup = self.get_tick_taskgroup(tick)
        if taskgroup:
            taskgroup.revoke()
        time.sleep(0.5)

    def collect_checker_results(self, tick: int) -> None:
        if tick <= 0:
            return

        taskgroup = self.get_tick_taskgroup(tick)
        combinations = self.get_tick_combinations(tick)
        collect_time = time.time()

        with db_session_2() as session:
            stats = {states.SUCCESS: 0, states.STARTED: 0, states.REVOKED: 0, states.FAILURE: 0}
            if taskgroup and combinations:
                for (team_id, service_id), result in zip(combinations, taskgroup.results):
                    status = self.__collect_checker_result(session, team_id, service_id, tick, result)
                    stats[status] += 1
                session.commit()

                # Warning if time runs out
                if stats[states.REVOKED] > 0:
                    log('dispatcher',
                        'Not all checker scripts have been executed. {} / {} revoked, {} / {} still active'.format(
                            stats[states.REVOKED], len(combinations), stats[states.STARTED], len(combinations)),
                        level=LogMessage.WARNING)
                elif stats[states.STARTED] > 0:
                    log('dispatcher', 'Not all checker scripts finished in time: {} / {} still active'.format(
                        stats[states.STARTED], len(combinations)), level=LogMessage.WARNING)
                else:
                    last_finished = session.query(func.max(CheckerResult.finished)).filter(CheckerResult.tick == tick).scalar()
                    if last_finished and collect_time - last_finished.timestamp() <= 3.5:
                        log('dispatcher', 'Worker close to overload: Last checker script finished {:.1f} sec before deadline'.format(
                            collect_time - last_finished.timestamp()), level=LogMessage.WARNING)

            # Log checker script errors
            # print(stats)
            crashed = session.query(CheckerResult.service_id, func.count()) \
                .filter(CheckerResult.tick == tick).filter(CheckerResult.status == 'CRASHED') \
                .group_by(CheckerResult.service_id).all()
            for service_id, count in crashed:
                service = session.query(Service).filter(Service.id == service_id).first()
                log('dispatcher', f'Checker scripts for {service.name if service else service_id} produced {count} errors in tick {tick}',
                    level=LogMessage.ERROR)

    def __collect_checker_result(self, session: Session, team_id: int, service_id: int, tick: int, result: AsyncResult) -> str:
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

    def collect_test_results_many(self, team: Team, service: Service, ticks: list[int], taskgroup: GroupResult) -> dict[str, int]:
        with db_session_2() as session:
            stats = {states.SUCCESS: 0, states.STARTED: 0, states.REVOKED: 0, states.FAILURE: 0}
            for tick, result in zip(ticks, taskgroup.results):
                status = self.__collect_checker_result(session, team.id, service.id, tick, result)
                stats[status] += 1
            session.commit()
            return stats

    def get_checker_results(self, tick: int) -> list[CheckerResult]:
        """
        :param tick:
        :return: All the results of a given tick
        """
        return CheckerResult.query.filter(CheckerResult.tick == tick).all()


Dispatcher.default = Dispatcher()
