import os
import sys


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.models import init_database, db_session_2, Tick
from controlserver.timer import redis_set_and_publish, CTFState
from saarctf_commons.redis import NamedRedisConnection, get_redis_connection
from saarctf_commons.config import config, load_default_config
from saarctf_commons.debug_sql_timing import print_query_stats

"""
Tries to rebuild the minimal necessary redis data from other datasources.
ARGUMENTS: none
"""


def reconstruct_redis() -> None:
    with db_session_2() as session:
        ticks = list(session.query(Tick).order_by(Tick.tick).all())
        ticks_by_number: dict[int, Tick] = {tick.tick: tick for tick in ticks}
        last_completed_tick = max(0, *(tick.tick for tick in ticks if tick.end))
        last_tick = max(0, *(tick.tick for tick in ticks))
        state = CTFState.STOPPED
        if 0 < last_completed_tick < last_tick:
            state = CTFState.SUSPENDED
        estimated_time = None
        current_start = None
        current_end = None
        if last_completed_tick > 0:
            current_start = int(ticks_by_number[last_completed_tick].start.timestamp())
            current_end = int(ticks_by_number[last_completed_tick].end.timestamp())
            dt = ticks_by_number[last_completed_tick].end - ticks_by_number[last_completed_tick].start
            estimated_time = int(round(dt.seconds / 5.0)) * 5
        print(f'  last tick: {last_tick}')
        print(f'  last completed tick: {last_completed_tick}  <-- restore end of this tick')
        print(f'  state: {state.name}')
        print(f'  estimated tick time: {estimated_time} seconds')

        with get_redis_connection() as redis:
            redis_set_and_publish("timing:state", state.name, redis)
            redis_set_and_publish("timing:desiredState", state.name, redis)
            redis_set_and_publish("timing:currentRound", last_completed_tick, redis)
            redis_set_and_publish("timing:roundStart", current_start, redis)
            redis_set_and_publish("timing:roundEnd", current_end, redis)
            redis_set_and_publish("timing:roundTime", estimated_time, redis)
            redis_set_and_publish("timing:stopAfterRound", None, redis)
            redis_set_and_publish("timing:startAt", None, redis)

            for tick in ticks:
                if tick.start:
                    redis.set(f'round.{tick.tick}.start', int(tick.start.timestamp()))
                if tick.end:
                    redis.set(f'round.{tick.tick}.end', int(tick.end.timestamp()))
                if tick.start and tick.end:
                    redis.set(f'round.{tick.tick}.time', int(round(tick.end.timestamp() - tick.start.timestamp())))


if __name__ == "__main__":
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname("script-" + os.path.basename(__file__))
    init_database()

    reconstruct_redis()

    print("Done. Your checklist for now:")
    print("1. Restart CTF Timer")
    print("2. Check status in dashboard")
    print("3. Set last tick")
    print("4. Rebuild the scoreboard")
    print("5. Continue the game")
    if "--stats" in sys.argv:
        print_query_stats()
