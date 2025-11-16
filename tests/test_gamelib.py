import unittest
from typing import Any

from gamelib import gamelib, usernames, Team, ServiceConfig
from tests.utils.base_cases import TestCase


class DummyService(gamelib.ServiceInterface):
    def __init__(self) -> None:
        super().__init__(ServiceConfig(
            service_id=1,
            name='dummy',
            flag_ids=['hex8', 'alphanum5', 'username', 'email', 'pattern:${username}/abc/${alphanum12}'],
            interface_class='',
            interface_file=''
        ))

    def check_integrity(self, team: Team, tick: int) -> None:
        raise NotImplementedError

    def store_flags(self, team: Team, tick: int) -> Any:
        raise NotImplementedError

    def retrieve_flags(self, team: Team, tick: int) -> Any:
        raise NotImplementedError


TEST_TEAMS = [
    gamelib.Team(1, 'Test1', '1.2.3.4'),
    gamelib.Team(2, 'Test2', '1.2.3.8'),
    gamelib.Team(1337, 'Test1337', '127.13.37.1'),
]


class GamelibTestCase(TestCase):
    def test_flag_generator(self) -> None:
        service = DummyService()
        seen_flags: set[str] = set()
        for team in TEST_TEAMS:
            for tick in (1, 2, 0, -1, 1338):
                for payload in (0, 1, 1339):
                    flag: str = service.get_flag(team, tick, payload)
                    self.assertNotIn(flag, seen_flags, f'Flag {flag} duplicated!')
                    seen_flags.add(flag)
                    self.assertTrue(gamelib.get_flag_regex().fullmatch(flag), f'Flag {flag} did not match regex {gamelib.get_flag_regex()}')
                    # parse flag
                    a, b, c, d = service.check_flag(flag)
                    self.assertEqual(a, team.id)
                    self.assertEqual(b, service.id)
                    self.assertEqual(c & 0xffff, tick & 0xffff)  # type: ignore
                    self.assertEqual(d, payload)
                    # check if flag is deterministic
                    for _ in range(3):
                        flag2 = service.get_flag(team, tick, payload)
                        self.assertEqual(flag, flag2)

    def test_flag_ids(self) -> None:
        service = DummyService()
        flag_ids: list[list[str]] = [[], []]
        for i in range(2):
            seen_flag_ids: set[str] = set()
            for team in TEST_TEAMS:
                for round in (1, 2, 0, -1, 1338):
                    for index in range(len(service.config.flag_ids)):
                        flag_id = service.get_flag_id(team, round, index)
                        self.assertNotIn(flag_id, seen_flag_ids, f'Flag ID {flag_id} repeated')
                        seen_flag_ids.add(flag_id)
                        flag_ids[i].append(flag_id)
                        for _ in range(3):
                            flag_id_2 = service.get_flag_id(team, round, index)
                            self.assertEqual(flag_id, flag_id_2, f'Flag ID not deterministic: {flag_id} != {flag_id_2}')
        self.assertListEqual(flag_ids[0], flag_ids[1], 'Multiple runs give different flag ids')


if __name__ == '__main__':
    unittest.main()
