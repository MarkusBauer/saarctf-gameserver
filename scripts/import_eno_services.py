import os
import sys
from argparse import ArgumentParser, Namespace
from json import loads
from logging import getLogger
from pathlib import Path

from requests import get

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.models import Service, db_session, init_database
from saarctf_commons.config import config, load_default_config
from saarctf_commons.redis import NamedRedisConnection

LOGGER = getLogger(__name__)


def fetch_service_info(host: str) -> dict:
    resp = get(f"{host}/service", timeout=5)
    data = resp.json()
    return {
        "name": data["serviceName"],
        "checker_timeout": config.TICK_DURATION_DEFAULT,
        "checker_runner": "eno:EnoCheckerRunner",
        "checker_script": "nono",
        "runner_config": {"url": host},
        "num_payloads": data["flagVariants"],
        "flags_per_tick": data["flagVariants"],
        "flag_ids": ",".join("custom" for _ in range(data["flagVariants"])),
    }


def add_service(service: dict) -> None:
    session = db_session()
    service_model = Service(
        id=service["id"],
        name=service["name"],
        checker_timeout=service["checker_timeout"],
        checker_runner=service["checker_runner"],
        checker_script=service["checker_script"],
        runner_config=service["runner_config"],
        num_payloads=service["num_payloads"],
        flag_ids=service["flag_ids"],
        flags_per_tick=service["flags_per_tick"],
    )
    session.add(service_model)
    session.commit()


def main(args: Namespace) -> None:
    init_database()
    services = {service_model.name: service_model for service_model in Service.query.all()}
    if args.reset:
        for _, service in services.items():
            db_session().delete(service)

    service_urls = loads(args.file.read_text())

    for idx, (_, host) in enumerate(service_urls.items()):
        new_service = fetch_service_info(host)
        new_service["id"] = idx + 1
        LOGGER.info("Fetched %s", new_service["name"])
        add_service(new_service)
        LOGGER.info("Imported %s", new_service["name"])


if __name__ == "__main__":
    load_default_config()
    config.set_script()
    NamedRedisConnection.set_clientname("script-" + os.path.basename(__file__))
    parser = ArgumentParser()
    parser.add_argument("file", type=Path, help="File containing service urls")
    parser.add_argument(
        "-r", "--reset", action="store_true", help="Delete services in database"
    )
    main(parser.parse_args())
