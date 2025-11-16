"""
Celery configuration (message queues) and code to run the checker scripts.
"""

import os
import resource
import subprocess
import sys
import time
from logging import Handler, NOTSET, getLogger, LogRecord
from typing import List, Any

import sqlalchemy
from celery import Celery, Task
from celery.local import PromiseProxy
from celery.signals import celeryd_after_setup
from kombu.common import Broadcast
from sqlalchemy import func

from checker_runner.checker_execution import process_needs_restart, set_process_needs_restart, CheckerRunOutput
from checker_runner.runners.factory import CheckerRunnerFactory
from controlserver.models import CheckerResult, db_session, init_database, db_session_2
from saarctf_commons.config import config, load_default_config
from saarctf_commons.db_utils import retry_on_sql_error
from saarctf_commons.redis import NamedRedisConnection, get_redis_connection


@celeryd_after_setup.connect
def worker_init(sender: Any, instance: Any, **kwargs: Any) -> None:
    """
    Called when a worker starts. Set the redis connection name and establish a connection (so that we can monitor this process in Redis' client list)
    :param sender:
    :param instance:
    :param kwargs:
    :return:
    """
    NamedRedisConnection.set_clientname("worker-host", True)
    # open redis connection so that we see this process in the client list
    get_redis_connection().get("components:worker")
    NamedRedisConnection.set_clientname("worker", True)


class OutputHandler(Handler):
    """
    Log handler that captures all log messages in a string list
    """

    def __init__(self, level: int = NOTSET) -> None:
        Handler.__init__(self, level)
        self.buffer: list[str] = []

    def emit(self, record: LogRecord) -> None:
        self.buffer.append(self.format(record))


def set_limits() -> None:
    """
    Set resource limits on the checker process
    """
    if "SAARCTF_NO_RLIMIT" not in os.environ:
        resource.setrlimit(resource.RLIMIT_AS, (2048 * 1000000, 3072 * 1000000))  # 2GB soft / 3GB hard
    pass


@retry_on_sql_error(attempts=3)
def save_checker_result(tick: int, service_id: int, team_id: int, celery_id: str,
                        result: CheckerRunOutput, runtime: float) -> None:
    dbresult = CheckerResult(tick=tick, service_id=service_id, team_id=team_id, celery_id=celery_id)
    dbresult.time = runtime  # type: ignore[assignment]
    dbresult.status = result.status
    dbresult.message = result.message
    dbresult.output = result.output
    dbresult.data = result.data
    dbresult.finished = func.now()

    with db_session_2() as session:
        session.execute(CheckerResult.upsert(dbresult).values(dbresult.props_dict()))
        session.commit()


def run_checkerscript(self: Task, runner_spec: str, package: str, script: str, service_id: int, team_id: int, tick: int, cfg: dict | None) -> str:
    """
    Run a given checker script against a single team.
    :param self: (celery task instance)
    :param runner_spec: which runner to use
    :param package:
    :param script: Format: "<filename rel to package root>:<class name>"
    :param service_id:
    :param team_id:
    :param tick:
    :param cfg:
    :return: The (db) status of this execution
    """
    set_limits()

    # Start of debug code to test "special" cases
    if script == "crashtest":
        # "rogue" - crash in framework
        raise Exception("Invalid script!")
    if script == "sleeptest":
        # "hard sleeper" - ignore soft timeout and gets killed by hard time limit
        try:
            time.sleep(20)
        finally:
            time.sleep(20)
            return "Wakeup"
    if script == "pendingtest":
        script = "checker_runner.demo_checker:TimeoutService"
    # End of debug code

    start_time = time.time()
    output = OutputHandler()
    getLogger().addHandler(output)

    runner = CheckerRunnerFactory.build(runner_spec, service_id, package, script, cfg)
    result = runner.execute_checker(team_id, tick)
    checker_output = "\n".join(output.buffer).replace("\x00", "<0x00>")
    if not result.output:
        result.output = checker_output

    getLogger().removeHandler(output)

    # store result in database
    try:
        save_checker_result(tick, service_id, team_id, self.request.id, result, time.time() - start_time)
    except sqlalchemy.exc.InvalidRequestError as e:
        # This session is in 'prepared' state; no further SQL can be emitted within this transaction.
        if "no further SQL can be emitted" in str(e):
            set_process_needs_restart()
        else:
            raise e
    if process_needs_restart():
        print("RESTART")
        sys.exit(0)
    return result.status


def run_checkerscript_external(self: Task, runner_spec: str, package: str, script: str, service_id: int, team_id: int, tick: int,
                               cfg: dict | None) -> str:
    """
    Run a given checker script against a single team - in a seperate process, decoupled from the celery worker.
    In case the checker script crashes the process, nobody is harmed.
    :param self: (celery task instance)
    :param runner_spec: which runner to use
    :param package:
    :param script: Format: "<filename rel to package root>:<class name>"
    :param service_id:
    :param team_id:
    :param tick:
    :param cfg:
    :return: The (db) status of this execution
    """
    set_limits()

    start_time = time.time()
    runner = CheckerRunnerFactory.build(runner_spec, service_id, package, script, cfg)
    result = runner.execute_checker_subprocess(team_id, tick, self.request.timelimit[0] - 5)
    save_checker_result(tick, service_id, team_id, self.request.id, result, time.time() - start_time)

    return result.status


def preload_packages(packages: List[str] | None = None) -> bool:
    """
    Load a list of packages, so that they are present on the disk when they're required.
    :param packages:
    :return:
    """
    from checker_runner.package_loader import PackageLoader

    if packages:
        for package in packages:
            print("Preloading {} ...".format(package))
            PackageLoader.ensure_package_exists(package)
    print("Done.")
    return True


def run_command(cmd: str) -> str:
    """
    Run a command on this machine. For example: "pip install ...".
    :param cmd:
    :return: the output of this command
    """
    cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, cwd=cwd, shell=True, timeout=90)
        print(output.decode("utf-8"))
    except subprocess.CalledProcessError as e:
        print("ERROR: ", e.returncode)
        print(e.output.decode("utf-8"))
        raise
    except subprocess.TimeoutExpired as e:
        print("TIMEOUT")
        print(e.output.decode("utf-8"))
        raise
    return output.decode("utf-8")


class CeleryWorker:
    def __init__(self) -> None:
        self.app: Celery
        self.run_checkerscript: PromiseProxy
        self.run_checkerscript_external: PromiseProxy
        self.preload_packages: PromiseProxy
        self.run_command: PromiseProxy

    def init(self, threadsafe: bool = False) -> None:
        print(f"CONFIGURING CELERY: broker={config.celery_url()}, backend={config.celery_redis_url()}")
        self.app = Celery(
            "checker_runner.celery_cmd",
            broker=config.celery_url(),
            backend=config.celery_redis_url(),
            broker_connection_retry_on_startup=True,
        )
        self.app.conf.task_track_started = True
        self.app.conf.result_expires = None
        self.app.conf.worker_pool_restarts = True
        self.app.conf.task_queues = (Broadcast(name="broadcast"),)
        self.app.conf.result_backend_thread_safe = threadsafe

        # register tasks
        self.run_checkerscript = self.app.task(bind=True)(run_checkerscript)
        self.run_checkerscript_external = self.app.task(bind=True)(run_checkerscript_external)
        self.preload_packages = self.app.task(queue="broadcast", options=dict(queue="broadcast"))(preload_packages)
        self.run_command = self.app.task(queue='broadcast', options=dict(queue='broadcast'), soft_time_limit=100)(
            run_command)


celery_worker = CeleryWorker()

if __name__ == "__main__":
    load_default_config()
    NamedRedisConnection.set_clientname("worker")
    init_database()
    celery_worker.init()
    celery_worker.app.start()
