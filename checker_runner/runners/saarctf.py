import importlib
import os
import subprocess
import sys
import traceback
from typing import Type, ClassVar

from celery.exceptions import SoftTimeLimitExceeded

from checker_runner.checker_execution import CheckerRunner, CheckerRunOutput, set_process_needs_restart
from controlserver.models import db_session_2, Service
from gamelib.exceptions import handle_checker_exceptions
from saarctf_commons.db_utils import retry_on_sql_error
from saarctf_commons.redis import NamedRedisConnection

# Set environment for pwntools
os.environ["TERM"] = "xterm"
os.environ["PWNLIB_NOTERM"] = "1"
# Set environment (path) for gamelib (in single-process mode)
if __name__ == "__main__":
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gamelib import gamelib, gamelogger, ServiceConfig
from saarctf_commons.config import config

SEPARATOR = "\n\n" + "-" * 72


class SaarctfServiceRunner(CheckerRunner):
    _service_config_cache: ClassVar[dict[str, ServiceConfig]] = {}

    @retry_on_sql_error(attempts=2)
    def get_service_config(self, service_id: int) -> ServiceConfig:
        if self.package in self._service_config_cache:
            cfg = self._service_config_cache[self.package]
        else:
            with db_session_2() as session:
                service: Service | None = session.get(Service, service_id)
                if service is None:
                    raise Exception(f"Service {service_id} not found in DB")
                fn, cl = service.checker_script.split(':', 1) if service.checker_script else ('', '')
                cfg = ServiceConfig(
                    name=service.name,
                    service_id=service.id,
                    flag_ids=service.flag_ids.split(",") if service.flag_ids else [],
                    interface_file=fn,
                    interface_class=cl,
                )
            self._service_config_cache[self.package] = cfg
        cfg.service_id = service_id
        return cfg

    def get_checker_class(self) -> Type[gamelib.ServiceInterface]:
        # Load service interface
        fname, clsname = self.script.split(":")
        if self.package:
            from checker_runner.package_loader import PackageLoader

            module = PackageLoader.load_module_from_package(self.package, fname)
        else:
            module = importlib.import_module(fname)
        return getattr(module, clsname)

    def _execute_checker_unchecked(self, service_id: int, team_id: int, tick: int) -> CheckerRunOutput:
        """
        Run a given checker script against a single team.
        :param service_id:
        :param team_id:
        :param tick:
        :return: (db-status, message) The (db) status of this execution, and an error message (if applicable)
        """
        team = gamelib.Team(team_id, '#' + str(team_id), config.NETWORK.team_id_to_vulnbox_ip(team_id))
        service_config = self.get_service_config(service_id)
        gamelogger.GameLogger.reset()
        checker: gamelib.ServiceInterface = self.get_checker_class()(service_config)
        checker.initialize_team(team)
        try:
            gamelogger.GameLogger.log("----- check_integrity -----")
            checker.check_integrity(team, tick)
            gamelogger.GameLogger.log(f"----- store_flags({tick}) -----")
            checker.store_flags(team, tick)
            if tick > 1:
                gamelogger.GameLogger.log(f"----- retrieve_flags({tick - 1}) -----")
                checker.retrieve_flags(team, tick - 1)
            elif tick <= -1:
                # Test run - retrieve the flag we just have set
                gamelogger.GameLogger.log(f"----- retrieve_flags({tick}) -----")
                checker.retrieve_flags(team, tick)
        finally:
            try:
                checker.finalize_team(team)
            except:
                traceback.print_exc()

        return CheckerRunOutput("SUCCESS")

    def execute_checker(self, team_id: int, tick: int) -> CheckerRunOutput:
        try:
            result = handle_checker_exceptions(lambda: self._execute_checker_unchecked(self.service_id, team_id, tick))
            if isinstance(result, tuple):
                return CheckerRunOutput(result[0], message=result[1])
            return result
        # handle only celery-specific exceptions, and crashes
        except SoftTimeLimitExceeded:
            traceback.print_exc()
            return CheckerRunOutput("TIMEOUT", message="Timeout, service too slow")
        except MemoryError:
            set_process_needs_restart()
            traceback.print_exc()
            return CheckerRunOutput("CRASHED")
        except:
            traceback.print_exc()
            return CheckerRunOutput("CRASHED")

    def execute_checker_subprocess(self, team_id: int, tick: int, timeout: int) \
        -> CheckerRunOutput:
        """
        Run a given checker script against a single team - in a discrete subprocess.
        :param self: (celery task instance)
        :param package:
        :param script: Format: "<filename rel to package root>:<class name>"
        :param team_id:
        :param tick:
        :param timeout: Process timeout in seconds
        :return: (db-status, message, output) The (db) status of this execution, an error message (if applicable), and the console output
        """
        try:
            cmd = [sys.executable, os.path.abspath(__file__),
                   self.package or '', self.script, str(self.service_id), str(team_id), str(tick)]
            output: str = subprocess.check_output(
                cmd, stderr=subprocess.STDOUT, timeout=timeout,
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ).decode('utf-8')
            p = output.rindex(SEPARATOR)
            status, message = output[p + len(SEPARATOR) + 1:].split('|', 1)
            return CheckerRunOutput(status, message=(message.strip() or None), output=output)
        except subprocess.TimeoutExpired as e:
            return CheckerRunOutput('TIMEOUT', message='Timeout, service too slow', output=e.output.decode('utf-8'))
        except subprocess.CalledProcessError as e:
            return CheckerRunOutput("CRASHED", output=e.output.decode("utf-8"))
        except subprocess.SubprocessError as e:
            return CheckerRunOutput("CRASHED", output=str(e))


if __name__ == "__main__":
    print("(subprocess invoked)")
    # execute checker script
    if len(sys.argv) <= 5:
        raise Exception("Not enough arguments!")
    NamedRedisConnection.set_clientname("worker-process")

    service_id = int(sys.argv[3])
    run = SaarctfServiceRunner(service_id, sys.argv[1], sys.argv[2], None)  # TODO None
    result = run.execute_checker(int(sys.argv[4]), int(sys.argv[5]))
    print(SEPARATOR)
    print(result.status + "|" + (result.message or ""))
    sys.exit(0)
