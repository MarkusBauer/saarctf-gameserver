from collections import defaultdict

from sqlalchemy import event
from sqlalchemy.engine import Engine
import time
import logging

logging.basicConfig()
logger = logging.getLogger("sqltime")
logger.setLevel(logging.DEBUG)


def timing(name=''):
	t = time.time()
	if not hasattr(timing, 't'):
		timing.t = t
	else:
		print('{:7.1f} ms  (+ {:6.1f} ms)  {}'.format((t - timing.t) * 1000, (t - timing.last_t) * 1000, name))
	timing.last_t = t


query_counter = defaultdict(lambda: 0)
query_total_time = defaultdict(lambda: 0.0)

debug_print = False


def enable_debug():
	global debug_print
	debug_print = True


def print_query_stats():
	print('count      total   query')
	for query, count in query_counter.items():
		total = query_total_time[query]
		print('{:5}  {:8.2f}ms  {}'.format(count, total*1000, query))


@event.listens_for(Engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
	statement = statement.replace('\n', ' ')[:165]
	context._query_start_time = time.time()
	if debug_print:
		logger.debug("Start Query: %s" % statement)


@event.listens_for(Engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
	total = time.time() - context._query_start_time
	statement = statement.replace('\n', ' ')[:165]
	query_counter[statement] += 1
	query_total_time[statement] += total
	if debug_print:
		logger.debug("Total Time: %.02fms" % (total * 1000))


def reset_timing():
	query_counter.clear()
	query_total_time.clear()
	if hasattr(timing, 't'):
		delattr(timing, 't')
