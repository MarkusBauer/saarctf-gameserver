#!/usr/bin/env python3
import os
import sys
import traceback

from sqlalchemy import func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons import config

config.EXTERNAL_TIMER = True

"""
Decrements the "cloud" connection counter for a team. Called as "down" script from OpenVPN.
ARGUMENTS: Team-ID
"""


def main():
	import controlserver.app
	team_id = int(sys.argv[1])
	from controlserver.models import Team, db
	changes = Team.query.filter(Team.id == team_id).update(dict(vpn_connection_count=0), synchronize_session=False)
	db.session.commit()
	if changes > 0:
		print(f'Updated connection status (down) of team #{team_id}.')
	else:
		print(f'Team #{team_id} not found.')


if __name__ == '__main__':
	try:
		main()
	except Exception as e:
		with open('/tmp/connect-error.log', 'a') as f:
			f.write('=== DOWN ===')
			f.write(repr(sys.argv))
			traceback.print_exc(file=f)
			f.write('\n')
		raise
