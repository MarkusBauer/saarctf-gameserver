"""
Events like "Start CTF", "New tick", ....
Everything is based on CTFEvents interface (in timer.py). Events are emitted by the Timer.
"""

import threading
import time
from abc import ABC, abstractmethod
from datetime import datetime

from typing_extensions import override

from controlserver.dispatcher import DispatcherFactory
from controlserver.logger import log, log_result_of_execution
from controlserver.models import LogMessage, db_session_2, Tick
from controlserver.scoring.scoreboard import Scoreboard, default_scoreboards
from controlserver.scoring.scoring import ScoringCalculation
from controlserver.events import CTFEvents
from controlserver.vpncontrol import VPNControl, VpnStatus
from saarctf_commons.config import config
from saarctf_commons.db_utils import retry_on_sql_error


class LogCTFEvents(CTFEvents):
    """
    Create log entries for the events
    """

    @override
    def on_start_tick(self, tick: int, ts: datetime) -> None:
        log("timer", "New tick: {}".format(tick), level=LogMessage.IMPORTANT)

    @override
    def on_start_ctf(self) -> None:
        log("timer", "CTF starts", level=LogMessage.IMPORTANT)

    @override
    def on_suspend_ctf(self) -> None:
        log("timer", "CTF suspended", level=LogMessage.IMPORTANT)

    @override
    def on_end_ctf(self) -> None:
        log("timer", "CTF stopped", level=LogMessage.IMPORTANT)

    @override
    def on_open_vulnbox_access(self) -> None:
        log("timer", "Vulnbox access opened", level=LogMessage.IMPORTANT)


class GenericDeferredCTFEvents(CTFEvents, ABC):
    @override
    def on_start_tick(self, tick: int, ts: datetime) -> None:
        thread = threading.Thread(
            name="starttick",
            target=self._on_start_tick_deferred,
            args=(tick, ts),
            daemon=False,
        )
        thread.start()

    @override
    def on_end_tick(self, tick: int, ts: datetime) -> None:
        thread = threading.Thread(
            name="endtick",
            target=self._on_end_tick_deferred,
            args=(tick, ts),
            daemon=False,
        )
        thread.start()

    @abstractmethod
    def _on_start_tick_deferred(self, tick: int, ts: datetime) -> None:
        raise NotImplementedError()

    @abstractmethod
    def _on_end_tick_deferred(self, tick: int, ts: datetime) -> None:
        raise NotImplementedError()


class DeferredCTFEvents(GenericDeferredCTFEvents):
    """
    Dispatcher, Scoring, Scoreboard - process them in seperate threads at tick start / end.
    """

    def __init__(self) -> None:
        self.dispatcher = DispatcherFactory.build(config.RUNNER.dispatcher)
        self.scoring = ScoringCalculation(config.SCORING)
        self.scoreboards: list[Scoreboard] = default_scoreboards(self.scoring, publish=True)

    @override
    def _on_start_tick_deferred(self, tick: int, ts: datetime) -> None:
        log_result_of_execution(
            "dispatcher",
            self.dispatcher.dispatch_checker_scripts,
            args=(tick,),
            success="Checker scripts dispatched, took {:.3f} sec",
            error="Couldn't start checker scripts: {} {}",
        )
        if tick == 1:
            for i, scoreboard in enumerate(self.scoreboards, start=1):
                log_result_of_execution(
                    "scoring",
                    scoreboard.create_scoreboard,
                    args=(tick - 1, True, True),
                    success=f"Scoreboard {i} generated, took {{:.1f}} sec",
                    error=f"Scoreboard {i} failed: {{}} {{}}",
                )

    @override
    def _on_end_tick_deferred(self, tick: int, ts: datetime) -> None:
        time.sleep(1)
        log_result_of_execution(
            "dispatcher",
            self.dispatcher.revoke_checker_scripts,
            args=(tick,),
            error="Couldn't revoke checker scripts: {} {}",
            reraise=False,
        )
        log_result_of_execution(
            "dispatcher",
            self.dispatcher.collect_checker_results,
            args=(tick,),
            success="Collected checker script results, took {:.3f} sec",
            error="Couldn't collect checker script results: {} {}",
        )
        log_result_of_execution(
            "scoring",
            self.scoring.scoring_and_ranking,
            args=(tick,),
            success="Ranking calculated, took {:.3f} sec",
            error="Ranking calculation failed: {} {}",
        )
        for i, scoreboard in enumerate(self.scoreboards, start=1):
            log_result_of_execution(
                "scoring",
                scoreboard.create_scoreboard,
                args=(tick, True, True),
                success=f"Scoreboard {i} generated, took {{:.1f}} sec",
                error=f"Scoreboard {i} failed: {{}} {{}}",
            )
            if tick > 0 and not scoreboard.exists(tick - 1, True):
                log_result_of_execution(
                    "scoring",
                    scoreboard.create_scoreboard,
                    args=(tick - 1, True, False),
                    success=f"Scoreboard {i} generated, took {{:.1f}} sec",
                    error=f"Scoreboard {i} failed: {{}} {{}}",
                )

    @override
    def on_start_ctf(self) -> None:
        for i, scoreboard in enumerate(self.scoreboards, start=1):
            log_result_of_execution(
                "scoring",
                scoreboard.update_tick_info,
                args=(),
                error=f"Couldn't create initial scoreboard {i}: {{}} {{}}",
            )

    @override
    def on_update_times(self) -> None:
        for i, scoreboard in enumerate(self.scoreboards, start=1):
            log_result_of_execution(
                "scoring",
                scoreboard.update_tick_info,
                args=(),
                error="Cloudn't create updated scoreboard: {} {}",
            )


class VPNCTFEvents(CTFEvents):
    def __init__(self) -> None:
        self.vpn = VPNControl()

    @override
    def on_start_tick(self, tick: int, ts: datetime) -> None:
        self.vpn.unban_for_tick(tick)

    @override
    def on_start_ctf(self) -> None:
        self.vpn.set_state(VpnStatus.ON)

    @override
    def on_end_ctf(self) -> None:
        if self.vpn.get_state() == VpnStatus.ON:
            self.vpn.set_state(VpnStatus.TEAMS_ONLY)

    @override
    def on_open_vulnbox_access(self) -> None:
        if self.vpn.get_state() != VpnStatus.ON:
            self.vpn.set_state(VpnStatus.TEAMS_ONLY)


class DatabaseTickRecording(GenericDeferredCTFEvents):
    @override
    @retry_on_sql_error(attempts=2)
    def _on_start_tick_deferred(self, tick: int, ts: datetime) -> None:
        with db_session_2() as session:
            Tick.set_start(session, tick, ts)
            session.commit()

    @override
    @retry_on_sql_error(attempts=2)
    def _on_end_tick_deferred(self, tick: int, ts: datetime) -> None:
        with db_session_2() as session:
            Tick.set_end(session, tick, ts)
            session.commit()
