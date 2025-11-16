from sqlalchemy import inspect
from sqlalchemy.orm import Session

from controlserver.models import TeamRanking, Team, Service, TeamPointsLite
from controlserver.scoring.algorithms.algorithm import TeamServicePair
from controlserver.scoring.scoring import ScoringCalculation
from saarctf_commons.config import ScoringConfig


class FilteredScoringCalculation(ScoringCalculation):
    """
    A ScoringCalculation that acts like some teams don't exist.
    That means: compute the full results (with all teams) under the hood, but return TeamRanking without some.
    """

    def __init__(self, config: ScoringConfig, *, exclude_team_ids: set[int] | None = None, subtract_nop_points: bool = False) -> None:
        super().__init__(config)
        self.exclude_team_ids = exclude_team_ids or set()
        self.subtract_nop_points = subtract_nop_points

    def get_considered_teams(self, session: Session) -> list[Team]:
        teams = super().get_considered_teams(session)
        return [t for t in teams if t.id not in self.exclude_team_ids]

    def get_results_for_tick_lite(self, session: Session, tick: int, teams: list[int] | None = None, services: list[Service] | None = None) \
        -> dict[TeamServicePair, TeamPointsLite]:
        points = super().get_results_for_tick_lite(session, tick, teams, services)
        points = {(team_id, service_id): v for (team_id, service_id), v in points.items() if team_id not in self.exclude_team_ids}
        return points

    def get_ranking_for_tick(self, session: Session, tick: int) -> list[TeamRanking]:
        rankings = super().get_ranking_for_tick(session, tick)
        rankings.sort(key=lambda r: r.rank)

        # option: offset every point (sum) by the nop team's points (so that anyone worse than the NOP team will get 0 points)
        point_offset = 0
        if self.subtract_nop_points:
            for r in rankings:
                if r.team_id == self.config.nop_team_id:
                    point_offset = r.points
                    break

        filtered_rankings = []
        removed = 0
        for ranking in rankings:
            if ranking.team_id in self.exclude_team_ids:
                removed += 1
            else:
                ranking.team  # preload that field - performance is not too important in the filtered case
                state = inspect(ranking)
                if state.pending or state.persistent:
                    session.expunge(ranking)
                ranking.rank -= removed
                ranking.points = max(0, ranking.points - point_offset)
                filtered_rankings.append(ranking)
        return filtered_rankings
