import random

import requests
import psycopg2
from gamelib import ServiceInterface, MumbleException, OfflineException, FlagMissingException
from saarctf_commons.config import config


class DBService(ServiceInterface):
    def check_integrity(self, team, tick):
        try:
            response = requests.get('http://localhost')
        except requests.exceptions.ConnectionError:
            raise OfflineException('localhost is offline')
        if response.status_code != 200:
            raise MumbleException(str(response.status_code))

    def store_flags(self, team, tick):
        conn = psycopg2.connect(config.postgres_psycopg2())
        cursor = conn.cursor()
        cursor.execute('''
		CREATE TABLE IF NOT EXISTS test_service_storage (
			team_id INTEGER NOT NULL,
			service_id INTEGER NOT NULL,
			tick INTEGER NOT NULL,
			flag TEXT NOT NULL
		);
		''')
        conn.commit()

        cursor.execute(
            "INSERT INTO test_service_storage (team_id, service_id, tick, flag) "
            "VALUES (%s, %s, %s, %s), (%s, %s, %s, %s), (%s, %s, %s, %s)", (
                team.id, self.id, tick, self.get_flag(team, tick, 0),
                team.id, self.id, tick, self.get_flag(team, tick, 1),
                team.id, self.id, tick, self.get_flag(team, tick, 2)
            )
        )
        conn.commit()
        cursor.close()
        conn.close()

    def retrieve_flags(self, team, tick):
        conn = psycopg2.connect(config.postgres_psycopg2())
        cursor = conn.cursor()
        cursor.execute(
            "SELECT flag FROM test_service_storage WHERE team_id = %s AND service_id = %s AND tick = %s",
            (team.id, self.id, tick)
        )
        rows = cursor.fetchmany(3)
        print(rows)
        if len(rows) < 3:
            raise FlagMissingException('Not all flags found')

        payloads = set()
        for flag, in rows:
            teamid, serviceid, expires, payload = self.check_flag(flag)
            if teamid != team.id or payload > 2:
                raise MumbleException('Strange parameters')
            payloads.add(payload)
        if len(payloads) < 3:
            raise FlagMissingException('Flag repeated')

        cursor.close()
        conn.close()


class UnreliableDBService(DBService):
    def check_integrity(self, team, tick):
        if team.id != 71 and random.randint(0, 100) < 7:
            raise MumbleException('Random said so')


class RandomCrashDBService(DBService):
    def store_flags(self, team, tick):
        if team.id != 71 and random.randint(0, 100) < 5:
            raise OfflineException('Random offline')
        return DBService.store_flags(self, team, tick)

    def retrieve_flags(self, team, tick):
        if team.id != 71 and random.randint(0, 100) < 10:
            raise FlagMissingException('Flag missing')
        return DBService.retrieve_flags(self, team, tick)
