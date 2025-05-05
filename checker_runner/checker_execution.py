from abc import abstractmethod, ABC
from dataclasses import dataclass, field

_process_needs_restart = False


def process_needs_restart() -> bool:
    global _process_needs_restart
    return _process_needs_restart


def set_process_needs_restart() -> None:
    global _process_needs_restart
    _process_needs_restart = True


@dataclass
class CheckerRunOutput:
    status: str  # "SUCCESS" etc
    output: str | None = None
    message: str | None = None
    data: dict = field(default_factory=dict)  # additional, runner-specific data


class CheckerRunner(ABC):
    def __init__(self, service_id: int, package: str, script: str, cfg: dict | None) -> None:
        """
        :param service_id:
        :param package:
        :param script: Format: "<filename rel to package root>:<class name>"
        :param cfg: config from database
        """
        self.service_id = service_id
        self.package = package
        self.script = script
        self.cfg = cfg or {}

    @abstractmethod
    def execute_checker(self, team_id: int, tick: int) -> CheckerRunOutput:
        raise NotImplementedError

    def execute_checker_subprocess(self, team_id: int, tick: int, timeout: int) \
        -> CheckerRunOutput:
        raise NotImplementedError
