import os
import random
import socket
import sys
import time

import gamelib.gamelib


class WorkingService(gamelib.gamelib.ServiceInterface):
	def check_integrity(self, team, tick):
		return True

	def store_flags(self, team, tick):
		print('stderr-Test', file=sys.stderr)
		return 1

	def retrieve_flags(self, team, tick):
		print('Test')
		os.system('echo stdout-Test-2')
		os.system('echo stderr-Test-2 1>&2')
		return 1


class FlagNotFoundService(gamelib.gamelib.ServiceInterface):
	def check_integrity(self, team, tick):
		return True

	def store_flags(self, team, tick):
		raise gamelib.FlagMissingException('Flag from tick {} not found!'.format(tick))

	def retrieve_flags(self, team, tick):
		print('Test')
		return 1


class OfflineService(gamelib.gamelib.ServiceInterface):
	def check_integrity(self, team, tick):
		raise gamelib.OfflineException('IOError')

	def store_flags(self, team, tick):
		raise gamelib.OfflineException('IOError')

	def retrieve_flags(self, team, tick):
		raise gamelib.OfflineException('IOError')


class TimeoutService(gamelib.gamelib.ServiceInterface):
	def check_integrity(self, team, tick):
		return True

	def store_flags(self, team, tick):
		time.sleep(20)
		print('stderr-Test', file=sys.stderr)
		return 1

	def retrieve_flags(self, team, tick):
		print('Test')
		return 1


class BlockingService(gamelib.gamelib.ServiceInterface):
	def check_integrity(self, team, tick):
		return True

	def store_flags(self, team, tick):
		try:
			import pysigset
			mask = pysigset.SIGSET()
			pysigset.sigfillset(mask)
			pysigset.sigprocmask(pysigset.SIG_SETMASK, mask, 0)
		except ImportError:
			pass
		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		sock.bind(('localhost', 50000 + random.randint(0, 14000)))
		while True:
			try:
				sock.recvfrom(4096)
			except:
				pass
		return 1

	def retrieve_flags(self, team, tick):
		return 1


class CrashingService(gamelib.gamelib.ServiceInterface):
	def check_integrity(self, team, tick):
		return True

	def store_flags(self, team, tick):
		raise Exception('Unhandled fun')

	def retrieve_flags(self, team, tick):
		print('Test')
		return 1


class TempService(gamelib.gamelib.ServiceInterface):
	def check_integrity(self, team, tick):
		print('PID', os.getpid())
		import requests
		response = requests.get('http://192.168.178.94:12345/')
		return response.status_code < 300

	def store_flags(self, team, tick):
		return 1

	def retrieve_flags(self, team, tick):
		return 1


class SegfaultService(gamelib.gamelib.ServiceInterface):
	def check_integrity(self, team, tick):
		import signal
		os.kill(os.getpid(), signal.SIGSEGV)

	def store_flags(self, team, tick):
		return 1

	def retrieve_flags(self, team, tick):
		return 1


class OOMService(gamelib.gamelib.ServiceInterface):
	def check_integrity(self, team, tick):
		data = list(range(1024*1024))
		data2 = data * 1024
		return sum(data2) == 12345

	def store_flags(self, team, tick):
		return 1

	def retrieve_flags(self, team, tick):
		return 1


class BinaryService(gamelib.gamelib.ServiceInterface):
	def check_integrity(self, team, tick):
		print('Hello World!')
		print(' >>> \x00 <<<')
		return True

	def store_flags(self, team, tick):
		for i in range(256):
			print(i, '=', chr(i))
		return 1

	def retrieve_flags(self, team, tick):
		return 1
