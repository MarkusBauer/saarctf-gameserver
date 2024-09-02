#!/usr/bin/env python3
import os
import sys
import traceback

from sqlalchemy import func

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.config import config, load_default_config
from controlserver.models import init_database, Team, db_session

"""
Marks a team as "online" for the gameserver. Called as "up" script from OpenVPN.
ARGUMENTS: Team-ID
"""


def main():
    team_id = int(sys.argv[1])
    is_vpn_2 = sys.argv[2] == 'cloudhosted' if len(sys.argv) > 2 else False
    if is_vpn_2:
        changes = Team.query.filter(Team.id == team_id).update(dict(vpn2_connected=True, vpn_last_connect=func.now()), synchronize_session=False)
    else:
        changes = Team.query.filter(Team.id == team_id).update(dict(vpn_connected=True, vpn_last_connect=func.now()), synchronize_session=False)
    db_session().commit()
    if changes > 0:
        print(f'Updated connection status (connected) of team #{team_id}.')
    elif team_id > 0:
        session = db_session()
        if is_vpn_2:
            session.add(Team(id=team_id, name=f'unnamed team #{team_id}', vpn2_connected=True, vpn_last_connect=func.now()))
        else:
            session.add(Team(id=team_id, name=f'unnamed team #{team_id}', vpn_connected=True, vpn_last_connect=func.now()))
        session.commit()
        print(f'Updated connection status (connected) of team #{team_id}. Created new dummy team entry for that.')
    else:
        print(f'Team #{team_id} not found.')


if __name__ == '__main__':
    try:
        load_default_config()
        config.set_script()
        init_database()
        main()
    except Exception as e:
        with open('/tmp/connect-error.log', 'a') as f:
            f.write('=== CONNECT ===')
            f.write(repr(sys.argv))
            traceback.print_exc(file=f)
            f.write('\n')
        raise
