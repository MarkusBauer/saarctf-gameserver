"""
Start worker:
celery -A vpnboard.vpncelery worker -E --concurrency=8
"""
from typing import Optional

from celery import Celery
from saarctf_commons.config import celery_url, celery_redis_url
from vpnboard.vpnchecks import test_ping, test_nping, test_web

celeryapp = Celery('tasks', broker=celery_url(), backend=celery_redis_url())
celeryapp.conf.task_default_queue = 'vpnboard'
celeryapp.conf.task_track_started = True
celeryapp.conf.result_expires = None
celeryapp.conf.worker_pool_restarts = True


@celeryapp.task
def test_ping_celery(ip: str) -> Optional[float]:
	return test_ping(ip)


@celeryapp.task
def test_nping_celery(ip: str) -> Optional[float]:
	return test_nping(ip)


@celeryapp.task
def test_web_celery(ip: str) -> Optional[str]:
	return test_web(ip)

