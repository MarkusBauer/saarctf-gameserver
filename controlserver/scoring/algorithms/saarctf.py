from controlserver.models import CheckerResult
from controlserver.scoring.algorithms.algorithm import SlaAlgorithm, StolenFlag, FlagPointAlgorithm, ScoreTickAlgorithmBase, DefensiveAlgorithm


class SlaSaarCtfDefault(SlaAlgorithm):
    def sla_points(self, tick: int, checker_result: CheckerResult) -> float:
        if checker_result.status == 'SUCCESS':
            sla_points: float = 1
        elif checker_result.status == 'RECOVERING':
            # default: half the points for a recovering tick
            sla_points = 0.5
        elif checker_result.status == 'CRASHED' or checker_result.status == 'REVOKED':
            # might be our fault, give partial points?
            sla_points = 0
        else:
            sla_points = 0
        return sla_points  # 0/1 * factor


class FlagPointsSaarCtfDefault(FlagPointAlgorithm):
    """
    Formula: OFF = 1 + sqrt(1 / num_submissions) + sqrt(1 / victim_rank)
    """

    def off_points(self, flag: StolenFlag, victim_rank: int) -> float:
        return 1.0 + \
            (1.0 / (flag.num_previous_submissions + flag.num_submissions)) ** 0.5 + \
            (1.0 / victim_rank) ** 0.5

    def off_points_previous(self, flag: StolenFlag, victim_rank: int) -> float:
        return 1.0 + \
            (1.0 / flag.num_previous_submissions) ** 0.5 + \
            (1.0 / victim_rank) ** 0.5


class DefensiveSaarCtfDefault(DefensiveAlgorithm):
    """
    FORMULA: DEF = (num_submissions / num_active_teams)^0.3 * SLA
    """
    def def_points(self, flag: StolenFlag, num_active_teams: int, victim_sla_when_issued: float) -> float:
        """Lost points caused by this flag (all steals in all ticks so far)"""
        submissions = flag.num_previous_submissions + flag.num_submissions
        return (submissions / num_active_teams) ** 0.3 * victim_sla_when_issued

    def def_points_previous(self, flag: StolenFlag, num_active_teams: int, victim_sla_when_issued: float) -> float:
        """Already lost points before this flag was stolen again"""
        submissions = flag.num_previous_submissions
        return (submissions / num_active_teams) ** 0.3 * victim_sla_when_issued


class SaarctfScoreAlgorithm(FlagPointsSaarCtfDefault, DefensiveSaarCtfDefault, SlaSaarCtfDefault, ScoreTickAlgorithmBase):
    pass
