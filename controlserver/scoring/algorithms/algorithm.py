from abc import ABC, abstractmethod
from dataclasses import dataclass
from math import sqrt
from typing import Collection, Any, TypeAlias

from controlserver.logger import log
from controlserver.models import CheckerResult, Service, TeamPointsLite, SubmittedFlag, LogMessage
from saarctf_commons.config import ScoringConfig


TeamServicePair: TypeAlias = tuple[int, int]
TickTeamPair: TypeAlias = tuple[int, int]
ServiceTickPair: TypeAlias = tuple[int, int]
ServicePayloadPair: TypeAlias = tuple[int, int]


class FlagSet:
    def __init__(self) -> None:
        self._set: set[tuple[int, int, int, int]] = set()  # service, team, tick_issued, payload

    def is_new(self, flag: SubmittedFlag) -> bool:
        """
        Return True if this flag was not seen by this set before.
        Submitter is ignored, thus similar to "flag string".
        """
        key = (flag.service_id, flag.team_id, flag.tick_issued, flag.payload)
        if key in self._set:
            return False
        self._set.add(key)
        return True


@dataclass(frozen=True)
class StolenFlag:
    flag: SubmittedFlag
    num_previous_submissions: int
    num_submissions: int
    previous_submitter_ids: Collection[int]


class FlagPointAlgorithm(ABC):
    """
    NOT including: configured OFF/DEF factors
    NOT including: service_flags_per_tick
    """
    @abstractmethod
    def off_points(self, flag: StolenFlag, victim_rank: int) -> float:
        """Total value of this flag"""
        raise NotImplementedError()

    @abstractmethod
    def off_points_previous(self, flag: StolenFlag, victim_rank: int) -> float | None:
        """
        How much this flag was worth in past ticks (or None if past results shouldn't be corrected)
        """
        raise NotImplementedError()


class DefensiveAlgorithm(ABC):
    @abstractmethod
    def def_points(self, flag: StolenFlag, num_active_teams: int, victim_sla_when_issued: float) -> float:
        """Lost points caused by this flag (all steals in all ticks so far)"""
        raise NotImplementedError()

    @abstractmethod
    def def_points_previous(self, flag: StolenFlag, num_active_teams: int, victim_sla_when_issued: float) -> float:
        """Already lost points before this flag was stolen again"""
        raise NotImplementedError()


class SlaAlgorithm(ABC):
    """
    NOT including: configured SLA factor.
    """
    @abstractmethod
    def sla_points(self, tick: int, checker_result: CheckerResult) -> float:
        """SLA points for a checker result."""
        raise NotImplementedError()


class ScoreTickAlgorithm(ABC):
    """
    Scoring algorithm interface, which also implements most of the boilerplate to get/set results.
    """
    def __init__(self, config: ScoringConfig, team_ids: list[int], services: list[Service]) -> None:
        self.config = config
        self.team_ids = team_ids
        self.services = services
        self.services_by_id = {service.id: service for service in services}
        self.sla_delta_for: dict[ServiceTickPair, dict[int, float]] = {}  # set by code outside of this module

    @abstractmethod
    def calculate_scoring_for_tick(self, tick: int,
                                   checker_results: dict[TeamServicePair, CheckerResult],
                                   last_tick_points: dict[TeamServicePair, TeamPointsLite],
                                   team_rank_in_tick: dict[TickTeamPair, int],  # (tick,teamid) => rank
                                   flags: list[StolenFlag],
                                   ) -> dict[TeamServicePair, TeamPointsLite]:
        raise NotImplementedError()


class ScoreTickAlgorithmBase(ScoreTickAlgorithm, FlagPointAlgorithm, DefensiveAlgorithm, SlaAlgorithm, ABC):
    active_status: set[str] = {'SUCCESS', 'FLAGMISSING', 'RECOVERING'}

    def _new_results_for_tick(self, tick: int) -> dict[TeamServicePair, TeamPointsLite]:
        """
        Return a dict with new / empty results, ready to be filled (and submitted using #save_teampoints)
        :param tick:
        :return:
        """
        result: dict[TeamServicePair, TeamPointsLite] = {}
        for team_id in self.team_ids:
            for service in self.services:
                if (team_id, service.id) not in result:
                    result[(team_id, service.id)] = TeamPointsLite(team_id=team_id, service_id=service.id, tick=tick)
        return result

    def calculate_scoring_for_tick(self, tick: int,
                                   checker_results: dict[TeamServicePair, CheckerResult],
                                   last_tick_points: dict[TeamServicePair, TeamPointsLite],
                                   team_rank_in_tick: dict[TickTeamPair, int],
                                   flags: list[StolenFlag],
                                   ) -> dict[TeamServicePair, TeamPointsLite]:
        """
        Calculate the results for one tick
        """

        # 1. Spaces for results
        for service in self.services:
            self.sla_delta_for[(service.id, tick)] = {}
        new_tick_points: dict[TeamServicePair, TeamPointsLite] = self._new_results_for_tick(tick)
        # from here on, new_tick_points contains the points ONLY from this tick, until the last step

        # 2. Calculate SLA and number of active teams
        num_active_teams = self._calculate_sla(tick, new_tick_points, checker_results)

        # 3 Distribute points for all flags submitted this tick
        stolen_flags = FlagSet()
        for flag in flags:
            try:
                service = self.services_by_id[flag.flag.service_id]
                service_flags_per_tick: float = service.flags_per_tick  # type: ignore
                # Victim's rank when the flag was created (end of the tick before)
                victim_rank = team_rank_in_tick.get((flag.flag.tick_issued - 1, flag.flag.team_id),
                                                    len(self.team_ids))

                self._flag_stolen_attacker(new_tick_points, flag, service_flags_per_tick, victim_rank)
                if stolen_flags.is_new(flag.flag):
                    # Deduce victim points - that happens only once for each stolen flag
                    self._flag_stolen_victim(new_tick_points, flag, service_flags_per_tick, num_active_teams)
                    # Offensive points of previous attackers need to be reduced - also only once for each flag
                    self._flag_stolen_previous_attackers(new_tick_points, flag, service_flags_per_tick, victim_rank)
            except KeyError:
                print(f'Flag submitted for invalid team/service: '
                      f'flag #{flag.flag.id} ({flag.flag.team_id}, {flag.flag.service_id})')
                log('scoring', 'Flag submitted for invalid team/service',
                    f'flag #{flag.flag.id} ({flag.flag.team_id}, {flag.flag.service_id})',
                    level=LogMessage.WARNING)

        # 4. Add the points from previous tick
        for (team_id, service_id), teampoints in new_tick_points.items():
            lr = last_tick_points[(team_id, service_id)]
            teampoints.off_points += lr.off_points
            teampoints.def_points += lr.def_points
            teampoints.sla_points = lr.sla_points + teampoints.sla_delta
            teampoints.flag_captured_count += lr.flag_captured_count
            teampoints.flag_stolen_count += lr.flag_stolen_count

        return new_tick_points

    def _flag_stolen_attacker(self, new_tick_points: dict[TeamServicePair, TeamPointsLite], flag: StolenFlag,
                              service_flags_per_tick: float, victim_rank: int) -> None:
        """Give each attacker points"""
        attacker = new_tick_points[(flag.flag.submitted_by, flag.flag.service_id)]
        attacker.flag_captured_count += 1
        attacker.off_points += self.off_points(flag, victim_rank) / service_flags_per_tick * self.config.off_factor

    def _flag_stolen_victim(self, new_tick_points: dict[TeamServicePair, TeamPointsLite], flag: StolenFlag,
                            service_flags_per_tick: float, num_active_teams: int) -> None:
        """Deduce defensive points"""
        # Victim's SLA points when the flag was stored (0 if the flag couldn't be stored)
        victim = new_tick_points[(flag.flag.team_id, flag.flag.service_id)]
        victim_sla_when_issued = self.sla_delta_for \
            .get((flag.flag.service_id, flag.flag.tick_issued), {}) \
            .get(flag.flag.team_id, 0)
        prev_damage = self.def_points_previous(flag, num_active_teams, victim_sla_when_issued)
        new_damage = self.def_points(flag, num_active_teams, victim_sla_when_issued)
        victim.def_points -= ((new_damage - prev_damage) / service_flags_per_tick) * self.config.def_factor
        if flag.num_previous_submissions == 0:
            # if flag is not known to be stolen
            victim.flag_stolen_count += 1

    def _flag_stolen_previous_attackers(self, new_tick_points: dict[TeamServicePair, TeamPointsLite], flag: StolenFlag,
                                        service_flags_per_tick: float, victim_rank: int) -> None:
        """
        A flag's value decreases if more teams steal it.
        In this case we also have to decrease their value for submitters from previous ticks.
        """
        if flag.num_previous_submissions > 0:
            assert len(flag.previous_submitter_ids) == flag.num_previous_submissions
            previous_flagpoints = self.off_points_previous(flag, victim_rank)
            if previous_flagpoints is not None:
                new_flagpoints = self.off_points(flag, victim_rank)
                for ps in flag.previous_submitter_ids:
                    new_tick_points[(ps, flag.flag.service_id)].off_points += \
                        (new_flagpoints - previous_flagpoints) / service_flags_per_tick * self.config.off_factor

    def _calculate_sla(self, tick: int, new_tick_points: dict[TeamServicePair, TeamPointsLite],
                       checker_results: dict[TeamServicePair, CheckerResult]) -> int:
        active_team_ids = set()
        for (team_id, service_id), teampoints in new_tick_points.items():
            checker_result = checker_results[(team_id, service_id)]
            sla_points = self.sla_points(tick, checker_result)
            teampoints.sla_delta = sla_points * self.config.sla_factor  # 0/1 * factor
            if sla_points > 0 or checker_result.status in self.active_status:
                active_team_ids.add(team_id)
        num_active_teams = max(1, len(active_team_ids))
        for (team_id, service_id), teampoints in new_tick_points.items():
            # SLA = (0/1) * sqrt(active_teams)
            teampoints.sla_delta *= sqrt(num_active_teams)
            self.sla_delta_for[service_id, tick][team_id] = teampoints.sla_delta
        return num_active_teams
