import random
import requests
from gamelib import gamelib


class HTTPService(gamelib.ServiceInterface):

	name = 'HTTPService'
	URL = 'http://localhost/demoservice.php'

	def check_integrity(self, team, round):
		try:
			response = requests.get(self.URL)
		except requests.exceptions.ConnectionError:
			raise gamelib.OfflineException('localhost is offline')
		if response.status_code != 200:
			raise gamelib.MumbleException(str(response.status_code))
		return True

	def store_flags(self, team, round):
		try:
			response = requests.post(self.URL, data={
				'team_id': team.id,
				'service_id': self.id,
				'round': round,
				'flag': '\n'.join((self.get_flag(team, round, i) for i in range(3)))
			})
			if response.status_code != 200:
				raise gamelib.MumbleException(str(response.status_code))
			return 3
		except requests.exceptions.ConnectionError:
			raise gamelib.OfflineException('localhost is offline')

	def retrieve_flags(self, team, round):
		try:
			response = requests.get(self.URL, params={
				'team_id': team.id,
				'service_id': self.id,
				'round': round
			})
			if response.status_code != 200:
				raise gamelib.MumbleException(str(response.status_code))
			flags = self.search_flags(response.text)
			if len(flags) < 3:
				raise gamelib.FlagMissingException('Not all flags found')

			payloads = set()
			for flag in flags:
				teamid, serviceid, round, payload = self.check_flag(flag, team.id, round)
				if not teamid:
					raise gamelib.FlagMissingException('Invalid flag retrieved')
				payloads.add(payload)
			if len(payloads) < 3:
				raise gamelib.FlagMissingException('Flag repeated')
			return 3
		except requests.exceptions.ConnectionError:
			raise gamelib.OfflineException('localhost is offline')


class UnreliableHTTPService(HTTPService):
	def check_integrity(self, team, round):
		if team.id != 71 and random.randint(0, 100) < 7:
			raise gamelib.MumbleException('Random said so')


class RandomCrashHTTPService(HTTPService):
	def store_flags(self, team, round):
		if team.id != 71 and random.randint(0, 100) < 5:
			raise gamelib.OfflineException('Random offline')
		return HTTPService.store_flags(self, team, round)

	def retrieve_flags(self, team, round):
		if team.id != 71 and random.randint(0, 100) < 10:
			raise gamelib.FlagMissingException('Flag missing')
		return HTTPService.retrieve_flags(self, team, round)
