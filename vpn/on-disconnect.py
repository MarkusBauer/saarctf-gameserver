#!/usr/bin/env python3
import os
import sys
import traceback

from sqlalchemy import func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.config import config, load_default_config
from controlserver.models import init_database, Team, db_session

"""
Marks a team as "offline" for the gameserver. Called as "down" script from OpenVPN.
ARGUMENTS: Team-ID
"""


def main() -> None:
    team_id_str = sys.argv[1]
    if team_id_str.startswith('team'):
        team_id_str = team_id_str[4:]
        if '-' in team_id_str:
            team_id_str = team_id_str.split('-')[0]
    team_id = int(team_id_str)
    is_vpn_2 = sys.argv[2] == 'cloudhosted' if len(sys.argv) > 2 else False
    if is_vpn_2:
        changes = Team.query.filter(Team.id == team_id).filter(Team.vpn2_connected == True) \
            .update(dict(vpn2_connected=False, vpn_last_disconnect=func.now()), synchronize_session=False)
    else:
        changes = Team.query.filter(Team.id == team_id).filter(Team.vpn_connected == True) \
            .update(dict(vpn_connected=False, vpn_last_disconnect=func.now()), synchronize_session=False)
    db_session().commit()
    if changes > 0:
        print(f'Updated connection status (disconnected) of team #{team_id}.')
    else:
        print(f'Team #{team_id} already disconnected or not found.')


if __name__ == '__main__':
    try:
        load_default_config()
        config.set_script()
        init_database()
        main()
    except Exception as e:
        with open('/tmp/connect-error.log', 'a') as f:
            f.write('=== DISCONNECT ===')
            f.write(repr(sys.argv))
            traceback.print_exc(file=f)
            f.write('\n')
        raise
