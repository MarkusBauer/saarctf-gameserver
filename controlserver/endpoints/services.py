"""
List Services
"""

from collections import defaultdict
from flask import Blueprint, jsonify, make_response, render_template, request
from flask.typing import ResponseReturnValue
import json

from controlserver.logger import log
from controlserver.models import LogMessage, Service, SubmittedFlag, db_session, expect, Team

app = Blueprint("services", __name__)


@app.route("/api/services", methods=["GET"])
def api_services() -> str:
    data = []
    for service in Service.query.all():
        data.append(
            {
                "id": service.id,
                "flagstores": service.num_payloads,
                "name": service.name,
            }
        )
    return json.dumps(data)


@app.route("/services/", methods=["GET"])
def services_index() -> ResponseReturnValue:
    services = Service.query.order_by(Service.id).all()
    teams = Team.query.order_by(Team.id).all()

    first_bloods = defaultdict(list)
    flags = SubmittedFlag.query \
        .filter(SubmittedFlag.is_firstblood > 0) \
        .order_by(SubmittedFlag.ts, SubmittedFlag.tick_submitted, SubmittedFlag.id) \
        .all()
    for flag in flags:
        first_bloods[flag.service_id].append(flag)

    all_firstbloods = request.args.get("firstbloods", "") == "all"
    if not all_firstbloods:
        for k in first_bloods:
            level_per_payload: dict[int, int] = {}
            for flag in first_bloods[k]:
                level_per_payload[flag.payload] = max(flag.is_firstblood, level_per_payload.get(flag.payload, 0))
            first_bloods[k] = [flag for flag in first_bloods[k] if level_per_payload[flag.payload] == flag.is_firstblood]

    return render_template("services.html", services=services, teams=teams, first_bloods=first_bloods)


@app.route("/services/checker_status", methods=["POST"])
def services_set_checker_status() -> ResponseReturnValue:
    service: Service = expect(Service.query.get(request.form["id"]))
    if service:
        service.checker_enabled = request.form["status"] == "1"
        session = db_session()
        session.add(service)
        session.commit()
        return "OK"
    else:
        return "Not found"


@app.route("/services/eno_config_valid", methods=["GET"])
def services_eno_config_valid() -> ResponseReturnValue:
    import requests

    def check_service(service: Service) -> str | None:
        try:
            url = service.runner_config["url"]
        except KeyError:
            return "No checker url set!"

        try:
            eno_service_response = requests.get(f"{url}/service", timeout=1.0)
        except Exception as e:
            return f"Failed to reach checker {service.name} at {url}"

        try:
            eno_service_info = eno_service_response.json()
            flagVariants = eno_service_info["flagVariants"]
            remote_name = eno_service_info["serviceName"]
        except Exception as _e:
            return f"Failed to decode /service"

        if service.name.lower() != remote_name.lower():
            return f"Url points to wrong service {remote_name}"

        if service.num_payloads != flagVariants:
            return f"Num Payloads should be {flagVariants}"

        if service.flags_per_tick != flagVariants:
            errors[service.name] = f"Flags per tick should be {flagVariants}"

        if service.flag_ids != "".join(["custom"] * flagVariants):
            return f"Flags per tick should be {flagVariants}"

        return None

    config_valid = True
    errors = {}
    services = Service.query.order_by(Service.id).all()
    for service in services:
        if service.checker_runner != "eno:EnoCheckerRunner":
            continue

        error = check_service(service)
        if error is None:
            errors[service.name] = "OK!"
            continue

        config_valid = False
        errors[service.name] = error

    if not config_valid:
        errors_formatted = ""
        for service_name, err in errors.items():
            errors_formatted += f"    {service_name}: {err}\n"
        log("Services", "EnoConfig invalid", f"{errors_formatted}", LogMessage.ERROR)

    return jsonify(errors), 200 if config_valid else 500
