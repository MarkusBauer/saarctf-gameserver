import datetime


class CTFEvents:
	"""
	Extend this class to listen to timing-relevant events. Timer.listener.append registers event listeners.
	"""

	def onStartRound(self, roundnumber: int):
		pass

	def onEndRound(self, roundnumber: int):
		pass

	def onStartCtf(self):
		pass

	def onSuspendCtf(self):
		pass

	def onEndCtf(self):
		pass

	def onUpdateTimes(self):
		pass


class ConsoleCTFEvents(CTFEvents):
	"""
	Example implementation of the CTFEvents interface
	"""

	def __now(self) -> str:
		return datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S') + ' |'

	def onStartRound(self, roundnumber: int):
		print(self.__now(), 'Start of round {}'.format(roundnumber))

	def onEndRound(self, roundnumber: int):
		print(self.__now(), 'End of round {}'.format(roundnumber))

	def onStartCtf(self):
		print(self.__now(), 'CTF initially started')

	def onSuspendCtf(self):
		print(self.__now(), 'CTF suspended')

	def onEndCtf(self):
		print(self.__now(), 'CTF is over!')
