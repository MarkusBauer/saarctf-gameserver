from gamelib import gamelib
from . import test

class SampleService(gamelib.ServiceInterface):
	def check_integrity(self, team, round):
		if not test.VERSION == 2:
			raise Exception(test.VERSION)
		return True

	def store_flags(self, team, round):
		return 1

	def retrieve_flags(self, team, round):
		return 1
