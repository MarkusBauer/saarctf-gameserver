from flask import Blueprint, request
from flask.typing import ResponseReturnValue
from influxdb import InfluxDBClient
from saarctf_commons.config import config

app = Blueprint('influx', __name__)


@app.route('/influx/write', methods=['POST'])
def influx_write() -> ResponseReturnValue:
    data = request.get_json()
    host = config.POSTGRES['server']
    client = InfluxDBClient(host=host, port=8086, username='admin', password=config.POSTGRES['password'])
    with client:
        client.switch_database('saarctf')
        if client.write_points(data, protocol='line', batch_size=64):
            return 'OK'
        else:
            return 'Error', 500
