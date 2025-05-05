from abc import ABC
from collections import defaultdict

from controlserver.models import CheckerResult, TeamPointsLite, Service
from controlserver.scoring.algorithms.algorithm import StolenFlag, FlagPointAlgorithm, ScoreTickAlgorithm, ScoreTickAlgorithmBase, ServicePayloadPair, \
    TeamServicePair, TickTeamPair
from controlserver.scoring.algorithms.saarctf import SlaSaarCtfDefault, DefensiveSaarCtfDefault
from saarctf_commons.config import ScoringConfig


class FlagPointsFixedWeightDefault(ScoreTickAlgorithm, FlagPointAlgorithm, ABC):
    """
    Formulas:
    OFF = 1 + sqrt(1 / num_submitters_this_tick) + sqrt(1 / victim_rank)
    Difference: consider number of attacking teams in the tick that flag was submitted. Not: number of submitters per flag.
    That means that attack points will never decrease.
    """

    def __init__(self, config: ScoringConfig, team_ids: list[int], services: list[Service]) -> None:
        super().__init__(config, team_ids, services)
        self._attacking_teams_count: dict[ServicePayloadPair, int] = {}

    def calculate_scoring_for_tick(self, tick: int, checker_results: dict[TeamServicePair, CheckerResult],
                                   last_tick_points: dict[TeamServicePair, TeamPointsLite],
                                   team_rank_in_tick: dict[TickTeamPair, int],
                                   flags: list[StolenFlag]) -> dict[TeamServicePair, TeamPointsLite]:
        self._attacking_teams_count = self._compute_attacking_teams_count(flags)
        return super().calculate_scoring_for_tick(tick, checker_results, last_tick_points, team_rank_in_tick, flags)  # type:ignore[safe-super]

    def _compute_attacking_teams_count(self, flags: list[StolenFlag]) -> dict[ServicePayloadPair, int]:
        result: dict[ServicePayloadPair, set[int]] = defaultdict(set)
        for flag in flags:
            result[(flag.flag.service_id, flag.flag.payload)].add(flag.flag.submitted_by)
        return {k: len(v) for k, v in result.items()}

    def off_points(self, flag: StolenFlag, victim_rank: int) -> float:
        return 1.0 + \
            (1.0 / self._attacking_teams_count[(flag.flag.service_id, flag.flag.payload)]) ** 0.5 + \
            (1.0 / victim_rank) ** 0.5

    def off_points_previous(self, flag: StolenFlag, victim_rank: int) -> float | None:
        return None


class PlaygroundScoreAlgorithm(FlagPointsFixedWeightDefault, DefensiveSaarCtfDefault, SlaSaarCtfDefault, ScoreTickAlgorithmBase):
    pass


class HappyHourFlagPoints(FlagPointsFixedWeightDefault, ABC):
    def factor(self, tick: int) -> float:
        return 2.0 if tick >= self.config.data.get('happy_hour_tick', 0xffffff) else 1.0

    def off_points(self, flag: StolenFlag, victim_rank: int) -> float:
        return super().off_points(flag, victim_rank) * self.factor(flag.flag.tick_issued)

    def off_points_previous(self, flag: StolenFlag, victim_rank: int) -> float | None:
        p = super().off_points_previous(flag, victim_rank)
        return p * self.factor(flag.flag.tick_issued) if p is not None else None
