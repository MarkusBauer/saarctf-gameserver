"""
Celery configuration (message queues) and code to run the checker scripts.
"""

import os
import resource
import subprocess
import sys
import time
from logging import Handler, NOTSET, getLogger
from typing import List

import sqlalchemy
from celery import Celery
from celery.signals import celeryd_after_setup
from kombu.common import Broadcast
from sqlalchemy import func

from checker_runner.checker_execution import execute_checker, execute_checker_subprocess, process_needs_restart, set_process_needs_restart
from controlserver.models import CheckerResult, db
from saarctf_commons.config import celery_redis_url, celery_url, set_redis_clientname, get_redis_connection

# Flask needs to be imported before
set_redis_clientname('worker')
import controlserver.app

# CELERY CONFIGURATION
celeryapp = Celery('checker_runner', broker=celery_url(), backend=celery_redis_url())
celeryapp.conf.task_track_started = True
celeryapp.conf.result_expires = None
celeryapp.conf.worker_pool_restarts = True
celeryapp.conf.task_queues = (Broadcast(name='broadcast'),)


# print(type(celeryapp.broker_connection().connection))


@celeryd_after_setup.connect
def worker_init(sender, instance, **kwargs):
	"""
	Called when a worker starts. Set the redis connection name and establish a connection (so that we can monitor this process in Redis' client list)
	:param sender:
	:param instance:
	:param kwargs:
	:return:
	"""
	set_redis_clientname('worker-host', True)
	# open redis connection so that we see this process in the client list
	get_redis_connection().get('components:worker')
	set_redis_clientname('worker', True)


class OutputHandler(Handler):
	"""
	Log handler that captures all log messages in a string list
	"""

	def __init__(self, level=NOTSET):
		Handler.__init__(self, level)
		self.buffer = []

	def emit(self, record):
		self.buffer.append(self.format(record))


def set_limits():
	"""
	Set resource limits on the checker process
	"""
	resource.setrlimit(resource.RLIMIT_AS, (1500000000, 2048000000))  # 1GB soft / 2GB hard


@celeryapp.task(bind=True)
def run_checkerscript(self, package: str, script: str, service_id: int, team_id: int, round: int) -> str:
	"""
	Run a given checker script against a single team.
	:param self: (celery task instance)
	:param package:
	:param script: Format: "<filename rel to package root>:<class name>"
	:param service_id:
	:param team_id:
	:param round:
	:return: The (db) status of this execution
	"""
	set_limits()

	# Start of debug code to test "special" cases
	if script == 'crashtest':
		# "rogue" - crash in framework
		raise Exception('Invalid script!')
	if script == 'sleeptest':
		# "hard sleeper" - ignore soft timeout and gets killed by hard time limit
		try:
			time.sleep(20)
		finally:
			time.sleep(20)
			return 'Wakeup'
	if script == 'pendingtest':
		script = 'checker_runner.demo_checker:TimeoutService'
	# End of debug code

	start_time = time.time()
	result = CheckerResult(round=round, service_id=service_id, team_id=team_id, celery_id=self.request.id)
	output = OutputHandler()
	getLogger().addHandler(output)

	status, message = execute_checker(package, script, service_id, team_id, round, result)

	result.time = time.time() - start_time
	result.status = status
	result.message = message
	result.output = '\n'.join(output.buffer).replace('\x00', '<0x00>')
	result.finished = func.now()
	getLogger().removeHandler(output)

	# store result in database
	try:
		db.session.execute(CheckerResult.upsert(result).values(result.props_dict()))
		db.session.commit()
	except sqlalchemy.exc.InvalidRequestError as e:
		# This session is in 'prepared' state; no further SQL can be emitted within this transaction.
		if 'no further SQL can be emitted' in str(e):
			set_process_needs_restart()
		else:
			raise e
	if process_needs_restart():
		print('RESTART')
		sys.exit(0)
	return result.status


@celeryapp.task(bind=True)
def run_checkerscript_external(self, package: str, script: str, service_id: int, team_id: int, round: int) -> str:
	"""
	Run a given checker script against a single team - in a seperate process, decoupled from the celery worker.
	In case the checker script crashes the process, nobody is harmed.
	:param self: (celery task instance)
	:param package:
	:param script: Format: "<filename rel to package root>:<class name>"
	:param service_id:
	:param team_id:
	:param round:
	:return: The (db) status of this execution
	"""
	set_limits()

	start_time = time.time()
	result = CheckerResult(round=round, service_id=service_id, team_id=team_id, celery_id=self.request.id)

	status, message, output = execute_checker_subprocess(package, script, service_id, team_id, round, self.request.timelimit[0] - 5)

	result.time = time.time() - start_time
	result.status = status
	result.message = message
	result.output = output.replace('\x00', '<0x00>')
	result.finished = func.now()

	# store result in database
	db.session.execute(CheckerResult.upsert(result).values(result.props_dict()))
	db.session.commit()
	return result.status


@celeryapp.task(queue="broadcast", options=dict(queue="broadcast"))
def preload_packages(packages: List[str] = list()):
	"""
	Load a list of packages, so that they are present on the disk when they're required.
	:param packages:
	:return:
	"""
	from checker_runner.package_loader import PackageLoader
	for package in packages:
		print('Preloading {} ...'.format(package))
		PackageLoader.ensure_package_exists(package)
	print('Done.')
	return True


@celeryapp.task(queue='broadcast', options=dict(queue='broadcast'), soft_time_limit=100)
def run_command(cmd: str) -> str:
	"""
	Run a command on this machine. For example: "pip install ...".
	:param cmd:
	:return: the output of this command
	"""
	cwd = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	try:
		output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, cwd=cwd, shell=True, timeout=90)
		print(output.decode('utf-8'))
	except subprocess.CalledProcessError as e:
		print('ERROR: ', e.returncode)
		print(e.output.decode('utf-8'))
		raise
	except subprocess.TimeoutExpired as e:
		print('TIMEOUT')
		print(e.output.decode('utf-8'))
		raise
	return output.decode('utf-8')


if __name__ == '__main__':
	celeryapp.start()
