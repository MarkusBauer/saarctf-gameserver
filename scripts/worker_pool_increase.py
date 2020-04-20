import sys
import os
import time
from typing import Iterable, Dict

import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.config import FLOWER_INTERNAL_URL

"""
ARGUMENTS: number_of_new_workers (optional, default=1)
"""


class FlowerInterface:
	def __init__(self):
		self.session: requests.Session = requests.Session()

	def get_worker_pool_size(self):
		workers = self.session.get(FLOWER_INTERNAL_URL + 'api/workers', params={'refresh': '1'}).json()
		return {name: len(worker['stats']['pool']['processes']) for name, worker in workers.items() if 'stats' in worker}

	def get_worker_online(self):
		workers = self.session.get(FLOWER_INTERNAL_URL + 'dashboard?json=1').json()
		return {item['hostname']: item['status'] for item in workers['data']}

	def grow_workers(self, workers: Iterable[str], n: int):
		for worker_name in workers:
			self.grow_worker(worker_name, n)

	def grow_worker(self, worker_name: str, n: int):
		response = self.session.post(
			FLOWER_INTERNAL_URL + 'api/worker/pool/grow/' + worker_name,
			data={'workername': worker_name, 'n': n})
		if response.status_code == 200:
			return response.json()['message']
		else:
			print('[ERR]', response.status_code, response.text)
			return str(response.status_code) + ': ' + response.text


def print_workers(workers: Dict[str, int], online: Dict[str, bool]=None):
	print('{} workers:'.format(len(workers)))
	for name, poolsize in workers.items():
		if online and not online[name]:
			print('  {:3d} processes  :  {}  (offline)'.format(poolsize, name))
		else:
			print('  {:3d} processes  :  {}'.format(poolsize, name))
	print('----------------')
	print('= {:3d} processes'.format(sum(workers.values())))  # type: ignore


def main():
	count: int = int(sys.argv[1]) if len(sys.argv) > 1 else 1
	flower = FlowerInterface()
	workers = flower.get_worker_pool_size()
	print_workers(workers, flower.get_worker_online())

	print('\nGrowing by {} processes each...'.format(count))
	flower.grow_workers(workers.keys(), count)
	print('Done, waiting for processes to start...\n')

	time.sleep(12)

	workers = flower.get_worker_pool_size()
	print_workers(workers, flower.get_worker_online())


if __name__ == '__main__':
	main()
