import os
import random
import socket
import sys
import time

import gamelib.gamelib


class WorkingService(gamelib.gamelib.ServiceInterface):
    def check_integrity(self, team: gamelib.Team, tick: int) -> None:
        pass

    def store_flags(self, team: gamelib.Team, tick: int) -> None:
        print("stderr-Test", file=sys.stderr)
        pass

    def retrieve_flags(self, team: gamelib.Team, tick: int) -> None:
        print("Test")
        os.system("echo stdout-Test-2")
        os.system("echo stderr-Test-2 1>&2")


class FlagNotFoundService(gamelib.gamelib.ServiceInterface):
    def check_integrity(self, team: gamelib.Team, tick: int) -> None:
        pass

    def store_flags(self, team: gamelib.Team, tick: int) -> None:
        raise gamelib.FlagMissingException("Flag from tick {} not found!".format(tick))

    def retrieve_flags(self, team: gamelib.Team, tick: int) -> None:
        print("Test")
        pass


class OfflineService(gamelib.gamelib.ServiceInterface):
    def check_integrity(self, team: gamelib.Team, tick: int) -> None:
        raise gamelib.OfflineException("IOError")

    def store_flags(self, team: gamelib.Team, tick: int) -> None:
        raise gamelib.OfflineException("IOError")

    def retrieve_flags(self, team: gamelib.Team, tick: int) -> None:
        raise gamelib.OfflineException("IOError")


class TimeoutService(gamelib.gamelib.ServiceInterface):
    def check_integrity(self, team: gamelib.Team, tick: int) -> None:
        pass

    def store_flags(self, team: gamelib.Team, tick: int) -> None:
        time.sleep(20)
        print("stderr-Test", file=sys.stderr)
        pass

    def retrieve_flags(self, team: gamelib.Team, tick: int) -> None:
        print("Test")
        pass


class BlockingService(gamelib.gamelib.ServiceInterface):
    def check_integrity(self, team: gamelib.Team, tick: int) -> None:
        pass

    def store_flags(self, team: gamelib.Team, tick: int) -> None:
        try:
            import pysigset

            mask = pysigset.SIGSET()
            pysigset.sigfillset(mask)
            pysigset.sigprocmask(pysigset.SIG_SETMASK, mask, 0)
        except ImportError:
            pass
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("localhost", 50000 + random.randint(0, 14000)))
        while True:
            try:
                sock.recvfrom(4096)
            except:
                pass

    def retrieve_flags(self, team: gamelib.Team, tick: int) -> None:
        pass


class CrashingService(gamelib.gamelib.ServiceInterface):
    def check_integrity(self, team: gamelib.Team, tick: int) -> None:
        pass

    def store_flags(self, team: gamelib.Team, tick: int) -> None:
        raise Exception("Unhandled fun")

    def retrieve_flags(self, team: gamelib.Team, tick: int) -> None:
        print("Test")
        pass


class TempService(gamelib.gamelib.ServiceInterface):
    def check_integrity(self, team: gamelib.Team, tick: int) -> None:
        print("PID", os.getpid())
        import requests

        response = requests.get("http://192.168.178.94:12345/")
        assert response.status_code < 300

    def store_flags(self, team: gamelib.Team, tick: int) -> None:
        pass

    def retrieve_flags(self, team: gamelib.Team, tick: int) -> None:
        pass


class SegfaultService(gamelib.gamelib.ServiceInterface):
    def check_integrity(self, team: gamelib.Team, tick: int) -> None:
        import signal

        os.kill(os.getpid(), signal.SIGSEGV)

    def store_flags(self, team: gamelib.Team, tick: int) -> None:
        pass

    def retrieve_flags(self, team: gamelib.Team, tick: int) -> None:
        pass


class OOMService(gamelib.gamelib.ServiceInterface):
    def check_integrity(self, team: gamelib.Team, tick: int) -> None:
        data = list(range(1024 * 1024))
        data2 = data * 1024
        assert sum(data2) == 12345

    def store_flags(self, team: gamelib.Team, tick: int) -> None:
        pass

    def retrieve_flags(self, team: gamelib.Team, tick: int) -> None:
        pass


class BinaryService(gamelib.gamelib.ServiceInterface):
    def check_integrity(self, team: gamelib.Team, tick: int) -> None:
        print("Hello World!")
        print(" >>> \x00 <<<")

    def store_flags(self, team: gamelib.Team, tick: int) -> None:
        for i in range(256):
            print(i, "=", chr(i))
        pass

    def retrieve_flags(self, team: gamelib.Team, tick: int) -> None:
        pass


class FlagIDService(gamelib.gamelib.ServiceInterface):
    def check_integrity(self, team: gamelib.Team, tick: int) -> None:
        pass

    def store_flags(self, team: gamelib.Team, tick: int) -> None:
        self.set_flag_id(team, tick, 0, f"flagid-{team.ip}-{tick}")

    def retrieve_flags(self, team: gamelib.Team, tick: int) -> None:
        self.get_flag_id(team, tick, 0)
