"""
List Services
"""
from collections import defaultdict
from flask import Blueprint, render_template, request
from flask.typing import ResponseReturnValue

from controlserver.models import Service, SubmittedFlag, db_session, expect

app = Blueprint('services', __name__)


@app.route('/services/', methods=['GET'])
def services_index() -> ResponseReturnValue:
    services = Service.query.order_by(Service.id).all()

    first_bloods = defaultdict(list)
    for flag in SubmittedFlag.query.filter(SubmittedFlag.is_firstblood).order_by(SubmittedFlag.ts).all():
        first_bloods[flag.service_id].append(flag)

    return render_template('services.html', services=services, first_bloods=first_bloods)


@app.route('/services/checker_status', methods=['POST'])
def services_set_checker_status() -> ResponseReturnValue:
    service: Service = expect(Service.query.get(request.form['id']))
    if service:
        service.checker_enabled = request.form['status'] == '1'
        session = db_session()
        session.add(service)
        session.commit()
        return 'OK'
    else:
        return 'Not found'
