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

from controlserver.models import Service, Team, SubmittedFlag, CheckerResult
from saarctf_commons.config import config

app = Blueprint('flags', __name__)


@app.route('/flags/', methods=['GET'])
def flags_index() -> ResponseReturnValue:
    from gamelib import MAC_LENGTH
    from controlserver.timer import Timer

    flag_inner_len = (8 + MAC_LENGTH) * 4 // 3
    flag_regex = r'SAAR\{[A-Za-z0-9-_]{' + str(flag_inner_len) + r'}\}'

    # analyze given flag
    flag = request.args.get('flag', '').strip()
    if flag:
        try:
            if flag[:5] != 'SAAR{' or flag[-1] != '}':
                raise Exception('SAAR{...}')
            data = base64.b64decode(flag[5:-1].replace('-', '+').replace('_', '/'))
            if len(data) < 8:
                raise Exception('Too short')

            stored_round, teamid, serviceid, payload = struct.unpack('<HHHH', data[:8])
            mac = binascii.hexlify(data[8:]).decode()
            real_mac_bin = hmac.HMAC(config.SECRET_FLAG_KEY, data[:8], hashlib.sha256).digest()[:MAC_LENGTH]
            real_mac = binascii.hexlify(real_mac_bin).decode()
            team = Team.query.filter(Team.id == teamid).first()
            service = Service.query.filter(Service.id == serviceid).first()

            valid_except_mac = stored_round <= Timer.currentRound and team and service
            valid = valid_except_mac and mac == real_mac
            repaired_flag = ''
            if valid_except_mac and not valid:
                repaired_flag = 'SAAR{' + base64.b64encode(data[:8] + real_mac_bin).decode() + '}'

            if valid:
                submissions = SubmittedFlag.query \
                    .filter(SubmittedFlag.round_issued == stored_round, SubmittedFlag.team_id == teamid, SubmittedFlag.service_id == serviceid,
                            SubmittedFlag.payload == payload) \
                    .order_by(SubmittedFlag.ts).all()
            else:
                submissions = []

            result_store = CheckerResult.query.filter(CheckerResult.round == stored_round, CheckerResult.team_id == teamid,
                                                      CheckerResult.service_id == serviceid).first()
            result_retrieve = CheckerResult.query.filter(CheckerResult.round == stored_round + 1, CheckerResult.team_id == teamid,
                                                         CheckerResult.service_id == serviceid).first()

            return render_template('flags.html', flag=flag, flag_regex=flag_regex,
                                   stored_round=stored_round, teamid=teamid, serviceid=serviceid, payload=payload, mac=mac, real_mac=real_mac,
                                   team=team, service=service, current_round=Timer.currentRound,
                                   valid=valid, repaired_flag=repaired_flag, submissions=submissions,
                                   result_store=result_store, result_retrieve=result_retrieve)
        except Exception as e:
            return render_template('flags.html', flag=flag, valid=False, err=str(e), flag_regex=flag_regex)
    else:
        return render_template('flags.html', flag=None, flag_regex=flag_regex)
