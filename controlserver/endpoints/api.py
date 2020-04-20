"""
API to interact with other programs
"""
from flask import Blueprint, request

from controlserver.models import LogMessage
from controlserver.logger import log

app = Blueprint('api', __name__)


@app.route('/api/grafana_warning', methods=['POST'])
def api_grafana_warning():
	data = request.get_json()
	if not data:
		return 'Invalid', 500
	if data['state'] != 'alerting':
		return 'We only want alerts', 500
	text = data['message'] + '\nRule: ' + data['ruleName'] + '\n' + data['ruleUrl']
	log('Grafana', data['title'], text, LogMessage.WARNING)
	return 'OK'
