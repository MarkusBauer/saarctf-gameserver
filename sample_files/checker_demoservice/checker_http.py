import random
import requests
from gamelib import ServiceInterface, Team, OfflineException, MumbleException, FlagMissingException


class HTTPService(ServiceInterface):

	# name = 'HTTPService'
	URL = 'http://localhost/demoservice.php'

	def check_integrity(self, team: Team, tick: int) -> None:
		try:
			response = requests.get(self.URL)
		except requests.exceptions.ConnectionError:
			raise OfflineException('localhost is offline')
		if response.status_code != 200:
			raise MumbleException(str(response.status_code))

	def store_flags(self, team: Team, tick: int) -> None:
		try:
			response = requests.post(self.URL, data={
				'team_id': team.id,
				'service_id': self.id,
				'tick': tick,
				'flag': '\n'.join((self.get_flag(team, tick, i) for i in range(3)))
			})
			if response.status_code != 200:
				raise MumbleException(str(response.status_code))
			return 3
		except requests.exceptions.ConnectionError:
			raise OfflineException('localhost is offline')

	def retrieve_flags(self, team: Team, tick: int) -> None:
		try:
			response = requests.get(self.URL, params={
				'team_id': team.id,
				'service_id': self.id,
				'tick': tick
			})
			if response.status_code != 200:
				raise MumbleException(str(response.status_code))
			flags = self.search_flags(response.text)
			if len(flags) < 3:
				raise FlagMissingException('Not all flags found')

			payloads = set()
			for flag in flags:
				teamid, serviceid, tick, payload = self.check_flag(flag, team.id, tick)
				if not teamid:
					raise FlagMissingException('Invalid flag retrieved')
				payloads.add(payload)
			if len(payloads) < 3:
				raise FlagMissingException('Flag repeated')
			return 3
		except requests.exceptions.ConnectionError:
			raise OfflineException('localhost is offline')


class UnreliableHTTPService(HTTPService):
	def check_integrity(self, team: Team, tick: int) -> None:
		if team.id != 71 and random.randint(0, 100) < 7:
			raise MumbleException('Random said so')


class RandomCrashHTTPService(HTTPService):
	def store_flags(self, team: Team, tick: int) -> None:
		if team.id != 71 and random.randint(0, 100) < 5:
			raise OfflineException('Random offline')
		return HTTPService.store_flags(self, team, tick)

	def retrieve_flags(self, team: Team, tick: int) -> None:
		if team.id != 71 and random.randint(0, 100) < 10:
			raise FlagMissingException('Flag missing')
		return HTTPService.retrieve_flags(self, team, tick)
