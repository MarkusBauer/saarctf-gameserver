#!/usr/bin/env python3
import os
import sys
from typing import List

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.config import config, load_default_config

from vpn.vpnlib import *
from controlserver.models import Team, init_database

"""
ARGUMENTS: none
"""

BASEPORT = 10000


def build_team_config(team: Team, client_root: Path, secret_root: Path):
    secret_file = secret_root / f'team{team.id}.key'

    # Create config
    content = f'''
    topology p2p
    remote {config.CONFIG['network']['vpn_host']} {BASEPORT + team.id}
    proto udp
    dev game
    dev-type tun
    
    ifconfig {' '.join(config.NETWORK.team_id_to_vpn_peers(team.id)[::-1])}
    route {network_to_mask(config.CONFIG['network']['game'])}
    
    user nobody
    group nogroup
    nobind
    persist-key
    persist-tun
    
    # Do not change these two lines!
    shaper 5000000
    keepalive 10 60
    connect-retry 5 30
    
    cipher AES-128-CBC
    auth SHA256
    
    verb 3
    
    <secret>
    {read(secret_file)}
    </secret>
    '''.replace('\n    ', '\n')

    write(client_root / f'client-team{team.id}.conf', content)
    # copy over key files
    print(f'[OK] Wrote team #{team.id} client configuration.')


def build_server_config(team: Team, server_root: Path, secret_root: Path):
    secret_file = secret_root / f'team{team.id}.key'

    # Create secret
    if not os.path.exists(secret_file):
        subprocess.check_call(['openvpn', '--genkey', '--secret', secret_file])
        print(f'[OK] Created team #{team.id} secret key.')
    else:
        print(f'...  Team #{team.id} secret key present.')

    # write config
    root = os.path.dirname(os.path.abspath(__file__))
    # root = '/saarctf/vpn'  # for debugging
    serverconfig = f'''
    # OpenVPN Configuration for Team #{team.id} - "{team.name}"
    topology p2p
    ifconfig {' '.join(config.NETWORK.team_id_to_vpn_peers(team.id))}
    proto udp
    port {BASEPORT + team.id}
    dev tun{team.id}
    dev-type tun
    
    # route game network there
    route {network_to_mask(config.NETWORK.team_id_to_network_range(team.id))}
    #push "route {network_to_mask(config.CONFIG['network']['game'])}"
    #TODO avoid loops
    
    cipher AES-128-CBC
    # ncp-ciphers AES-128-GCM
    auth SHA256
    keepalive 15 60
    connect-retry 5 30
    
    # "secure" version
    #user nobody
    #group nogroup
    #persist-tun
    
    # version with up/down callbacks
    route-delay
    up-restart
    up-delay
    
    max-clients 1
    persist-key
    status /var/log/vpn/openvpn-status-team{team.id}.log

    script-security 3
    up "{root}/on-connect.sh {team.id} teamhosted"
    down "{root}/on-disconnect.sh {team.id} teamhosted"
    
    verb 3
    explicit-exit-notify 1
    
    <secret>
    {read(secret_file)}
    </secret>
    '''.replace('\n    ', '\n')
    if team.id == 0:
        serverconfig = serverconfig.replace('\nup ', '\n# up ') \
            .replace('\ndown ', '\n# down ').replace('\ndev ', '\ndev orga0  # not ')
    write(server_root / f'team{team.id}.conf', serverconfig)

    print(f'[OK] Created team #{team.id} server config')


def build_systemd_file(teams: List[Team]):
    prefix = '''
    [Unit]
    After=network.target
    After=vpn@team0.service
    Requires=vpn@team0.service
    '''.replace('\n\t', '\n')

    lines = [f'After=vpn@team{team.id}.service\nRequires=vpn@team{team.id}.service' for team in teams]

    suffix = '''
    
    [Service]
    Type=oneshot
    RemainAfterExit=true
    ExecStart=/bin/true
    
    [Install]
    WantedBy=multi-user.target
    '''.replace('\n    ', '\n')
    text = prefix + '\n'.join(lines) + suffix
    with open(config.VPN_BASE_DIR / 'vpn.service', 'w') as f:
        f.write(text)
    print('[OK] Systemd service generated.')


def main():
    server_root = config.VPN_BASE_DIR / 'config-server'  # output: server config
    client_root = config.VPN_BASE_DIR / 'config-client'  # output: team config
    secret_root = config.VPN_BASE_DIR / 'secrets'
    server_root.mkdir(exist_ok=True)
    client_root.mkdir(exist_ok=True)
    secret_root.mkdir(exist_ok=True)
    print(f'SETUP: rm -r /etc/openvpn/server && ln -s "{server_root}" /etc/openvpn/server\n\n')

    teams = list(Team.query.order_by(Team.id).all())
    if len(sys.argv) > 1:
        prebuild_count = int(sys.argv[1])
        max_id = max(team.id for team in teams)
        for i in range(max_id + 1, max_id + prebuild_count + 1):
            teams.append(Team(id=i, name=f'unnamed team #{i}'))
    for team in teams:
        assert '\n' not in team.name
        build_server_config(team, server_root, secret_root)
        build_team_config(team, client_root, secret_root)
    if teams:
        build_systemd_file(teams)
    else:
        print('No teams.')
    # build a config for the orgas
    orga = Team(id=0, name='orga')
    build_server_config(orga, server_root, secret_root)
    build_team_config(orga, client_root, secret_root)

    print('[DONE]')


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    init_database()
    main()
