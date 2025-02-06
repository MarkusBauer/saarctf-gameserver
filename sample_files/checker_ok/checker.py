from gamelib import gamelib
from . import test


class SampleService(gamelib.ServiceInterface):
    def check_integrity(self, team, tick):
        if not test.VERSION == 2:
            raise Exception(test.VERSION)

    def store_flags(self, team, tick):
        pass

    def retrieve_flags(self, team, tick):
        pass
