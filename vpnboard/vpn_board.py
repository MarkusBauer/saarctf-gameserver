import datetime
import os
import shutil
import sys
import time
import traceback
from typing import Dict, Optional, List, Iterable

import htmlmin
from celery import group
from jinja2 import Environment, FileSystemLoader, select_autoescape

from saarctf_commons.config import team_id_to_gateway_ip, team_id_to_testbox_ip, SCOREBOARD_PATH, team_id_to_vulnbox_ip
from vpnboard.vpncelery import test_ping, test_web
from controlserver.models import Team

try:
	import ujson as json
except ImportError:
	import json  # type: ignore


def eprint(*args, **kwargs):
	print(*args, file=sys.stderr, **kwargs)


class TeamResult:
	def __init__(self):
		self.router_ping_ms: Optional[float] = None
		self.testbox_ping_ms: Optional[float] = None
		self.testbox_ok: bool = False
		self.testbox_err: Optional[str] = None
		self.vulnbox_ping_ms: Optional[float] = None  # only filled if explicitly selected


class VpnBoard:
	jinja2_env = Environment(
		loader=FileSystemLoader(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')),
		autoescape=select_autoescape(['html', 'xml'])
	)

	def __init__(self):
		if not os.path.exists(SCOREBOARD_PATH):
			self.create_directories()
		if not os.path.exists(os.path.join(SCOREBOARD_PATH, 'index.css')):
			self.copy_static_files()

	def create_directories(self):
		os.makedirs(SCOREBOARD_PATH, exist_ok=True)

	def copy_static_files(self):
		static_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'controlserver', 'static')
		shutil.copyfile(os.path.join(static_dir, 'css', 'vpnboard.css'), os.path.join(SCOREBOARD_PATH, 'index.css'))
		shutil.copyfile(os.path.join(static_dir, 'img', 'favicon.png'), os.path.join(SCOREBOARD_PATH, 'favicon.png'))

	def render_template(self, template: str, filename: str, minimize=False, **kwargs) -> None:
		"""
		Render a template to file
		:param template:
		:param filename:
		:param kwargs:
		:return:
		"""
		template_jinja = self.jinja2_env.get_template(template)
		content = template_jinja.render(**kwargs)
		if minimize:
			content = htmlmin.minify(content, remove_empty_space=True)
		with open(os.path.join(SCOREBOARD_PATH, filename), 'wb') as f:
			f.write(content.encode('utf-8'))

	def write_json(self, filename: str, data):
		with open(os.path.join(SCOREBOARD_PATH, filename), 'w') as f:
			json.dump(data, f)

	def build_vpn_json(self, teams: Iterable[Team]):
		data = {
			'teams': [{
				'id': team.id,
				'name': team.name,
				'ip': team_id_to_vulnbox_ip(team.id),
				'online': team.vpn_connected,
				'ever_online': team.vpn_last_connect is not None,
			} for team in teams]
		}
		self.write_json('all_teams.json', data)
		data = {
			'teams': [{
				'id': team.id,
				'name': team.name,
				'ip': team_id_to_vulnbox_ip(team.id),
				'online': team.vpn_connected,
				'ever_online': team.vpn_last_connect is not None
			} for team in teams if team.vpn_connected or team.vpn_last_connect is not None]
		}
		self.write_json('available_teams.json', data)

	def collect_team_results(self, teams: List[Team], check_vulnboxes: bool = False) -> Dict[int, TeamResult]:
		"""
		Dispatch celery tasks that check the connectivity of all given teams and return status info.
		:param teams:
		:param check_vulnboxes: Only if True the vulnbox IPs will be pinged
		:return:
		"""
		if not teams:
			return {}
		results: Dict[int, TeamResult] = {team.id: TeamResult() for team in teams}
		# collect ping / http results for connected teams
		router_ping_group = group(test_ping.signature([team_id_to_gateway_ip(team.id)], time_limit=10) for team in teams)
		testbox_ping_group = group(test_ping.signature([team_id_to_testbox_ip(team.id)], time_limit=10) for team in teams)
		testbox_web_group = group(test_web.signature([team_id_to_testbox_ip(team.id)], time_limit=10) for team in teams)
		if check_vulnboxes:
			vulnbox_ping_group = group(test_ping.signature([team_id_to_vulnbox_ip(team.id)], time_limit=10) for team in teams)
		eprint(f'{datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}: Dispatching {3 * len(teams)} tasks ...')
		router_ping_result = router_ping_group.apply_async()
		testbox_ping_result = testbox_ping_group.apply_async()
		testbox_web_result = testbox_web_group.apply_async()
		if check_vulnboxes:
			vulnbox_ping_result = vulnbox_ping_group.apply_async()
		eprint(f'{datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}: Collecting router ping results ...')
		for team, result in zip(teams, router_ping_result.join(propagate=False, timeout=300)):
			results[team.id].router_ping_ms = result if isinstance(result, float) else None
		eprint(f'{datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}: Collecting testbox ping results ...')
		for team, result in zip(teams, testbox_ping_result.join(propagate=False, timeout=300)):
			results[team.id].testbox_ping_ms = result if isinstance(result, float) else None
		eprint(f'{datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}: Collecting testbox web results ...')
		for team, result in zip(teams, testbox_web_result.join(propagate=False, timeout=300)):
			if isinstance(result, str):
				results[team.id].testbox_ok = result == 'OK'
				results[team.id].testbox_err = result
			else:
				results[team.id].testbox_ok = False
				results[team.id].testbox_err = str(result)
		if check_vulnboxes:
			eprint(f'{datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}: Collecting vulnbox ping results ...')
			for team, result in zip(teams, vulnbox_ping_result.join(propagate=False, timeout=300)):
				results[team.id].vulnbox_ping_ms = result if isinstance(result, float) else None
		eprint(f'{datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}: Collected results.')
		return results

	def print_results_for_influxdb(self, ts: datetime.datetime, teams: List[Team], results: Dict[int, TeamResult], check_vulnboxes: bool):
		influx_ts = int(ts.timestamp() * 1000000000)
		for team in teams:
			if team.id in results:
				result = results[team.id]
				fields = {
					'router_up': '0i' if result.router_ping_ms is None else '1i',
					'testbox_up': '0i' if result.testbox_ping_ms is None else '1i',
					'testbox_ok': '0i' if result.testbox_ok else '1i',
				}
				if result.router_ping_ms:
					fields['router_ping_ms'] = str(result.router_ping_ms)
				if result.testbox_ping_ms:
					fields['testbox_ping_ms'] = str(result.testbox_ping_ms)
				if check_vulnboxes:
					fields['vulnbox_up'] = '0i' if result.vulnbox_ping_ms is None else '1i'
					if result.vulnbox_ping_ms:
						fields['vulnbox_ping_ms'] = str(result.vulnbox_ping_ms)
				fields_str = ','.join(f'k=v' for k, v in fields.items())
				print(f'vpn_connection,team_id={team.id}i connected=1i {influx_ts}')
				print(f'vpn_board,team_id={team.id}i {fields_str} {influx_ts}')
			else:
				print(f'vpn_connection,team_id={team.id}i connected=0i {influx_ts}')

	def build_vpn_board(self, check_vulnboxes: bool = False):
		start = datetime.datetime.now(datetime.timezone.utc)
		teams = Team.query.order_by(Team.id).all()
		connected_teams = [team for team in teams if team.vpn_connected]
		results = self.collect_team_results(connected_teams, check_vulnboxes)
		self.render_template('vpn.html', 'vpn.html', minimize=True, start=start, teams=teams, results=results, check_vulnboxes=check_vulnboxes)
		self.build_vpn_json(teams)
		self.print_results_for_influxdb(start, teams, results, check_vulnboxes)
		seconds = (datetime.datetime.now(datetime.timezone.utc) - start).total_seconds()
		eprint(f'{start.strftime("%d.%m.%Y %H:%M:%S")}: Created VPN board, took {seconds:.3f} seconds.')


def main():
	from controlserver import app
	board = VpnBoard()
	check_vulnboxes = '--check-vulnbox' in sys.argv
	if '--daemon' in sys.argv:
		eprint(f'{datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}: VPN Board daemon started.')
		while True:
			start = time.time()
			try:
				board.build_vpn_board(check_vulnboxes)
			except:
				traceback.print_exc()
				eprint(f'{datetime.datetime.now().strftime("%d.%m.%Y %H:%M:%S")}: Could not create VPN board.')
			duration = time.time() - start
			sleeptime = min(60, max(5, round((60 if duration >= 25 else 30) - duration)))
			eprint(f'sleeping {sleeptime} ...')
			time.sleep(sleeptime)
	else:
		board.build_vpn_board(check_vulnboxes)


if __name__ == '__main__':
	from saarctf_commons import config

	config.set_redis_clientname('scoreboard', True)
	config.EXTERNAL_TIMER = True
	main()
