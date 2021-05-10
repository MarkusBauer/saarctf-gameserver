import os
import sys
import hashlib
from typing import Optional, Dict

import requests

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config
from controlserver.models import Team, TeamLogo

config.EXTERNAL_TIMER = True

"""
NO ARGUMENTS
Sync teams with a remote HTTP source, configured TODO
"""


def import_logo(team: Team, logo: Optional[str]):
	os.makedirs(os.path.join(config.SCOREBOARD_PATH, 'logos'), exist_ok=True)
	root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
	logo_in = logo or os.path.join(root, 'controlserver', 'static', 'img', 'profile_dummy.png')
	imghash = TeamLogo.store_logo_file(logo_in)
	team.logo = imghash


def import_logo_from_bytes(team: Team, data: bytes):
	os.makedirs(os.path.join(config.SCOREBOARD_PATH, 'logos'), exist_ok=True)
	imghash = TeamLogo.store_logo_bytes(data)
	team.logo = imghash


def import_logo_from_url(team: Team, fname: str):
	if not fname:
		import_logo(team, None)
		return
	# check if image is present
	if fname.split('.')[0] == team.logo:
		return
	# download image
	url: str = config.CONFIG['website_team_url'].split('?')[0]
	url = url.rstrip('/').rsplit('/', 2)[0]
	url += '/static/img/logo/' + fname
	resp = requests.get(url)
	assert resp.status_code == 200
	import_logo_from_bytes(team, resp.content)


def add_team(remote_team: Dict):
	import controlserver
	team = Team(id=remote_team['id'], name=remote_team['name'], affiliation=remote_team['affiliation'], website=remote_team['website'])
	controlserver.models.db.session.add(team)
	controlserver.models.db.session.commit()
	import_logo_from_url(team, remote_team['logo'])
	controlserver.models.db.session.add(team)
	print(f'Added  team "{team.name}".')


def update_team(team: Team, remote_team: Dict):
	import controlserver
	team.name = remote_team['name']
	team.affiliation = remote_team['affiliation']
	team.website = remote_team['website']
	import_logo_from_url(team, remote_team['logo'])
	controlserver.models.db.session.add(team)
	print(f'Update team "{team.name}".')


def main():
	import controlserver.app
	should_delete = '--delete' in sys.argv
	teams = {team.id: team for team in Team.query.all()}
	remote_teams = requests.get(config.CONFIG['website_team_url']).json()['teams']

	if config.NOP_TEAM_ID and config.NOP_TEAM_ID not in teams:
		team = Team(id=config.NOP_TEAM_ID, name='NOP')
		controlserver.models.db.session.add(team)
		teams[team.id] = team
	for remote_team in remote_teams:
		if remote_team['id'] in teams:
			update_team(teams[remote_team['id']], remote_team)
			del teams[remote_team['id']]
		else:
			add_team(remote_team)
	# handle teams in this DB that are not present in the remote
	for id, team in teams.items():
		if id == config.NOP_TEAM_ID:
			import_logo(team, None)
		elif should_delete:
			team.delete()
			print(f'Deleted team "{team.name}".')
		else:
			print(f'Team not found on website: #{team.id} "{team.name}". Use --delete to drop.')
			import_logo(team, None)
	controlserver.models.db.session.commit()


if __name__ == '__main__':
	main()
