from gamelib import gamelib
from . import test


class SampleService(gamelib.ServiceInterface):
	def check_integrity(self, team, tick):
		if not test.VERSION == 1:
			raise Exception(test.VERSION)
		return True

	def store_flags(self, team, tick):
		# self.do_blocking_io()
		return 1

	def retrieve_flags(self, team, tick):
		# return 1
		raise gamelib.FlagMissingException("FLAG{} not found")

	def do_blocking_io(self):
		print('Block...')
		import socket
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.connect(('127.0.0.1', 12345))
		print(sock.recv(1024))
