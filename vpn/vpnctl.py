#!/usr/bin/env python3
import argparse
import logging
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Iterable

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.config import load_default_config, config

from controlserver.models import Team, init_database, db_session


@dataclass
class VpnStatus:
    team_id: int
    # things from DB
    self_connected: bool
    cloud_connected: bool
    cloud_player_conns: int
    # things from systemctl
    self_active: bool
    cloud_active: bool
    cloud_players_active: bool


DRY = False


class SystemCtlUtils:

    @classmethod
    def service_vpn_selfhosted(cls, team_id: int) -> str:
        return f'vpn@team{team_id}'

    @classmethod
    def service_vpn_cloudhosted(cls, team_id: int) -> str:
        return f'vpn@team{team_id}-vulnbox'

    @classmethod
    def service_vpn_cloud_players(cls, team_id: int) -> str:
        return f'vpn2@team{team_id}-cloud'

    @classmethod
    def _execute(cls, cmd: list[str], check: bool = True) -> str:
        logging.debug(f'execute systemctl {cmd}')
        result = subprocess.run(['systemctl'] + cmd,
                                check=check,
                                stdout=subprocess.PIPE)
        return result.stdout.decode('utf-8')

    @classmethod
    def is_active(cls, service_names: list[str]) -> dict[str, bool]:
        results: list[bool] = []
        for offset in range(0, len(service_names), 100):
            # check=False because `systemctl is-active` will return code 3 if ALL
            # selected services are down
            text: str = cls._execute(
                ['is-active'] + service_names[offset:offset + 100],
                check=False)
            for i, line in enumerate(text.strip().split('\n')):
                if line == 'active':
                    results.append(True)
                elif line == 'activating':
                    results.append(True)
                    print(CliColors.WARNING +
                          f'[WARN] Service {service_names[offset + i]} is activating' + CliColors.ENDC)
                elif line == 'inactive' or line == 'deactivating':
                    results.append(False)
                else:
                    raise Exception(f'Unexpected line in systemctl is-active output: {repr(line)}')
        if len(results) != len(service_names):
            raise Exception('Unexpected length difference in systemctl is-active outputs: '
                            f'{len(results)}, but expected {len(service_names)}')
        return {name: result for name, result in zip(service_names, results)}

    @classmethod
    def start(cls, service_names: list[str]) -> None:
        cmd = ['start'] + service_names
        if DRY:
            print(f'WOULD EXECUTE: systemctl {" ".join(cmd)}')
        elif len(service_names) > 0:
            cls._execute(cmd)

    @classmethod
    def stop(cls, service_names: list[str]) -> None:
        cmd = ['start'] + service_names
        if DRY:
            print(f'WOULD EXECUTE: systemctl {" ".join(cmd)}')
        elif len(service_names) > 0:
            cls._execute(['stop'] + service_names)


class VpnStatusFactory:
    @classmethod
    def from_team_ids(cls, ids: list[int]) -> list[VpnStatus]:
        teams = list(Team.query.filter(Team.id.in_(ids)).order_by(Team.id).all())
        return cls.from_teams(teams)

    @classmethod
    def for_all_teams(cls) -> list[VpnStatus]:
        teams = list(Team.query.order_by(Team.id).all())
        return cls.from_teams(teams)

    @classmethod
    def from_teams(cls, teams: list[Team]) -> list[VpnStatus]:
        services: list[str] = []
        for team in teams:
            services.append(SystemCtlUtils.service_vpn_selfhosted(team.id))
            services.append(SystemCtlUtils.service_vpn_cloudhosted(team.id))
            services.append(SystemCtlUtils.service_vpn_cloud_players(team.id))
        service_status = SystemCtlUtils.is_active(services)
        return [VpnStatus(
            team_id=team.id,
            self_connected=team.vpn_connected,
            cloud_connected=team.vpn2_connected,
            cloud_player_conns=team.vpn_connection_count,
            self_active=service_status[SystemCtlUtils.service_vpn_selfhosted(team.id)],
            cloud_active=service_status[SystemCtlUtils.service_vpn_cloudhosted(team.id)],
            cloud_players_active=service_status[SystemCtlUtils.service_vpn_cloud_players(team.id)],
        ) for team in teams]

    @classmethod
    def for_future_teams(cls, team_ids: Iterable[int]) -> list[VpnStatus]:
        """
        We can start VPNs for teams that do not yet exist.
        They are not affected by any fix/reset until they appear in DB.
        """
        services: list[str] = []
        for team_id in team_ids:
            services.append(SystemCtlUtils.service_vpn_selfhosted(team_id))
            services.append(SystemCtlUtils.service_vpn_cloudhosted(team_id))
            services.append(SystemCtlUtils.service_vpn_cloud_players(team_id))
        service_status = SystemCtlUtils.is_active(services)
        return [VpnStatus(
            team_id=team_id,
            self_connected=False,
            cloud_connected=False,
            cloud_player_conns=0,
            self_active=service_status[SystemCtlUtils.service_vpn_selfhosted(team_id)],
            cloud_active=service_status[SystemCtlUtils.service_vpn_cloudhosted(team_id)],
            cloud_players_active=service_status[SystemCtlUtils.service_vpn_cloud_players(team_id)],
        ) for team_id in team_ids]


@dataclass
class VpnStatusCheck:
    team_id: int
    ok: bool
    messages: list[str]
    mode: str | None = None  # "self", "cloud", None
    fix_start_service: list[str] = field(default_factory=list)
    fix_stop_service: list[str] = field(default_factory=list)
    fix_needs_reset: bool = False

    def add_error(self, message: str) -> None:
        self.ok = False
        self.messages.append(message)

    @classmethod
    def from_status(cls, status: VpnStatus) -> 'VpnStatusCheck':
        result = VpnStatusCheck(status.team_id, True, [])
        if status.cloud_connected:
            result.mode = 'cloud'
            if status.self_connected:
                result.add_error('Both self-hosted and cloud-hosted VPN are connected.')
                result.fix_needs_reset = True
            if status.self_active:
                result.add_error('Self-hosted VPN is active although cloud-hosted VPN is connected.')
                result.fix_stop_service.append(SystemCtlUtils.service_vpn_selfhosted(status.team_id))
            if not status.cloud_active:
                result.add_error('Cloud-hosted VPN is connected but inactive (wtf?).')
                result.fix_start_service.append(SystemCtlUtils.service_vpn_cloud_players(status.team_id))
            if not status.cloud_players_active:
                result.add_error('Cloud players VPN is inactive.')
                result.fix_start_service.append(SystemCtlUtils.service_vpn_cloud_players(status.team_id))
        elif status.self_connected:
            result.mode = 'self'
            if status.cloud_player_conns > 0:
                result.add_error('Both self-hosted and cloud player VPNs have connections.')
                if status.cloud_players_active:
                    result.fix_stop_service.append(SystemCtlUtils.service_vpn_cloud_players(status.team_id))
                else:
                    result.fix_needs_reset = True
            if not status.self_active:
                result.add_error('Self-hosted VPN is connected but inactive (wtf?).')
                result.fix_needs_reset = True
            if not status.cloud_active:
                result.add_error('Cloud-hosted VPN is inactive.')
                result.fix_start_service.append(SystemCtlUtils.service_vpn_cloudhosted(status.team_id))
            if status.cloud_players_active:
                result.add_error('Cloud players VPN is active while self-hosted VPN is connected.')
                result.fix_stop_service.append(SystemCtlUtils.service_vpn_cloud_players(status.team_id))
        else:
            if not status.self_active:
                result.add_error('Self-hosted VPN is inactive.')
                result.fix_start_service.append(SystemCtlUtils.service_vpn_selfhosted(status.team_id))
            if not status.cloud_active:
                result.add_error('Cloud-hosted VPN is inactive.')
                result.fix_start_service.append(SystemCtlUtils.service_vpn_cloudhosted(status.team_id))
            if not status.cloud_players_active:
                result.add_error('Cloud players VPN is inactive.')
                result.fix_start_service.append(SystemCtlUtils.service_vpn_cloud_players(status.team_id))
        return result


class VpnStatusFixer:
    @classmethod
    def reset(cls, check_list: list[VpnStatusCheck]) -> None:
        services: list[str] = []
        for check in check_list:
            services.append(SystemCtlUtils.service_vpn_selfhosted(check.team_id))
            services.append(SystemCtlUtils.service_vpn_cloudhosted(check.team_id))
            services.append(SystemCtlUtils.service_vpn_cloud_players(check.team_id))
        print(f'[reset] Stopping {len(services)} services ...')
        SystemCtlUtils.stop(services)

        ids = [check.team_id for check in check_list]
        changes = Team.query.filter(Team.id.in_(ids)) \
            .update({'vpn_connected': False, 'vpn2_connected': False, 'vpn_connection_count': 0})

        if not DRY:
            db_session().commit()
            print(f'[reset] DB reset ({changes} teams)')
        else:
            print(f'WOULD UPDATE {changes} teams in the db')

        print(f'[reset] Starting {len(services)} services ...')
        SystemCtlUtils.start(services)

    @classmethod
    def fix(cls, check_list: list[VpnStatusCheck]) -> None:
        reset_checks: list[VpnStatusCheck] = []
        start_services: list[str] = []
        stop_services: list[str] = []
        for check in check_list:
            if check.fix_needs_reset:
                reset_checks.append(check)
            else:
                start_services += check.fix_start_service
                stop_services += check.fix_stop_service
        if len(reset_checks) > 0:
            print(f'Resetting {len(reset_checks)} VPNs ...')
            cls.reset(reset_checks)
        if len(start_services) > 0:
            print(f'Starting {len(start_services)} services ...')
            SystemCtlUtils.start(start_services)
        if len(stop_services) > 0:
            print(f'Stopping {len(stop_services)} services ...')
            SystemCtlUtils.stop(stop_services)


class CliColors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'


def command_status(args: argparse.Namespace) -> None:
    team_status = VpnStatusFactory.from_team_ids(args.teamid) if args.teamid else VpnStatusFactory.for_all_teams()
    errors = 0

    print(CliColors.HEADER + '-' * 55 + CliColors.ENDC)
    print(f'{CliColors.HEADER}Team      | Mode  | Self VPN  | Cloud VPN | Player VPN{CliColors.ENDC}')
    print(CliColors.HEADER + '-' * 55 + CliColors.ENDC)
    for status in team_status:
        check = VpnStatusCheck.from_status(status)
        state_self = f'{CliColors.OKGREEN}connected{CliColors.ENDC}' if status.self_connected \
            else ('on' if status.self_active else 'off')
        state_cloud = f'{CliColors.OKGREEN}connected{CliColors.ENDC}' if status.cloud_connected \
            else ('on' if status.cloud_active else 'off')
        state_players = f'{CliColors.OKGREEN}{status.cloud_player_conns:>4} conns{CliColors.ENDC}' \
            if status.cloud_player_conns > 0 else ('on' if status.cloud_players_active else 'off')
        line = (f'Team #{status.team_id:3} | {check.mode or "-":5} | '
                f'{state_self:>9s} | {state_cloud:>9s} | {state_players:>10s}')
        if check.ok:
            print(line)
        else:
            errors += 1
            print(CliColors.FAIL + line + CliColors.ENDC)
            for msg in check.messages:
                print(f'  - {msg}')
    print('')
    if errors > 0:
        print(f'=> {len(team_status)} VPNs, {errors} in invalid status')
        sys.exit(1)
    else:
        print(f'=> {len(team_status)} VPNs, {CliColors.OKGREEN}all good{CliColors.ENDC}')


def command_fix(args: argparse.Namespace) -> None:
    if args.all:
        team_status = VpnStatusFactory.for_all_teams()
    elif args.teamid:
        team_status = VpnStatusFactory.from_team_ids(args.teamid)
    else:
        print('Please specify team ids or use --all.')
        return

    VpnStatusFixer.fix([VpnStatusCheck.from_status(status) for status in team_status])
    print('Fix finished.')


def command_reset(args: argparse.Namespace) -> None:
    if args.all:
        team_status = VpnStatusFactory.for_all_teams()
    elif args.teamid:
        team_status = VpnStatusFactory.from_team_ids(args.teamid)
    else:
        print('Please specify team ids or use --all.')
        return
    VpnStatusFixer.reset([VpnStatusCheck.from_status(status) for status in team_status])
    print('Reset finished.')


def command_set(args: argparse.Namespace) -> None:
    services_self = [SystemCtlUtils.service_vpn_selfhosted(i) for i in args.teamid]
    services_cloud = [SystemCtlUtils.service_vpn_cloudhosted(i) for i in args.teamid]
    services_players = [SystemCtlUtils.service_vpn_cloud_players(i) for i in args.teamid]
    if args.mode == 'self':
        SystemCtlUtils.stop(services_players + services_cloud)
        SystemCtlUtils.start(services_self)
    elif args.mode == 'cloud':
        SystemCtlUtils.stop(services_self)
        SystemCtlUtils.start(services_players + services_cloud)
    elif args.mode == 'off':
        SystemCtlUtils.stop(services_self + services_cloud + services_players)
    else:
        raise Exception('Invalid mode')


def command_startup(args: argparse.Namespace) -> None:
    # get team IDs from existing configurations
    team_ids: list[int] = []
    for fname in os.listdir(config.VPN_BASE_DIR / 'config-server'):
        m = re.match(r'^team(\d+).conf$', fname)
        if m and m.group(1) != "0":
            team_ids.append(int(m.group(1)))
    # get status from all configured teams
    status_list = VpnStatusFactory.for_all_teams()
    status_list += VpnStatusFactory.for_future_teams(set(team_ids) - set(s.team_id for s in status_list))
    # collect services to start
    services: list[str] = []
    for status in status_list:
        check = VpnStatusCheck.from_status(status)
        services += check.fix_start_service
    if len(services) > 0:
        print(f'Starting {len(services)} services ...')
        print(' '.join(services))
        SystemCtlUtils.start(services)
        print('Done.')
    else:
        print('Nothing to start.')


def main() -> None:
    parser = argparse.ArgumentParser(description='VPN Systemd Service Status Control')
    parser.add_argument('--dry', action='store_true', help='Don\'t actually start/stop services or modify the DB.')
    subparsers = parser.add_subparsers(dest='command', help='subcommands')

    parser_status = subparsers.add_parser('status', help='get VPN status')
    parser_status.add_argument('teamid', nargs='*', type=int, help='Team IDs (optional)')

    parser_fix = subparsers.add_parser('fix', help='fix issues with the current VPN status')
    parser_fix.add_argument('teamid', nargs='*', type=int, help='Team IDs')
    parser_fix.add_argument('--all', action="store_true", help='Fix all teams.')

    parser_reset = subparsers.add_parser('reset', help='reset and restart VPN servers')
    parser_reset.add_argument('teamid', nargs='*', type=int, help='Team IDs')
    parser_reset.add_argument('--all', action="store_true", help='Reset all teams.')

    parser_set = subparsers.add_parser('set', help='manually choose cloud- or selfhosted (or off)')
    parser_set.add_argument('mode', choices=['self', 'cloud', 'off'])
    parser_set.add_argument('teamid', nargs='+', type=int, help='Team IDs')

    subparsers.add_parser('startup', help='start all configured VPN servers')

    args = parser.parse_args()

    global DRY
    DRY = args.dry

    match args.command:
        case 'status':
            command_status(args)
        case 'fix':
            command_fix(args)
        case 'reset':
            command_reset(args)
        case 'set':
            command_set(args)
        case 'startup':
            command_startup(args)
        case _:
            if args.command:
                print(CliColors.FAIL + 'unknown command' + CliColors.ENDC)
            parser.print_help()
            sys.exit(1)


if __name__ == '__main__':
    load_default_config()
    config.set_script()
    init_database()
    main()
