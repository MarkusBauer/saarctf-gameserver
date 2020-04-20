import os
import saarctf_commons.config

saarctf_commons.config.set_redis_clientname('script-' + os.path.basename(__file__))

from checker_runner.runner import *
from controlserver.app import *
from sample_files.debug_sql_timing import timing, print_query_stats


def main():
	from controlserver.dispatcher import Dispatcher
	dispatcher = Dispatcher()

	for rn in range(505, 507):
		timing()
		dispatcher.dispatch_checker_scripts(rn)
		timing('dispatch')

		time.sleep(2)

		timing()
		# print(dispatcher.get_round_taskgroup(rn).get())
		dispatcher.collect_checker_results(rn)
		timing('collect')

	print_query_stats()


if __name__ == '__main__':
	main()
