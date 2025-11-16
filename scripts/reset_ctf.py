import os
import shutil
import sys
from typing import Any

import redis

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.models import init_database
from controlserver.scoring.scoring import ScoringCalculation
from controlserver.scoring.scoreboard import default_scoreboards
from saarctf_commons.config import config, load_default_config
from saarctf_commons.redis import NamedRedisConnection, get_redis_connection

"""
NO ARGUMENTS
"""


def query_yes_no(question: str, default: str = "yes") -> bool:
    """Ask a yes/no question via raw_input() and return their answer.

    https://stackoverflow.com/a/3041990

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """
    valid = {"yes": True, "y": True, "ye": True, "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError(f"invalid default answer: '{default}'")

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == "":
            return valid[default]
        if choice in valid:
            return valid[choice]
        sys.stdout.write("Please respond with 'yes' or 'no' (or 'y' or 'n').\n")


def reset_redis() -> None:
    get_redis_connection().flushdb()
    conn = redis.StrictRedis.from_url(config.celery_redis_url())
    conn.flushdb()

    from controlserver.timer import CTFTimer

    timer = CTFTimer()
    timer.on_update_times()  # update without init - write default values


def reset_broker() -> None:
    url = config.celery_url()
    if url.startswith("redis:"):
        redis.StrictRedis.from_url(url).flushdb()
    else:
        from kombu import Connection, Message, Queue

        def accept(body: Any, message: Message) -> None:
            message.ack()

        with Connection(url) as connection:
            with connection.Consumer(Queue("celery"), callbacks=[accept]) as _:
                try:
                    while True:
                        connection.drain_events(timeout=1)
                except TimeoutError:
                    pass


def reset_database(include_storage: bool = False) -> None:
    init_database()
    import controlserver.models
    for m in ["TeamPoints", "TeamRanking", "SubmittedFlag", "CheckerResult", "LogMessage", "Tick"]:
        count = getattr(controlserver.models, m).query.delete()
        print("- dropped {} entries from {}".format(count, m))
    if include_storage:
        for m in ["CheckerFile", "CheckerFilesystem"]:
            count = getattr(controlserver.models, m).query.delete()
            print("- dropped {} entries from {}".format(count, m))
        controlserver.models.Service.query.update({controlserver.models.Service.package: None})
    controlserver.models.db_session().commit()


def reset_scoreboard() -> None:
    for scoreboard in default_scoreboards(ScoringCalculation(config.SCORING)):
        path = scoreboard.output / "api"
        if path.exists():
            shutil.rmtree(path)


def reset_ctf(force: bool = False) -> None:
    if not force and not query_yes_no("Do you really want to wipe the whole CTF?", "no"):
        return

    print("Wiping redis ...")
    reset_redis()

    print("Wiping broker ...")
    reset_broker()

    print("Wiping database ...")
    reset_database()

    reset_scoreboard()

    print("Done. I suggest restarting other components.")


if __name__ == "__main__":
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname("script-" + os.path.basename(__file__))
    reset_ctf("--force" in sys.argv)
