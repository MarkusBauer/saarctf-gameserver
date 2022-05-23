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
	if 'ruleName' in data:
		text = data['message'] + '\nRule: ' + data['ruleName'] + '\n' + data['ruleUrl']
		log('Grafana', data['title'], text, LogMessage.WARNING)
	elif 'alerts' in data:
		for alert in data['alerts']:
			if alert['status'] != 'firing':
				continue
			title = '[Grafana] ' + alert['labels']['alertname']
			if 'rulename' in alert['labels']:
				title += ' / ' + alert['labels']['rulename']
			text = []
			if 'dashboardURL' in alert and alert['dashboardURL']:
				text.append('Dashboard: ' + alert['dashboardURL'])
			if 'panelURL' in alert and alert['panelURL']:
				text.append('Panel: ' + alert['panelURL'])
			log('Grafana', title, '\n'.join(text), LogMessage.WARNING)
	else:
		text = data['title'] + '\n' + data['message']
		log('Grafana', data['title'], text, LogMessage.WARNING)
	return 'OK'
