"""
Displays checker results - list or single entry.
"""

from flask import Blueprint, render_template, request
from flask.json import jsonify
from flask.typing import ResponseReturnValue
from sqlalchemy.orm import joinedload

from controlserver.endpoints.utils import Pagination, paginate_query
from controlserver.models import CheckerResult, Service, Team
from saarctf_commons.config import config

app = Blueprint("checker_results", __name__)


@app.route("/checker_results/", methods=["GET"])
@app.route("/checker_results/<int:page>", methods=["GET"])
def checker_results_index(page: int = 1) -> ResponseReturnValue:
    query = CheckerResult.query.options(joinedload(CheckerResult.team)).options(joinedload(CheckerResult.service))

    per_page = 50
    order = request.args.get("sort", "id")
    direction = request.args.get("dir", "desc")
    order_column = getattr(CheckerResult, order)
    if direction == "desc":
        order_column = order_column.desc()
    query = query.order_by(order_column)

    filter_status = request.args["filter_status"].split("|") if "filter_status" in request.args else None
    if filter_status is not None:
        query = query.filter(CheckerResult.status.in_(filter_status))

    filter_team = int(request.args.get("filter_team", 0)) or None
    if filter_team:
        query = query.filter(CheckerResult.team_id == filter_team)

    filter_service = int(request.args.get("filter_service", 0)) or None
    if filter_service:
        query = query.filter(CheckerResult.service_id == filter_service)

    filter_tick = int(request.args.get("filter_tick", 0)) or None
    if filter_tick:
        query = query.filter(CheckerResult.tick == filter_tick)

    checker_results: Pagination = paginate_query(query, page, per_page)
    if checker_results.pages < page:
        page = checker_results.pages if checker_results.pages > 0 else 1
        checker_results = paginate_query(query, page, per_page)

    teams = [(team.id, team.name) for team in Team.query.order_by(Team.name).all()]
    services = [(service.id, service.name) for service in Service.query.order_by(Service.name).all()]
    return render_template(
        "checker_results.html",
        checker_results=checker_results,
        FLOWER_URL=config.FLOWER_URL,
        states=CheckerResult.states,
        query_string=request.query_string.decode("utf8"),
        teams=teams,
        services=services,
        filter_team=filter_team,
        filter_service=filter_service,
        filter_status=filter_status,
    )


@app.route("/checker_results/view/<int:id>", methods=["GET"])
def checker_results_view(id: int | None = None) -> ResponseReturnValue:
    checker_result: CheckerResult | None = CheckerResult.query.options(joinedload(CheckerResult.team)).options(joinedload(CheckerResult.service)) \
        .filter(CheckerResult.id == id).first()
    if not checker_result:
        return render_template("404.html"), 404
    if request.headers.get("accept", "") == "application/json":
        return jsonify(
            {
                "id": checker_result.id,
                "tick": checker_result.tick,
                "team_id": checker_result.team_id,
                "service_id": checker_result.service_id,
                "status": checker_result.status,
                "message": checker_result.message,
                "time": checker_result.time,
                "output": checker_result.output,
                "finished": checker_result.finished,
            }
        )
    return render_template(
        "checker_results_view.html",
        checker_result=checker_result,
        FLOWER_URL=config.FLOWER_URL,
    )
