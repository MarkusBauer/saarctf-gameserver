"""
Calculate results and ranking for each team/tick. That's a two-step process:

Results (TeamPoints):
("service" columns of the scoreboard)
- One entry per tick/team/service
- Contains:
  - flags stolen up to this tick
  - sla for this service (up to this tick)
  - ...

Ranking (TeamRanking):
("team" columns of the scoreboard)
- One entry per tick/team
- Contains:
  - total points
  - rank number [1..N]


Want to edit the score calculation? Check `calculate_scoring_for_tick` and `calculate_ranking_per_tick`.


// Dict key are typically (team_id, service_id).

"""

from collections import defaultdict
from typing import Sequence

from sqlalchemy import func, distinct, and_, text
from sqlalchemy.orm import defer, Session, aliased
from sqlalchemy.sql.functions import count

from controlserver.logger import log_to_session
from controlserver.models import (
    Team,
    TeamPoints,
    TeamRanking,
    SubmittedFlag,
    Service,
    CheckerResult,
    TeamPointsLite,
    CheckerResultLite,
    LogMessage,
    expect,
    db_session_2,
)
from controlserver.scoring.algorithms.algorithm import (
    FlagSet,
    StolenFlag,
    TeamServicePair,
    TickTeamPair,
)

from controlserver.scoring.algorithms.factory import ScoreAlgorithmFactory, FirstBloodAlgorithmFactory
from saarctf_commons.config import ScoringConfig
from saarctf_commons.db_utils import retry_on_sql_error


class ScoringCalculation:
    def __init__(self, config: ScoringConfig) -> None:
        self.config = config
        with db_session_2() as session:
            # move to algorithm???
            services = list(session.query(Service).all())
            for service in services:
                session.expunge(service)
            self.first_blood = FirstBloodAlgorithmFactory.build(config, services)
            self.first_blood.init_state(session)

    def get_considered_teams(self, session: Session) -> list[Team]:
        return list(session.query(Team).order_by(Team.id).all())

    def get_considered_services(self, session: Session) -> list[Service]:
        return list(session.query(Service).order_by(Service.id).all())

    def scoring_and_ranking(self, tick: int) -> None:
        self.calculate_scoring_for_tick(tick)
        self.calculate_ranking_per_tick(tick)

    # ----- Results ---

    def get_results_for_tick_lite(
        self,
        session: Session,
        tick: int,
        teams: list[int] | None = None,
        services: list[Service] | None = None,
    ) -> dict[TeamServicePair, TeamPointsLite]:
        """
        Get the results per team and service from a tick, calculate if not present in database.
        This method might be overridden by subclasses.
        :param session:
        :param tick:
        :param teams: List of all team IDs
        :param services: List of all services
        :return: Dict mapping (team_id, service_id) to Result
        """
        return self._get_results_for_tick_lite(session, tick, teams, services)

    def _get_results_for_tick_lite(
        self,
        session: Session,
        tick: int,
        teams: list[int] | None = None,
        services: list[Service] | None = None,
    ) -> dict[TeamServicePair, TeamPointsLite]:
        """do not override (computation should be unaffected)"""
        if teams is None:
            teams = [team_id for (team_id,) in session.query(Team.id).all()]
        if services is None:
            services = session.query(Service).all()
            assert services is not None
        if tick <= 0:
            results: dict[TeamServicePair, TeamPointsLite] = {}
            for id in teams:
                for service in services:
                    results[(id, service.id)] = TeamPointsLite(
                        # define here: default points for tick 0
                        team_id=id, service_id=service.id, tick=tick,
                        flag_captured_count=0, flag_stolen_count=0,
                        off_points=0.0, def_points=0.0, sla_points=0.0
                    )
            return results
        else:
            team_points = TeamPointsLite.query(session).filter(TeamPoints.tick == tick).all()
            if len(team_points) < len(teams) * len(services):
                self._calculate_scoring_for_tick(session, tick)
                team_points = TeamPointsLite.query(session).filter(TeamPoints.tick == tick).all()
            return {(tp.team_id, tp.service_id): TeamPointsLite(*tp) for tp in team_points}

    def _save_teampoints(
        self,
        session: Session,
        tick: int,
        teampoints: dict[TeamServicePair, TeamPoints]
                    | dict[TeamServicePair, TeamPointsLite],
    ) -> None:
        session.query(TeamPoints).filter(TeamPoints.tick == tick).delete()
        TeamPoints.efficient_insert(tick, teampoints.values(), session=session)

    def _get_checker_results(self, session: Session, tick: int) -> dict[TeamServicePair, CheckerResult]:
        # TODO queries
        if tick <= 0:
            return defaultdict(lambda: CheckerResult(tick=tick, status='REVOKED'))
        checker_results: list[CheckerResult] = session.query(CheckerResult).filter(CheckerResult.tick == tick) \
            .options(defer(CheckerResult.output)).all()
        result: dict[TeamServicePair, CheckerResult] = defaultdict(
            lambda: CheckerResult(tick=tick, status='REVOKED')
        )
        for r in checker_results:
            result[(r.team_id, r.service_id)] = r
        return result

    def get_checker_results_lite(self, session: Session, tick: int) -> dict[TeamServicePair, CheckerResultLite]:
        if tick <= 0:
            return defaultdict(lambda: CheckerResultLite(0, 0, tick, 'REVOKED'))
        checker_results = session.query(
            CheckerResult.team_id, CheckerResult.service_id, CheckerResult.status, CheckerResult.run_over_time,
            CheckerResult.message) \
            .filter(CheckerResult.tick == tick).all()
        result: dict[TeamServicePair, CheckerResultLite] = defaultdict(
            lambda: CheckerResultLite(0, 0, tick, 'REVOKED')
        )
        for team_id, service_id, status, run_over_time, message in checker_results:
            result[(team_id, service_id)] = \
                CheckerResultLite(team_id, service_id, tick, status, run_over_time, message)
        return result

    def _record_first_blood(self, session: Session, flag: SubmittedFlag, service: Service, level: int = 1, write_log: bool = True) -> None:
        if write_log:
            submitted_by_team: Team = expect(session.get(Team, flag.submitted_by))
            victim_team: Team = expect(session.get(Team, flag.team_id))
            log_to_session(
                session,
                "scoring",
                f'First Blood: "{submitted_by_team.name}" on "{service.name}" (flag {flag.payload})',
                f"Time: {flag.ts.strftime('%H:%M:%S')}\nStolen from: {victim_team.name}\n"
                f"Submitted by: {submitted_by_team.name}\n"
                f"Flag #{flag.id}, payload {flag.payload}, issued in tick {flag.tick_issued}.",
                level=LogMessage.NOTIFICATION,
            )

        session.query(SubmittedFlag).filter(SubmittedFlag.id == flag.id).update({'is_firstblood': level})

    @retry_on_sql_error(attempts=2)
    def recompute_first_blood_flags(self) -> None:
        """
        Drop and recompute all first-blood markings on submitted flags. Restart other scoring calculators afterwards (to clear their cache).
        :return:
        """
        # Remove all previous first blood flags
        with db_session_2() as session:
            session.query(SubmittedFlag).filter(SubmittedFlag.is_firstblood > 0).update({SubmittedFlag.is_firstblood: 0})
            self.first_blood.reset_caches()
            for service in self.first_blood.services.values():
                print(f'recompute firstbloods for {service.name}...')
                flags_with_fp = self.first_blood.get_firstbloods_for_recomputation(session, service)
                for flag, fp_value in flags_with_fp:
                    self._record_first_blood(session, flag, service, level=fp_value, write_log=False)
            session.commit()

    def _ranking_for_last_ticks(self, session: Session, tick: int) -> dict[TickTeamPair, int]:
        """
        :param session:
        :param tick:
        :return: Return (tick, team_id) => rank for last FLAG_ROUNDS_VALID ticks
        """
        ranks = session.query(TeamRanking.tick, TeamRanking.team_id, TeamRanking.rank) \
            .filter(TeamRanking.tick >= tick - self.config.flags_rounds_valid - 1,
                    TeamRanking.tick < tick).all()
        return {(tick, team_id): rank for tick, team_id, rank in ranks}

    def _sla_delta_for(self, session: Session, service_id: int, tick: int) -> dict[int, float]:
        """
        :return: Dict: team_id => sla_delta
        """
        tp = session.query(TeamPoints.team_id, TeamPoints.sla_delta) \
            .filter(TeamPoints.service_id == service_id, TeamPoints.tick == tick).all()
        return {team_id: sla_delta for team_id, sla_delta in tp}

    def _get_submitted_flags(self, session: Session, tick: int) -> list[StolenFlag]:
        """
        Result format: [
            (flag, num_previous_submissions, num_submissions, previous_submitted_ids)
        ]
        """
        sf1 = aliased(SubmittedFlag)  # submitted flags
        sf2 = aliased(SubmittedFlag)  # count for each flag: # submissions before this tick
        sf3 = aliased(SubmittedFlag)  # count for each flag: # submissions this tick
        query = session.query(sf1, count(distinct(sf2.id)), count(distinct(sf3.id)),
                              func.array_agg(distinct(sf2.submitted_by))) \
            .outerjoin(sf2, and_(sf2.tick_submitted < tick,
                                 sf2.tick_submitted >= tick - self.config.flags_rounds_valid - 2,
                                 sf1.team_id == sf2.team_id, sf1.service_id == sf2.service_id,
                                 sf1.tick_issued == sf2.tick_issued,
                                 sf1.payload == sf2.payload)) \
            .outerjoin(sf3, and_(sf3.tick_submitted == tick, sf1.team_id == sf3.team_id,
                                 sf1.service_id == sf3.service_id,
                                 sf1.tick_issued == sf3.tick_issued, sf1.payload == sf3.payload)) \
            .filter(sf1.tick_submitted == tick).order_by(sf1.ts, sf1.tick_submitted, sf1.id) \
            .group_by(sf1)  # type: ignore[arg-type]
        flags = query.all()
        result = []
        for flag, num_previous_submissions, num_submissions, previous_submitter_ids in flags:
            session.expunge(flag)
            result.append(StolenFlag(
                flag=flag,
                num_previous_submissions=num_previous_submissions,
                num_submissions=num_submissions,
                previous_submitter_ids=previous_submitter_ids
            ))
        return result

    @retry_on_sql_error(attempts=2)
    def calculate_scoring_for_tick(self, tick: int) -> None:
        """
        Recalculate the results for one tick and save them.
        If calculation depends on previous results, these are calculated as well.
        :param tick:
        """

        with db_session_2() as session:
            self._calculate_scoring_for_tick(session, tick)

    def _calculate_scoring_for_tick(self, session: Session, tick: int) -> None:
        teams: list[int] = [id for (id,) in session.query(Team.id).all()]
        services: list[Service] = session.query(Service).all()
        algo = ScoreAlgorithmFactory.build(self.config, teams, services)

        last_tick_points = self._get_results_for_tick_lite(session, tick - 1, teams, services)
        team_rank_in_tick = self._ranking_for_last_ticks(session, tick)
        checker_results = self._get_checker_results(session, tick)
        flags = self._get_submitted_flags(session, tick)
        for flag in flags:
            # get the SLA at flag handout time for every stolen flag
            key = (flag.flag.service_id, flag.flag.tick_issued)
            if key not in algo.sla_delta_for:
                algo.sla_delta_for[key] = self._sla_delta_for(session, flag.flag.service_id, flag.flag.tick_issued)

        try:
            self.compute_firstblood_incremental(session, [sf.flag for sf in flags])

            team_points = \
                algo.calculate_scoring_for_tick(tick, checker_results, last_tick_points, team_rank_in_tick, flags)

            # 5. Finally - save the new results
            self._save_teampoints(session, tick, team_points)
            # Commit everything
            session.commit()
        except:
            self.first_blood.reset_caches()  # if anything goes wrong, we should recreate our caches!
            raise

    def compute_firstblood_incremental(self, session: Session, flags: list[SubmittedFlag]) -> None:
        firstbloods = self.first_blood.get_firstbloods(session, flags)
        for fp_flag, fp_value in firstbloods:
            self._record_first_blood(session, fp_flag, self.first_blood.services[fp_flag.service_id], level=fp_value, write_log=True)

    # ----- Ranking ---

    def get_ranking_for_tick(self, session: Session, tick: int) -> list[TeamRanking]:
        """
        Gives the order of teams for a given tick, including their total points
        :param tick:
        :param session:
        :return:
        """
        if tick <= 0:
            teams: list[Team] = session.query(Team).order_by(Team.id).all()
            return [
                TeamRanking(team_id=team.id, team=team, tick=0, points=0.0, rank=1)  # type: ignore[misc]
                for team in teams
            ]
        ranking = (
            session.query(TeamRanking)
            .filter(TeamRanking.tick == tick)
            .order_by(TeamRanking.rank, TeamRanking.team_id)
            .all()
        )
        if not ranking:
            self.calculate_ranking_per_tick(tick)
            ranking = (
                session.query(TeamRanking)
                .filter(TeamRanking.tick == tick)
                .order_by(TeamRanking.rank, TeamRanking.team_id)
                .all()
            )
        return ranking

    def calculate_ranking_per_tick(self, tick: int) -> None:
        """
        Compute the ranking, based on the results.
        :param tick:
        :return:
        """
        with db_session_2() as session:
            session.query(TeamRanking).filter(TeamRanking.tick == tick).delete()
            session.commit()
            teams: list[int] = [id for (id,) in session.query(Team.id).all()]
            results = self._get_results_for_tick_lite(session, tick, teams)
            ranking: dict[int, TeamRanking] = {
                id: TeamRanking(tick=tick, team_id=id, points=0.0) for id in teams  # type: ignore[misc]
            }
            # Computation - final points = off_points + def_points + sla_points
            for result in results.values():
                ranking[result.team_id].points += \
                    result.off_points + result.def_points + result.sla_points  # type: ignore[operator]
            # do the ranking and save
            ranks = self._order_by_points(list(ranking.values()))
            session.bulk_save_objects(ranks)
            session.commit()

    def _order_by_points(self, ranking: list[TeamRanking]) -> list[TeamRanking]:
        """
        Order the given TeamRanking instances by points, and set the "ranking" parameter
        :param ranking:
        :return:
        """
        ranking.sort(key=lambda tr: tr.points, reverse=True)
        i = 1
        previous_rank = None
        for rank in ranking:
            if previous_rank and previous_rank.points == rank.points:
                rank.rank = previous_rank.rank
            else:
                rank.rank = i
            previous_rank = rank
            if rank.points > 0:
                i += 1
        return ranking
