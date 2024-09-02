import datetime


class CTFEvents:
    """
    Extend this class to listen to timing-relevant events. Timer.listener.append registers event listeners.
    """

    def onStartRound(self, roundnumber: int) -> None:
        pass

    def onEndRound(self, roundnumber: int) -> None:
        pass

    def onStartCtf(self) -> None:
        pass

    def onSuspendCtf(self) -> None:
        pass

    def onEndCtf(self) -> None:
        pass

    def onUpdateTimes(self) -> None:
        pass


class ConsoleCTFEvents(CTFEvents):
    """
    Example implementation of the CTFEvents interface
    """

    def __now(self) -> str:
        return datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S') + ' |'

    def onStartRound(self, roundnumber: int) -> None:
        print(self.__now(), 'Start of round {}'.format(roundnumber))

    def onEndRound(self, roundnumber: int) -> None:
        print(self.__now(), 'End of round {}'.format(roundnumber))

    def onStartCtf(self) -> None:
        print(self.__now(), 'CTF initially started')

    def onSuspendCtf(self) -> None:
        print(self.__now(), 'CTF suspended')

    def onEndCtf(self) -> None:
        print(self.__now(), 'CTF is over!')
