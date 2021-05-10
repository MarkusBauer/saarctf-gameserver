import importlib
import os
import subprocess
import sys
import traceback
from typing import Tuple, Optional
from celery.exceptions import SoftTimeLimitExceeded
import requests

# Set environment for pwntools
os.environ['TERM'] = 'xterm'
os.environ['PWNLIB_NOTERM'] = '1'
# Set environment (path) for gamelib (in single-process mode)
if __name__ == '__main__':
	sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gamelib import gamelib, gamelogger
from saarctf_commons.config import team_id_to_vulnbox_ip, set_redis_clientname

SEPARATOR = "\n\n" + '-' * 72

_process_needs_restart = False


def process_needs_restart() -> bool:
	global _process_needs_restart
	return _process_needs_restart


def set_process_needs_restart():
	global _process_needs_restart
	_process_needs_restart = True


def execute_checker(package: str, script: str, service_id: int, team_id: int, round: int, result=None) -> Tuple[str, Optional[str]]:
	"""
	Run a given checker script against a single team.
	:param self: (celery task instance)
	:param package:
	:param script: Format: "<filename rel to package root>:<class name>"
	:param service_id:
	:param team_id:
	:param round:
	:param result: (optional) CheckerResult object that might receive partial success information
	:return: (db-status, message) The (db) status of this execution, and an error message (if applicable)
	"""
	import pwnlib

	team = gamelib.Team(team_id, '#' + str(team_id), team_id_to_vulnbox_ip(team_id))
	try:
		# Load service interface
		fname, clsname = script.split(':')
		if package:
			from checker_runner.package_loader import PackageLoader
			module = PackageLoader.load_module_from_package(package, fname)
		else:
			module = importlib.import_module(fname)
		cls = getattr(module, clsname)

		# Check the service
		gamelogger.GameLogger.reset()
		checker: gamelib.ServiceInterface = cls(service_id)
		checker.initialize_team(team)
		try:
			gamelogger.GameLogger.log('----- check_integrity -----')
			checker.check_integrity(team, round)
			if result: result.integrity = True
			gamelogger.GameLogger.log(f'----- store_flags({round}) -----')
			checker.store_flags(team, round)
			if result: result.stored = True
			if round > 1:
				gamelogger.GameLogger.log(f'----- retrieve_flags({round - 1}) -----')
				checker.retrieve_flags(team, round - 1)
				if result: result.retrieved = True
			elif round == -1:
				# Test run - retrieve the flag we just have set
				gamelogger.GameLogger.log(f'----- retrieve_flags({round}) -----')
				checker.retrieve_flags(team, round)
				if result: result.retrieved = True
		finally:
			try:
				checker.finalize_team(team)
			except:
				traceback.print_exc()

		return 'SUCCESS', None

	except gamelib.FlagMissingException as e:
		traceback.print_exc()
		return 'FLAGMISSING', e.message
	except gamelib.MumbleException as e:
		traceback.print_exc()
		return 'MUMBLE', e.message
	except AssertionError as e:
		traceback.print_exc()
		if len(e.args) == 1 and type(e.args[0]) == str:
			return 'MUMBLE', e.args[0]
		return 'MUMBLE', repr(e.args)
	except requests.ConnectionError as e:
		traceback.print_exc()
		return 'OFFLINE', 'Connection timeout'
	except pwnlib.exception.PwnlibException as e:
		if 'Could not connect to' in e.args[0]:
			return 'OFFLINE', str(e.args[0])
		return 'CRASHED', None
	except gamelib.OfflineException as e:
		traceback.print_exc()
		return 'OFFLINE', e.message
	except SoftTimeLimitExceeded:
		traceback.print_exc()
		return 'TIMEOUT', 'Timeout, service too slow'
	except OSError as e:
		traceback.print_exc()
		if 'No route to host' in str(e):
			return 'OFFLINE', 'no route to host'
		return 'CRASHED', None
	except MemoryError:
		set_process_needs_restart()
		traceback.print_exc()
		return 'CRASHED', None
	except:
		traceback.print_exc()
		return 'CRASHED', None


def execute_checker_subprocess(package: str, script: str, service_id: int, team_id: int, round: int, timeout: int) -> Tuple[str, Optional[str], str]:
	"""
	Run a given checker script against a single team - in a discrete subprocess.
	:param self: (celery task instance)
	:param package:
	:param script: Format: "<filename rel to package root>:<class name>"
	:param service_id:
	:param team_id:
	:param round:
	:param timeout: Process timeout in seconds
	:return: (db-status, message, output) The (db) status of this execution, an error message (if applicable), and the console output
	"""
	try:
		cmd = [sys.executable, os.path.abspath(__file__), package or '', script, str(service_id), str(team_id), str(round)]
		output: str = subprocess.check_output(
			cmd, stderr=subprocess.STDOUT, timeout=timeout, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
		).decode('utf-8')
		p = output.rindex(SEPARATOR)
		status, message = output[p + len(SEPARATOR) + 1:].split('|', 1)
		return status, (message.strip() or None), output
	except subprocess.TimeoutExpired as e:
		return 'TIMEOUT', 'Timeout, service too slow', e.output.decode('utf-8')
	except subprocess.CalledProcessError as e:
		return 'CRASHED', None, e.output.decode('utf-8')
	except subprocess.SubprocessError as e:
		return 'CRASHED', None, str(e)


if __name__ == '__main__':
	print('(subprocess invoked)')
	# execute checker script
	if len(sys.argv) <= 5:
		raise Exception('Not enough arguments!')
	set_redis_clientname('worker-process')
	status, message = execute_checker(sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]))
	print(SEPARATOR)
	print(status + '|' + (message or ''))
	sys.exit(0)
