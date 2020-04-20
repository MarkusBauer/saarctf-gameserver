import random

import requests
import psycopg2
from gamelib import gamelib
from saarctf_commons.config import postgres_psycopg2


class DBService(gamelib.ServiceInterface):
	def check_integrity(self, team, round):
		try:
			response = requests.get('http://localhost')
		except requests.exceptions.ConnectionError:
			raise gamelib.OfflineException('localhost is offline')
		if response.status_code != 200:
			raise gamelib.MumbleException(str(response.status_code))
		return True

	def store_flags(self, team, round):
		conn = psycopg2.connect(postgres_psycopg2())
		cursor = conn.cursor()
		cursor.execute(
			"INSERT INTO test_service_storage (team_id, round, flag) VALUES (%s, %s, %s), (%s, %s, %s), (%s, %s, %s)", (
				team.id, round, self.get_flag(team, round, 0),
				team.id, round, self.get_flag(team, round, 1),
				team.id, round, self.get_flag(team, round, 2)
			)
		)
		conn.commit()
		cursor.close()
		conn.close()
		return 3

	def retrieve_flags(self, team, round):
		conn = psycopg2.connect(postgres_psycopg2())
		cursor = conn.cursor()
		cursor.execute(
			"SELECT flag FROM test_service_storage WHERE team_id = %s AND round = %s",
			(team.id, round)
		)
		rows = cursor.fetchmany(3)
		print(rows)
		if len(rows) < 3:
			raise gamelib.FlagMissingException('Not all flags found')

		payloads = set()
		for flag, in rows:
			teamid, serviceid, expires, payload = self.check_flag(flag)
			if teamid != team.id or payload > 2:
				raise gamelib.MumbleException('Strange parameters')
			payloads.add(payload)
		if len(payloads) < 3:
			raise gamelib.FlagMissingException('Flag repeated')

		cursor.close()
		conn.close()
		return 1


class UnreliableDBService(DBService):
	def check_integrity(self, team, round):
		if team.id != 71 and random.randint(0, 100) < 7:
			raise gamelib.MumbleException('Random said so')


class RandomCrashDBService(DBService):
	def store_flags(self, team, round):
		if team.id != 71 and random.randint(0, 100) < 5:
			raise gamelib.OfflineException('Random offline')
		return DBService.store_flags(self, team, round)

	def retrieve_flags(self, team, round):
		if team.id != 71 and random.randint(0, 100) < 10:
			raise gamelib.FlagMissingException('Flag missing')
		return DBService.retrieve_flags(self, team, round)
