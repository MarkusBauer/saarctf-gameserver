import os
import pwd
import subprocess
from pathlib import Path

from controlserver.db_filesystem import DBFilesystem
from controlserver.models import db_session_2, Service
from gamelib import ServiceConfig
from saarctf_commons.config import config


def _getuser() -> str:
    return pwd.getpwuid(os.getuid())[0]


class ServiceRepoManager:
    def __init__(self) -> None:
        self.messages: list[str] = []
        self.dbfs = DBFilesystem()

    def _report(self, msg: str) -> None:
        print(msg)
        self.messages.append(msg)

    def _directory(self, remote_url: str) -> Path:
        if "/" in remote_url:
            remote_url = remote_url.rsplit("/", 1)[-1]
        if remote_url.endswith(".git"):
            remote_url = remote_url[:-4]
        return config.SERVICES_PATH / remote_url

    def is_owner(self) -> bool:
        return config.SERVICES_PATH.owner() == _getuser()

    def checkout_services(self) -> int:
        count = 0
        for remote_service in config.SERVICE_REMOTES:
            if self.git_checkout_service(remote_service):
                count += 1
        return count

    def git_checkout_service(self, remote_url: str) -> bool:
        dir = self._directory(remote_url)
        if dir.exists() and (dir / ".git").exists():
            return False
        self._report(f"Checking out {remote_url} ...")
        subprocess.check_call(["git", "clone", remote_url, str(dir)], cwd=dir.parent)
        self._report(f"Populated: {str(dir)}")
        return True

    def git_pull_service(self, remote_url: str) -> None:
        dir = self._directory(remote_url)
        is_unclean = subprocess.run(["git", "diff", "--quiet"], cwd=dir).returncode != 0
        if is_unclean:
            subprocess.check_call(['git', 'stash'], cwd=dir.parent)
        try:
            self._report(f"Pulling {str(dir)}")
            subprocess.check_call(["git", "pull", "--rebase"], cwd=dir)
        finally:
            if is_unclean:
                subprocess.check_call(["git", "stash", "apply"], cwd=dir.parent)
        self._report(f"Pulled {str(dir)}")

    def import_services(self) -> None:
        disk_services = self.find_services()
        with db_session_2() as session:
            by_name = {service.name: service for service in session.query(Service).all()}
            for dir, cfg in disk_services:
                if cfg.name not in by_name:
                    session.add(self._cfg_to_db(dir, cfg))
                    self._report(f'Added "{cfg.name}" to DB')
            session.commit()

    def _cfg_to_db(self, dir: Path, cfg: ServiceConfig) -> Service:
        checker_dir = str(dir / "checkers")
        package, setup_package, _ = self.upload_checker_scripts(checker_dir)
        return Service(
            name=cfg.name,
            checker_script_dir=checker_dir,
            checker_script=f"{cfg.interface_file}:{cfg.interface_class}",
            num_payloads=cfg.num_payloads,
            flag_ids=",".join(cfg.flag_ids),
            flags_per_tick=cfg.flags_per_tick,  # type: ignore
            ports=",".join(cfg.ports),
            package=package,
            setup_package=setup_package,
        )

    def _cfg_equals_db(self, dir: Path, cfg: ServiceConfig, service: Service) -> bool:
        return (
            service.name == cfg.name
            and service.checker_script_dir == str(dir / "checkers")
            and service.checker_script == f"{cfg.interface_file}:{cfg.interface_class}"
            and service.num_payloads == cfg.num_payloads
            and service.flag_ids == ",".join(cfg.flag_ids)
            and service.flags_per_tick == cfg.flags_per_tick
            and service.ports == ",".join(cfg.ports)
        )

    def _update_db_from_cfg(self, dir: Path, cfg: ServiceConfig, service: Service) -> None:
        service.name = cfg.name
        service.checker_script_dir = str(dir / "checkers")
        service.checker_script = f"{cfg.interface_file}:{cfg.interface_class}"
        service.num_payloads = cfg.num_payloads
        service.flag_ids = ",".join(cfg.flag_ids)
        service.flags_per_tick = cfg.flags_per_tick  # type: ignore
        service.ports = ",".join(cfg.ports)

    def find_services(self) -> list[tuple[Path, ServiceConfig]]:
        results = []
        for dir in sorted(config.SERVICES_PATH.iterdir()):
            if not dir.is_dir():
                continue
            try:
                cfg = ServiceConfig.from_file(dir / "checkers" / "config.toml")
                results.append((dir, cfg))
            except FileNotFoundError:
                self._report(f"Not a service (or no config): {dir}")
        return results

    def update_service(self, remote_url: str) -> None:
        dir = self._directory(remote_url)
        with db_session_2() as session:
            by_name = {service.name: service for service in session.query(Service).all()}

            if not dir.exists():
                self.git_checkout_service(remote_url)
                cfg = ServiceConfig.from_file(dir / "checkers" / "config.toml")
                session.add(self._cfg_to_db(dir, cfg))
                self._report(f'Added "{cfg.name}" to DB')

            else:
                cfg_before = ServiceConfig.from_file(dir / "checkers" / "config.toml")
                self.git_pull_service(remote_url)
                cfg = ServiceConfig.from_file(dir / "checkers" / "config.toml")
                # write to DB if service exists and wasn't altered manually
                if cfg.name in by_name and cfg_before != cfg and self._cfg_equals_db(dir, cfg_before, by_name[cfg.name]):
                    self._update_db_from_cfg(dir, cfg, by_name[cfg.name])
                    self._report(f'Updating service {by_name[cfg.name].id}: {by_name[cfg.name].name} because config changed')

            session.commit()

    def update_all_services(self) -> None:
        config.SERVICES_PATH.mkdir(parents=True, exist_ok=True)

        if not self.is_owner():
            raise PermissionError(f"You are not the owner of {config.SERVICES_PATH}. Please do not mess up permissions. "
                                  f"You are {_getuser()!r} but should be {config.SERVICES_PATH.owner()!r}.")

        for remote_service in config.SERVICE_REMOTES:
            self.update_service(remote_service)

    def upload_checker_scripts(self, checker_script_dir: str) -> tuple[str, str | None, bool]:
        # main package
        package, is_new = self.dbfs.move_folder_to_package(checker_script_dir)

        # try to upload a setup script
        base = Path(checker_script_dir).parent
        fnames = [f for f in [base / "dependencies.sh", base / "checker-requirements.txt"] if f.exists()]
        if len(fnames) > 0:
            setup_package, _ = self.dbfs.move_single_files_to_package(fnames)
        else:
            setup_package = None

        return package, setup_package, is_new
