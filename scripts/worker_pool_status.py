import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.config import load_default_config, config
from saarctf_commons.redis import NamedRedisConnection
from scripts.worker_pool_increase import FlowerInterface, print_workers


def main() -> None:
    flower = FlowerInterface()
    workers = flower.get_worker_pool_size()
    online = flower.get_worker_online()
    print_workers(workers, online)


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname('script-' + os.path.basename(__file__))
    main()
