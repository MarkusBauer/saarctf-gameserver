from abc import ABC, abstractmethod
from collections import defaultdict
from typing import TypeAlias, Sequence, TypeVar

from sqlalchemy.orm.query import Query
from sqlalchemy.orm.session import Session
from sqlalchemy.sql.expression import text
from sqlalchemy.sql.functions import func

from controlserver.models import SubmittedFlag, Service
from controlserver.scoring.algorithms.algorithm import FlagSet
from saarctf_commons.config import ScoringConfig

FirstBloodFlagT: TypeAlias = int
QT = TypeVar("QT", bound=Query)


class FirstBloodAlgorithm(ABC):
    def __init__(self, config: ScoringConfig, services: list[Service]) -> None:
        self.config = config
        self.services: dict[int, Service] = {service.id: service for service in services}

    def get_required_level(self) -> int:
        """this level is considered a "final" firstblood which won't change in the future"""
        return 1

    def init_state(self, session: Session) -> None:
        """preload whatever necessary"""
        pass

    def reset_caches(self) -> None:
        """throw away all caches, you might receive historical data soon"""
        pass

    @abstractmethod
    def get_firstbloods(self, session: Session, flags: list[SubmittedFlag]) -> list[tuple[SubmittedFlag, FirstBloodFlagT]]:
        """
        Judge if some of these flags are firstbloods (and their level).
        Results will either propagate to the database, or you'll receive a reset_caches() call first in case of retries.
        """
        raise NotImplementedError()

    @abstractmethod
    def get_firstbloods_for_recomputation(self, session: Session, service: Service) -> list[tuple[SubmittedFlag, FirstBloodFlagT]]:
        """
        Batch-compute firstbloods for a given service.
        """
        raise NotImplementedError()


class DefaultFirstBloodAlgorithm(FirstBloodAlgorithm):
    def __init__(self, config: ScoringConfig, services: list[Service]) -> None:
        super().__init__(config, services)
        self.first_blood_cache_services: dict[int, set[int]] = defaultdict(set)  # service_id => {payload1, ...}

    def reset_caches(self) -> None:
        self.first_blood_cache_services.clear()

    def get_firstbloods(self, session: Session, flags: list[SubmittedFlag]) -> list[tuple[SubmittedFlag, FirstBloodFlagT]]:
        result = []
        first_blood_candidates = FlagSet()
        for flag in flags:
            if flag.service_id in self.services and first_blood_candidates.is_new(flag):
                if self._is_first_blood(session, flag, self.services[flag.service_id]):
                    result.append((flag, 1))
                    self._record_first_blood(flag)
        return result

    def _is_first_blood(self, session: Session, flag: SubmittedFlag, service: Service) -> bool:
        # check cache if we already found a first blood for this service/payload
        if service.num_payloads > 0 and flag.payload in self.first_blood_cache_services[service.id]:
            return False
        if service.num_payloads == 0 and service.id in self.first_blood_cache_services:
            return False
        # Check database if we already have a first blood flag
        query = session.query(SubmittedFlag).filter(
            SubmittedFlag.service_id == flag.service_id,
            SubmittedFlag.is_firstblood > 0,
            SubmittedFlag.ts <= flag.ts,
        )
        if service.num_payloads > 0:
            query = query.filter(SubmittedFlag.payload == flag.payload)
        return query.count() == 0

    def _record_first_blood(self, flag: SubmittedFlag) -> None:
        """into our cache"""
        self.first_blood_cache_services[flag.service_id].add(flag.payload)

    def get_firstbloods_for_recomputation(self, session: Session, service: Service) -> list[tuple[SubmittedFlag, FirstBloodFlagT]]:
        if service.num_payloads == 0:
            flags: Sequence[SubmittedFlag] = session.query(SubmittedFlag) \
                .filter(SubmittedFlag.service_id == service.id) \
                .order_by(SubmittedFlag.ts, SubmittedFlag.id)[:1]
        else:
            data = session.execute(text(
                '''
                WITH summary AS (SELECT *, ROW_NUMBER() OVER (PARTITION BY payload, service_id ORDER BY ts, tick_submitted, id) AS rk
                                 FROM submitted_flags
                                 WHERE service_id = :serviceid)
                SELECT s.id
                FROM summary s
                WHERE s.rk = 1
                '''), {'serviceid': service.id})
            flags = session.query(SubmittedFlag) \
                .filter(SubmittedFlag.id.in_([d.id for d in data])) \
                .order_by(SubmittedFlag.ts).all()

        for flag in flags:
            self._record_first_blood(flag)
        return [(flag, 1) for flag in flags if self._is_first_blood(session, flag, service)]


class MultiFirstBloodAlgorithm(FirstBloodAlgorithm):
    def __init__(self, config: ScoringConfig, services: list[Service]) -> None:
        super().__init__(config, services)
        self.limit = config.data.get("firstblood_limit", 3)
        self.cache_max: dict[tuple[int, int], int] = defaultdict(lambda: 0)  # (service_id, payload) => max_attacked_teams
        self.cache_victims: dict[tuple[int, int, int], set[int]] = defaultdict(set)  # (service_id, payload, attacker) => set of victims

    def get_required_level(self) -> int:
        return self.config.data.get("firstblood_limit_scoreboard", self.limit)

    def reset_caches(self) -> None:
        super().reset_caches()
        self.cache_max.clear()
        self.cache_victims.clear()

    def get_firstbloods(self, session: Session, flags: list[SubmittedFlag]) -> list[tuple[SubmittedFlag, FirstBloodFlagT]]:
        """
        This is called in time order for all flags. All previous flags have already been processed and saved.
        """
        result = []
        for flag in flags:
            # from here on: all previous flags have already been processed. They are either saved to DB, or their result is in the cache.
            # so we always have to check both.

            use_payload = self.services[flag.service_id].num_payloads > 0
            key1 = (flag.service_id, flag.payload) if use_payload else (flag.service_id, 0)
            key2 = (flag.service_id, flag.payload, flag.submitted_by) if use_payload else (flag.service_id, 0, flag.submitted_by)

            # is this service+payload already "done"?
            if self.cache_max[key1] >= self.limit:
                continue
            # can this flag have some new value? (attacker/victim pair new?)
            if flag.team_id in self.cache_victims[key2]:
                continue
            # get the best-so-far attacker (if cache is stale) and re-check
            current_firstblood_level = max(self.cache_max[key1], self._get_max_firstblood_level(session, flag))
            self.cache_max[key1] = current_firstblood_level
            if current_firstblood_level >= self.limit:
                continue
            # get previous victims of this attacker and check again if this attacker/victim pair is new
            previous_victims = self._get_previous_victims(session, flag)
            self.cache_victims[key2].update(previous_victims)
            if flag.team_id in self.cache_victims[key2]:
                continue

            # this victim is new, this might have some outcome...
            self.cache_victims[key2].add(flag.team_id)
            firstblood_level = len(self.cache_victims[key2])
            if firstblood_level > current_firstblood_level:
                # yes, it's first blood level N
                result.append((flag, firstblood_level))
                self.cache_max[key1] = firstblood_level
        return result

    def _get_max_firstblood_level(self, session: Session, flag: SubmittedFlag) -> int:
        query = session.query(func.max(SubmittedFlag.is_firstblood)).filter(SubmittedFlag.is_firstblood > 0)
        query = self._filter_before_flag(query, flag)
        return query.scalar() or 0

    def _get_previous_victims(self, session: Session, flag: SubmittedFlag) -> set[int]:
        query = session.query(SubmittedFlag.team_id).filter(SubmittedFlag.submitted_by == flag.submitted_by)
        query = self._filter_before_flag(query, flag)
        return set(victim_id for victim_id, in query.all())

    def _filter_before_flag(self, query: QT, flag: SubmittedFlag) -> QT:
        query = query.filter(SubmittedFlag.service_id == flag.service_id, SubmittedFlag.ts < flag.ts)
        if self.services[flag.service_id].num_payloads > 0:
            query = query.filter(SubmittedFlag.payload == flag.payload)
        return query

    def get_firstbloods_for_recomputation(self, session: Session, service: Service) -> list[tuple[SubmittedFlag, FirstBloodFlagT]]:
        result: list[tuple[SubmittedFlag, FirstBloodFlagT]] = []
        min_tick, max_tick = session.query(func.min(SubmittedFlag.tick_submitted), func.max(SubmittedFlag.tick_submitted)) \
            .filter(SubmittedFlag.service_id == service.id).one()
        if min_tick is None or max_tick is None:
            return result

        for tick in range(min_tick, max_tick + 1):
            flags = list(session.query(SubmittedFlag)
                         .filter(SubmittedFlag.tick_submitted == tick, SubmittedFlag.service_id == service.id)
                         .order_by(SubmittedFlag.ts, SubmittedFlag.id))
            new_firstbloods = self.get_firstbloods(session, flags)
            result += new_firstbloods

            # all payloads done? then no further ticks checked
            if len(new_firstbloods) > 0:
                if all(self.cache_max[(service.id, pl)] >= self.limit for pl in range(0, max(1, service.num_payloads))):
                    break
        return result
