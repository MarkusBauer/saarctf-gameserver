from flask import Blueprint, request
from influxdb import InfluxDBClient
from saarctf_commons.config import POSTGRES

app = Blueprint('influx', __name__)


@app.route('/influx/write', methods=['POST'])
def influx_write():
	data = request.get_json()
	host = POSTGRES['server']
	# TODO FOR TODAY
	host = '10.32.250.2'
	client = InfluxDBClient(host=host, port=8086, username='admin', password=POSTGRES['password'])
	with client:
		client.switch_database('saarctf')
		if client.write_points(data, protocol='line', batch_size=64):
			return 'OK'
		else:
			return 'Error', 500
