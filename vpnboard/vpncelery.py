"""
Start worker:
celery -A vpnboard.vpncelery worker -E --concurrency=8
"""

import re
import subprocess
from typing import Optional

import requests
from celery import Celery
from saarctf_commons.config import celery_url, celery_redis_url

celeryapp = Celery('tasks', broker=celery_url(), backend=celery_redis_url())
celeryapp.conf.task_default_queue = 'vpnboard'
celeryapp.conf.task_track_started = True
celeryapp.conf.result_expires = None
celeryapp.conf.worker_pool_restarts = True


@celeryapp.task
def test_ping(ip: str) -> Optional[float]:
	try:
		result = subprocess.run(['ping', '-c', '3', ip], stdout=subprocess.PIPE, timeout=5, check=False)
		if result.returncode != 0:
			return None
		times = re.findall(r'time=([\d.]+) ms', result.stdout.decode())
		if len(times) != 3:
			return None
		return sum(float(x) for x in times) / len(times)
	except subprocess.TimeoutExpired:
		return None


@celeryapp.task()
def test_web(ip: str) -> Optional[str]:
	try:
		response = requests.get(f'http://{ip}/saarctf', timeout=3)
		if response.status_code != 200:
			return f'status {response.status_code}'
		if response.text.strip() != 'saarctf-testbox':
			return f'unexpected text'
		return 'OK'
	except requests.Timeout:
		return 'unreachable'
	except requests.ConnectionError:
		return 'unreachable'
	except requests.RequestException as e:
		return 'error: ' + str(e)
