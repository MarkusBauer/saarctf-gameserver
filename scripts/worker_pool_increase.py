import sys
import os
import time
from typing import Iterable, Dict

import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.redis import NamedRedisConnection
from saarctf_commons.config import config, load_default_config

"""
ARGUMENTS: number_of_new_workers (optional, default=1)
"""


class FlowerInterface:
    def __init__(self) -> None:
        self.session: requests.Session = requests.Session()

    def get_worker_pool_size(self) -> dict[str, int]:
        workers = self.session.get(config.FLOWER_INTERNAL_URL + 'api/workers', params={'refresh': '1'}).json()
        return {name: len(worker['stats']['pool']['processes']) for name, worker in workers.items() if 'stats' in worker}

    def get_worker_pool_size_for_queue(self, queue: str) -> int:
        c = 0
        workers = self.session.get(config.FLOWER_INTERNAL_URL + 'api/workers', params={'refresh': '1'}).json()
        for name, worker in workers.items():
            if 'stats' in worker and 'active_queues' in worker and any(q['name'] == queue for q in worker['active_queues']):
                c += len(worker['stats']['pool']['processes'])
        return c

    def get_worker_online(self) -> dict[str, bool]:
        workers = self.session.get(config.FLOWER_INTERNAL_URL + 'dashboard?json=1').json()
        return {item['hostname']: item['status'] for item in workers['data']}

    def grow_workers(self, workers: Iterable[str], n: int) -> None:
        for worker_name in workers:
            self.grow_worker(worker_name, n)

    def grow_worker(self, worker_name: str, n: int) -> str:
        response = self.session.post(
            config.FLOWER_INTERNAL_URL + 'api/worker/pool/grow/' + worker_name,
            data={'workername': worker_name, 'n': n})
        if response.status_code == 200:
            return response.json()['message']
        else:
            print('[ERR]', response.status_code, response.text)
            return str(response.status_code) + ': ' + response.text


def print_workers(workers: Dict[str, int], online: Dict[str, bool] | None = None) -> None:
    print('{} workers:'.format(len(workers)))
    for name, poolsize in workers.items():
        if online and not online[name]:
            print('  {:3d} processes  :  {}  (offline)'.format(poolsize, name))
        else:
            print('  {:3d} processes  :  {}'.format(poolsize, name))
    print('----------------')
    print('= {:3d} processes'.format(sum(workers.values())))  # type: ignore


def main() -> None:
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
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))
    main()
