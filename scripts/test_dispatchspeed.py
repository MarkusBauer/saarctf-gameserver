from checker_runner.runner import *
from saarctf_commons.debug_sql_timing import timing, print_query_stats


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
