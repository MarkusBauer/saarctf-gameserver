import argparse
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import cast

from sqlalchemy import func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.logging_utils import setup_script_logging
from saarctf_commons.config import config, load_default_config
from saarctf_commons.redis import NamedRedisConnection
from controlserver.models import db_session_2, Team, Service, CheckerResult, init_database
from controlserver.dispatcher import Dispatcher
from checker_runner.runner import celery_worker
from scripts.worker_pool_increase import FlowerInterface

"""
ARGUMENTS: --team X --service Y [ -n 1,2,3,4... ]
"""


def timings_from_message(result: CheckerResult) -> tuple[float | None, float | None, float | None]:
    if result.output is None:
        return None, None, None
    # this is ugly as fuck, but it works
    m = re.search(r'\[([ \d.]{6})] \n \n----- store_flags\(', result.output, re.MULTILINE)
    if m is not None:
        ti = float(m.group(1).strip())
        m = re.search(r'\[([ \d.]{6})] \n \n----- retrieve_flags\(', result.output, re.MULTILINE)
        if m is not None:
            ts = float(m.group(1).strip())
            tr = cast(float, result.time) - ti - ts if result.time is not None else None
            return ti, ts, tr
        return ti, None, None
    return None, None, None


@dataclass
class TimeStats:
    min: float = 0.0
    max: float = 0.0
    avg: float = 0.0

    @classmethod
    def from_times(cls, times: list[float]) -> 'TimeStats':
        if len(times) == 0:
            return TimeStats()
        return TimeStats(
            min=min(times),
            max=max(times),
            avg=sum(times) / len(times),
        )

    def __str__(self) -> str:
        return f'{self.avg:.1f}s ({self.min:.1f}s - {self.max:.1f}s)'


@dataclass
class LoadTestResult:
    n: int
    c: int
    results: list[CheckerResult]

    # auto-computed
    success: int = 0
    times: TimeStats = field(default_factory=TimeStats)
    times_integrity: TimeStats = field(default_factory=TimeStats)
    times_store: TimeStats = field(default_factory=TimeStats)
    times_retrieve: TimeStats = field(default_factory=TimeStats)
    walltime: float = 0.0

    def __post_init__(self) -> None:
        integrity_times = []
        store_times = []
        retrieve_times = []
        for result in self.results:
            if result.status == 'SUCCESS':
                self.success += 1
            ti, ts, tr = timings_from_message(result)
            if ti is not None:
                integrity_times.append(ti)
            if ts is not None:
                store_times.append(ts)
            if tr is not None:
                retrieve_times.append(tr)

        self.times = TimeStats.from_times([cast(float, result.time) for result in self.results])
        self.times_integrity = TimeStats.from_times(integrity_times)
        self.times_store = TimeStats.from_times(store_times)
        self.times_retrieve = TimeStats.from_times(retrieve_times)
        walltime_start = min(result.finished - timedelta(seconds=cast(float, result.time)) for result in self.results
                             if result.finished is not None and result.time is not None)
        walltime_end = min(result.finished for result in self.results if result.finished is not None)
        self.walltime = (walltime_end - walltime_start).total_seconds()

    def to_line(self) -> str:
        return f'n={n}  success={self.success}/{len(self.results)}  runtime={self.times}'


class LoadTester:
    def __init__(self, team_id: int, service_id: int, concurrency: int) -> None:
        with db_session_2() as session:
            team = session.query(Team).get(team_id)
            service = session.query(Service).get(service_id)
            session.expunge_all()
        if team is None:
            raise ValueError(f'Invalid team ID: {team_id}')
        if service is None:
            raise ValueError(f'Invalid service ID: {service_id}')

        self.dispatcher = Dispatcher()
        self.concurrency = concurrency
        self.team: Team = team
        self.service: Service = service

    def get_meta(self) -> list[list[str]]:
        return [
            ['service', self.service.name],
            ['package', self.service.package or ''],
            ['timeout', f'{self.service.checker_timeout:2d}s'],
            ['subprocess', str(self.service.checker_subprocess)],
            ['concurrency', str(self.concurrency)],
        ]

    def _get_min_tick(self) -> int:
        with db_session_2() as session:
            min_tick: int | None = session.query(func.min(CheckerResult.tick)) \
                .filter(CheckerResult.team_id == self.team.id) \
                .filter(CheckerResult.service_id == self.service.id) \
                .scalar()
            return min_tick if min_tick is not None and min_tick < 0 else 0

    def run(self, n: int) -> LoadTestResult:
        min_tick = self._get_min_tick()
        ticks = list(range(min_tick - n, min_tick))
        taskgroup = self.dispatcher.dispatch_test_script_many(self.team, self.service, ticks, route='loadtest')
        taskgroup.join()
        self.dispatcher.collect_test_results_many(self.team, self.service, ticks, taskgroup)
        with db_session_2() as session:
            results = session.query(CheckerResult) \
                .filter(CheckerResult.team_id == self.team.id) \
                .filter(CheckerResult.service_id == self.service.id) \
                .filter(CheckerResult.tick.in_(ticks)) \
                .all()
            session.expunge_all()
            return LoadTestResult(n, self.concurrency, results)


def results_to_table(results: list[LoadTestResult]) -> list[list[str]]:
    table = [[
        ' n ', ' c ', 'success', 'avg.time', 'min.time', 'max.time', 'tasks/s',
        '',
        'integrity', '(max)', 'store', '(max)', 'retrieve', '(max)'
    ]]
    for result in results:
        table.append([
            f'{result.n:3d}',
            f'{min(result.n, result.c):3d}',
            f'{result.success * 100 / len(result.results):.1f}%',
            f'{result.times.avg:4.1f}s',
            f'{result.times.min:4.1f}s',
            f'{result.times.max:4.1f}s',
            f'{len(result.results) / result.walltime:7.1f}',

            '',

            f'{result.times_integrity.avg:4.1f}s',
            f'{result.times_integrity.max:4.1f}s',
            f'{result.times_store.avg:4.1f}s',
            f'{result.times_store.max:4.1f}s',
            f'{result.times_retrieve.avg:4.1f}s',
            f'{result.times_retrieve.max:4.1f}s',
        ])
    return table


def format_table(rows: list[list[str]], hline_after: list[int]) -> str:
    max_width: list[int] = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    hline: str = '-' * (sum(max_width) + 3 * len(max_width) - 2)
    lines: list[str] = [hline]
    for i, row in enumerate(rows):
        lines.append(' | '.join(cell.ljust(max_width[j]) for j, cell in enumerate(row)))
        if i in hline_after:
            lines.append(hline)
    lines.append(hline)
    return '\n'.join(lines)


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    setup_script_logging('loadtest_service')
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))
    init_database()

    parser = argparse.ArgumentParser()
    parser.add_argument('--team', type=int, required=True, help='Team ID to load-test')
    parser.add_argument('--service', type=int, required=True, help='Service ID to load-test')
    parser.add_argument('-n', type=str, default='1,2,4,8,16,32,48,64', help='Number of tasks (comma separated)')
    args = parser.parse_args()
    ns = [int(n.strip()) for n in args.n.split(',')]

    celery_worker.init()
    flower = FlowerInterface()
    concurrency = flower.get_worker_pool_size_for_queue('loadtest')

    lt = LoadTester(args.team, args.service, concurrency)
    logging.info(f'Testing service #{lt.service.id} {lt.service.name!r} against team #{lt.team.id} {lt.team.name!r}:')
    logging.info(f'Checks: {ns}  (max. concurrency: {concurrency})')
    results = []
    for n in ns:
        logging.info(f'Running load test with {n} instances ...')
        result = lt.run(int(n))
        results.append(result)
        logging.info(f'Complete: {result.to_line()}')
        time.sleep(0.25)

    print(format_table(lt.get_meta(), []))
    print(format_table(results_to_table(results), [0]))
