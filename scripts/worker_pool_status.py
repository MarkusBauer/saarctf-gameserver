import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.worker_pool_increase import FlowerInterface, print_workers


def main():
	flower = FlowerInterface()
	workers = flower.get_worker_pool_size()
	online = flower.get_worker_online()
	print_workers(workers, online)


if __name__ == '__main__':
	main()
