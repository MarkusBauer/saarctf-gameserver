import datetime
from typing_extensions import override


class CTFEvents:
    """
    Extend this class to listen to timing-relevant events. Timer.listener.append registers event listeners.
    """

    def on_start_tick(self, tick: int, ts: datetime.datetime) -> None:
        pass

    def on_end_tick(self, tick: int, ts: datetime.datetime) -> None:
        pass

    def on_start_ctf(self) -> None:
        pass

    def on_suspend_ctf(self) -> None:
        pass

    def on_end_ctf(self) -> None:
        pass

    def on_update_times(self) -> None:
        pass


class ConsoleCTFEvents(CTFEvents):
    """
    Example implementation of the CTFEvents interface
    """

    def __now(self, ts: datetime.datetime) -> str:
        return ts.astimezone().strftime('%d.%m.%Y %H:%M:%S') + ' |'

    @override
    def on_start_tick(self, tick: int, ts: datetime.datetime) -> None:
        print(self.__now(ts), 'Start of tick {}'.format(tick))

    @override
    def on_end_tick(self, tick: int, ts: datetime.datetime) -> None:
        print(self.__now(ts), 'End of tick {}'.format(tick))

    @override
    def on_start_ctf(self) -> None:
        print(self.__now(datetime.datetime.now()), 'CTF initially started')

    @override
    def on_suspend_ctf(self) -> None:
        print(self.__now(datetime.datetime.now()), 'CTF suspended')

    @override
    def on_end_ctf(self) -> None:
        print(self.__now(datetime.datetime.now()), 'CTF is over!')
