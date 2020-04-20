import os
import subprocess
import sys
from typing import List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.EXTERNAL_TIMER = True

from controlserver.models import Service
from controlserver.db_filesystem import DBFilesystem

"""
Run the setup scripts from all services
ARGUMENTS: none
"""


def run_service_setup_scripts(filters: List[str]):
	# noinspection PyUnresolvedReferences
	import controlserver.app
	if filters:
		services = Service.query.filter(Service.name.in_(filters)).filter(Service.setup_package != None).all()
	else:
		services = Service.query.filter(Service.setup_package != None).all()
	errors = 0
	dbfs = DBFilesystem()
	for service in services:
		print(f'[{service.name}] Extracting script from package {service.setup_package} ...')
		path = f'/tmp/setup_packages/{service.setup_package}'
		dbfs.load_package_to_folder(service.setup_package, path, '/tmp/setup_packages/lfs')
		script = f'{path}/dependencies.sh'
		if not os.path.exists(script):
			print(f'[{service.name}] Script not found: "{script}"!')
			errors += 1
		else:
			print(f'[{service.name}] Running script "{script}" ...')
			os.system(f'chmod +x "{script}"')
			result = subprocess.run([script])
			if result.returncode != 0:
				errors += 1
				print(f'[{service.name}] Script failed with code {result.returncode}.')
			else:
				print(f'[{service.name}] Script succeeded.')
	return errors


if __name__ == '__main__':
	config.set_redis_clientname('script-' + os.path.basename(__file__))
	errors = run_service_setup_scripts(sys.argv[1:])
	if errors > 0:
		print(f'[ERROR] {errors} errors reported.')
		sys.exit(1)
