"""
Analyzes flags
"""

import base64
import binascii
import hashlib
import hmac
import struct

from flask import Blueprint, render_template, request
from flask.typing import ResponseReturnValue

from controlserver.models import CheckerResult, Service, SubmittedFlag, Team
from saarctf_commons.config import config
import gamelib

app = Blueprint("flags", __name__)


@app.route("/flags/", methods=["GET"])
def flags_index() -> ResponseReturnValue:
    from controlserver.timer import Timer
    from gamelib import MAC_LENGTH

    flag_inner_len = (8 + MAC_LENGTH) * 4 // 3
    flag_regex = config.FLAG_PREFIX + r"\{[A-Za-z0-9-_]{" + str(flag_inner_len) + r"}\}"

    # demo flags for status checks
    demo_flags = [
        (
            "status check for teams",
            "[OK] You are team 65535",
            gamelib.gamelib.get_flag(1, 0xFFFE, -1, 0),
        ),
        (
            "status check for monitoring",
            "[OK] Status check passed. submitter=65535 max_team_id=151 max_service_id=7 online_status=2 tick=211 nop_team_id=1",
            gamelib.gamelib.get_flag(1, 0xFFFF, -1, 0),
        ),
    ]

    # analyze given flag
    flag = request.args.get("flag", "").strip()
    if flag:
        try:
            if flag[:5] != config.FLAG_PREFIX + "{" or flag[-1] != "}":
                raise Exception(config.FLAG_PREFIX + "{...}")
            data = base64.b64decode(flag[5:-1].replace("-", "+").replace("_", "/"))
            if len(data) < 8:
                raise Exception("Too short")

            stored_tick, teamid, serviceid, payload = struct.unpack("<HHHH", data[:8])
            mac = binascii.hexlify(data[8:]).decode()
            real_mac_bin = hmac.HMAC(config.SECRET_FLAG_KEY, data[:8], hashlib.sha256).digest()[:MAC_LENGTH]
            real_mac = binascii.hexlify(real_mac_bin).decode()
            team = Team.query.filter(Team.id == teamid).first()
            service = Service.query.filter(Service.id == serviceid).first()

            valid_except_mac = stored_tick <= Timer.current_tick and team and service
            valid = valid_except_mac and mac == real_mac
            repaired_flag = ""
            if valid_except_mac and not valid:
                repaired_flag = config.FLAG_PREFIX + "{" + base64.b64encode(data[:8] + real_mac_bin).decode() + "}"

            if valid:
                submissions = (
                    SubmittedFlag.query.filter(
                        SubmittedFlag.tick_issued == stored_tick,
                        SubmittedFlag.team_id == teamid,
                        SubmittedFlag.service_id == serviceid,
                        SubmittedFlag.payload == payload,
                    )
                    .order_by(SubmittedFlag.ts)
                    .all()
                )
            else:
                submissions = []

            result_store = CheckerResult.query.filter(
                CheckerResult.tick == stored_tick,
                CheckerResult.team_id == teamid,
                CheckerResult.service_id == serviceid,
            ).first()
            result_retrieve = CheckerResult.query.filter(
                CheckerResult.tick == stored_tick + 1,
                CheckerResult.team_id == teamid,
                CheckerResult.service_id == serviceid,
            ).first()

            return render_template(
                "flags.html",
                flag=flag,
                flag_regex=flag_regex,
                demo_flags=demo_flags,
                stored_tick=stored_tick,
                teamid=teamid,
                serviceid=serviceid,
                payload=payload,
                mac=mac,
                real_mac=real_mac,
                team=team,
                service=service,
                current_round=Timer.current_tick,
                valid=valid,
                repaired_flag=repaired_flag,
                submissions=submissions,
                result_store=result_store,
                result_retrieve=result_retrieve,
            )
        except Exception as e:
            return render_template(
                "flags.html",
                flag=flag,
                valid=False,
                err=str(e),
                flag_regex=flag_regex,
                demo_flags=demo_flags,
            )
    else:
        return render_template("flags.html", flag=None, flag_regex=flag_regex, demo_flags=demo_flags)
