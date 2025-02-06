#!/usr/bin/env python3
import datetime
import os
import subprocess
import sys

from controlserver.models import init_database, Team, db_session

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.config import config, load_default_config

"""
ARGUMENTS: none
Reset the connection status of all teams that connected to this machine before the last reboot.
"""


def main() -> None:
    uptime: bytes = subprocess.check_output(['uptime', '-s'])
    last_boot = datetime.datetime.strptime(uptime.decode().strip(), '%Y-%m-%d %H:%M:%S')
    print('Last boot: ' + last_boot.strftime('%d.%m.%Y %H:%M:%S'))

    team_count = Team.query.filter((Team.vpn_connected == True) |
                                   (Team.vpn2_connected == True) |
                                   (Team.wg_boxes_connected == True) |
                                   (Team.wg_vulnbox_connected == True),
                                   Team.vpn_last_connect < last_boot) \
        .update({
        'vpn_connected': False,
        'vpn2_connected': False,
        'wg_boxes_connected': False,
        'wg_vulnbox_connected': False,
        'vpn_last_disconnect': last_boot
    })
    print(f'{team_count} teams were disconnected due to last reboot (and have not reconnected yet).')
    db_session().commit()

    if '--all' in sys.argv:
        team_count = Team.query.filter(Team.vpn_connection_count > 0) \
            .update({'vpn_connection_count': 0})
        print(f'{team_count} cloud connections were disconnected.')
    else:
        print('Use --all to reset the cloud-style connection counter')
    db_session().commit()

    print('[DONE]')


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    init_database()
    main()
