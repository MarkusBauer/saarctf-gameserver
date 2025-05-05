from typing import Any

from checker_runner.checker_execution import CheckerRunner
from controlserver.utils.import_factory import ImportFactory


class CheckerRunnerFactory(ImportFactory[CheckerRunner]):
    base_class = CheckerRunner

    @classmethod
    def build(cls, runner: str, service_id: int, package: str, script: str, cfg: dict | None, **kwargs: Any) -> CheckerRunner:
        return cls.get_class(runner or 'saarctf:SaarctfServiceRunner')(service_id, package, script, cfg, **kwargs)
