import datetime
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Optional, Iterable, Any

import htmlmin
from jinja2 import Environment, FileSystemLoader, select_autoescape

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from controlserver.models import Team
from saarctf_commons.config import config
from vpnboard import VpnStatus, VpnStatusHandler

try:
    import ujson as json
except ImportError:
    import json  # type: ignore


class TeamResult:
    def __init__(self) -> None:
        self.router_ping_ms: Optional[float] = None
        self.testbox_ping_ms: Optional[float] = None
        self.testbox_ok: bool = False
        self.testbox_err: Optional[str] = None
        self.vulnbox_ping_ms: Optional[float] = None  # only filled if explicitly selected


class VpnBoard(VpnStatusHandler):
    jinja2_env = Environment(
        loader=FileSystemLoader(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')),
        autoescape=select_autoescape(['html', 'xml'])
    )

    def __init__(self) -> None:
        if not config.VPNBOARD_PATH.exists():
            self.create_directories()
        if not os.path.exists(config.VPNBOARD_PATH / 'index.css'):
            self.copy_static_files()

    def create_directories(self) -> None:
        config.VPNBOARD_PATH.mkdir(exist_ok=True)

    def copy_static_files(self) -> None:
        static_dir: Path = Path(os.path.abspath(__file__)).parent.parent / 'controlserver' / 'static'
        shutil.copyfile(static_dir / 'css' / 'vpnboard.css', config.VPNBOARD_PATH / 'index.css')
        shutil.copyfile(static_dir / 'img' / 'favicon.png', config.VPNBOARD_PATH / 'favicon.png')

    def render_template(self, template: str, filename: str, minimize: bool = False, **kwargs: Any) -> None:
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
        with open(config.VPNBOARD_PATH / filename, 'wb') as f:
            f.write(content.encode('utf-8'))

    def write_json(self, filename: str, data: Any) -> None:
        (config.VPNBOARD_PATH / filename).write_text(json.dumps(data))

    def build_vpn_json(self, teams: Iterable[Team]) -> None:
        data = {
            'teams': [{
                'id': team.id,
                'name': team.name,
                'ip': config.NETWORK.team_id_to_vulnbox_ip(team.id),
                'online': team.vpn_connected or team.vpn2_connected or team.wg_boxes_connected,
                'ever_online': team.vpn_last_connect is not None,
            } for team in teams]
        }
        self.write_json('all_teams.json', data)

        data = {
            'teams': [{
                'id': team.id,
                'name': team.name,
                'ip': config.NETWORK.team_id_to_vulnbox_ip(team.id),
                'online': team.vpn_connected or team.vpn2_connected or team.wg_boxes_connected,
                'ever_online': team.vpn_last_connect is not None
            } for team in teams if team.vpn_connected or team.vpn2_connected or team.wg_boxes_connected or team.vpn_last_connect is not None]
        }
        self.write_json('available_teams.json', data)

    def build_vpn_board(self, states: list[VpnStatus], banned_teams: set[int] | None = None, check_vulnboxes: bool = False,
                        start: float = time.time()) -> None:
        if banned_teams is None:
            banned_teams = set()

        self.render_template('vpn.html', 'vpn.html', minimize=True, wireguard=any(s.wg is not None for s in states),
                             start=datetime.datetime.fromtimestamp(start, datetime.timezone.utc),
                             states=states, check_vulnboxes=check_vulnboxes, banned_teams=banned_teams)
        self.build_vpn_json(s.team for s in states)

    def update_all(self, states: list[VpnStatus], banned_teams: set[int], check_vulnboxes: bool, start: float) -> None:
        self.build_vpn_board(states, banned_teams, check_vulnboxes, start)
