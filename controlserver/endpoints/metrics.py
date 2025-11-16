from flask import Blueprint, request
from flask.typing import ResponseReturnValue
from saarctf_commons.metric_utils import Metrics

app = Blueprint("metrics", __name__)


@app.route("/metrics/write", methods=["POST"])
def metrics_write() -> ResponseReturnValue:
    data = request.get_json()
    for record in data:
        Metrics.record_many(
            record["metric"],
            record["values"],
            record.get("ts", None),
            **record.get("attributes", {}),
        )
    return "OK"
