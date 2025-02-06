import os
import subprocess
import sys
from pathlib import Path
from typing import List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.redis import NamedRedisConnection
from saarctf_commons.config import config, load_default_config
from controlserver.models import Service, init_database
from controlserver.db_filesystem import DBFilesystem

"""
Run the setup scripts from all services
ARGUMENTS: none
"""


def run_service_setup_scripts(filters: List[str]) -> int:
    init_database()
    if filters:
        services = Service.query.filter(Service.name.in_(filters)).filter(Service.setup_package != None).all()
    else:
        services = Service.query.filter(Service.setup_package != None).all()
    errors = 0
    dbfs = DBFilesystem()
    for service in services:
        setup_package: str = service.setup_package  # type: ignore
        print(f'[{service.name}] Extracting script from package {setup_package} ...')
        path = Path('/tmp/setup_packages') / setup_package  # type: ignore[operator]
        dbfs.load_package_to_folder(setup_package, path, Path('/tmp/setup_packages/lfs'))

        dependencies_script = path / 'dependencies.sh'
        if not dependencies_script.exists():
            print(f'[{service.name}] Script not found: "{dependencies_script}"!')
            errors += 1
        else:
            print(f'[{service.name}] Running script "{dependencies_script}" ...')
            subprocess.check_call(['chmod', '+x', str(dependencies_script)])
            result = subprocess.run([str(dependencies_script)])
            if result.returncode != 0:
                errors += 1
                print(f'[{service.name}] Script failed with code {result.returncode}.')
            else:
                print(f'[{service.name}] Script succeeded.')

        requirements_file = path / 'checker-requirements.txt'
        if not requirements_file.exists():
            print(f'[{service.name}] Requirements file not found: "{requirements_file}"!')
            errors += 1
        else:
            print(f'[{service.name}] Installing from "{requirements_file}" ...')
            result = subprocess.run(['pip', 'install', '-r', str(requirements_file)])
            if result.returncode != 0:
                errors += 1
                print(f'[{service.name}] Pip failed with code {result.returncode}.')
            else:
                print(f'[{service.name}] Pip succeeded.')

    return errors


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))
    errors = run_service_setup_scripts(sys.argv[1:])
    if errors > 0:
        print(f'[ERROR] {errors} errors reported.')
        sys.exit(1)
