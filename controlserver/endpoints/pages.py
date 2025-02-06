"""
Pages for the management interface
"""

import copy
import datetime
import os
import threading
import time
from collections import defaultdict
from math import ceil, floor
from typing import List, Optional, Tuple, Any, cast

from flask import Blueprint, render_template, jsonify, request, Response
from flask.typing import ResponseReturnValue
from sqlalchemy import distinct, Integer, text, func
from sqlalchemy.orm.exc import NoResultFound

from checker_runner.runner import celery_worker
from controlserver.db_filesystem import DBFilesystem
from controlserver.models import db_session, Service, Team, LogMessage, TeamTrafficStats, \
    CheckerFile, CheckerFilesystem, CheckerResult
from controlserver.service_mgr import ServiceRepoManager
from controlserver.vpncontrol import VPNControl, VpnStatus
from saarctf_commons.config import config
from controlserver.logger import log_result_of_execution
from saarctf_commons.redis import get_redis_connection

app = Blueprint('endpoints', __name__)


@app.route('/')
def frontpage() -> ResponseReturnValue:
    from controlserver.timer import Timer, CTFState
    # basic checks - things you should know
    missing_scripts = db_session().query(Service.name).order_by(Service.name) \
        .filter(Service.checker_script_dir.isnot(None)).filter(Service.package.is_(None)).all()
    missing_scoreboard = not (config.SCOREBOARD_PATH / 'api' / 'scoreboard_current.json').exists()
    unwriteable_scoreboard = not missing_scoreboard and \
                             (not os.access(config.SCOREBOARD_PATH, os.W_OK | os.X_OK) or
                              not os.access(config.SCOREBOARD_PATH / 'api', os.W_OK | os.X_OK) or
                              ((config.SCOREBOARD_PATH / 'index.css').exists() and not os.access(
                                  config.SCOREBOARD_PATH / 'index.css', os.W_OK)))
    teams = Team.query.order_by(Team.id).all()
    # render
    return render_template(
        'index.html', Timer=Timer, CTFState=CTFState,
        missing_scripts=', '.join([service_name for service_name, in missing_scripts]),
        missing_scoreboard=missing_scoreboard,
        unwriteable_scoreboard=unwriteable_scoreboard,
        teams=teams,
        fluid_layout=True,
        flower_ajax_url=config.FLOWER_AJAX_URL,
        scoreboard_path=config.SCOREBOARD_PATH
    )


@app.route('/overview/timing')
def overview_timing() -> ResponseReturnValue:
    from controlserver.timer import Timer
    return jsonify({
        'state': Timer.state,
        'desiredState': Timer.desired_state,
        'currentRound': Timer.current_tick,
        'roundStart': Timer.tick_start,
        'roundEnd': Timer.tick_end,
        'roundTime': Timer.tick_time,
        'lastRound': Timer.stop_after_tick,
        'startAt': Timer.start_at,
        'serverTime': int(time.time()),
        'masterTimers': Timer.count_master_timer()
    })


@app.route('/overview/set_timing', methods=['POST'])
def overview_set_timing() -> ResponseReturnValue:
    from controlserver.timer import Timer, CTFState
    body: dict[str, Any] = request.json  # type: ignore
    if 'state' in body:
        state = CTFState(body['state'])
        if state == CTFState.RUNNING:
            Timer.start_ctf()
        elif state == CTFState.SUSPENDED:
            Timer.suspend_ctf_after_tick()
        elif state == CTFState.STOPPED:
            Timer.stop_ctf_after_tick()
    if 'roundtime' in body:
        roundtime = body['roundtime']
        if roundtime >= 5 and roundtime < 1000:
            Timer.tick_time = roundtime
    if 'lastround' in body:
        lastround = body['lastround'] or None
        if lastround is None or lastround > Timer.current_tick:
            Timer.stop_after_tick = lastround
        elif lastround == Timer.current_tick:
            Timer.stop_ctf_after_tick()
    if 'startAt' in body:
        startAt = body['startAt'] or None
        if startAt is None or startAt >= int(time.time()):
            Timer.start_at = startAt
    return 'OK'


@app.route('/overview/logs')
@app.route('/overview/logs/<int:minId>')
def overview_logs(minId: Optional[int] = None) -> ResponseReturnValue:
    if minId is not None:
        logs = LogMessage.query.filter(LogMessage.level >= LogMessage.INFO).filter(LogMessage.id > minId) \
            .order_by(LogMessage.id.desc()).limit(100).all()
    else:
        logs = LogMessage.query.filter(LogMessage.level >= LogMessage.INFO).order_by(LogMessage.id.desc()).limit(
            30).all()
    log_dicts = LogMessage.serialize_list(logs)
    for log in log_dicts:
        log['created'] = int(log['created'].timestamp())
    return jsonify(log_dicts)


@app.route('/overview/components')
def overview_components() -> ResponseReturnValue:
    clients = [client for client in get_redis_connection().client_list() if int(client['db']) == config.REDIS['db']]
    clients.sort(key=lambda client: client['name'])
    return jsonify({'redis': clients})


@app.route('/overview/vpn')
def overview_vpn() -> ResponseReturnValue:
    vpn = VPNControl()
    banned_teams = [
        {'id': team.id, 'name': team.name, 'network': config.NETWORK.team_id_to_network_range(team.id), 'tick': tick}
        for team, tick in vpn.get_banned_teams()
    ]
    open_teams = [{'id': team.id, 'name': team.name, 'network': config.NETWORK.team_id_to_network_range(team.id)} for
                  team in vpn.get_open_teams()]
    teams_online = Team.query.filter((Team.vpn_connected == True) | (Team.vpn2_connected == True) | (Team.wg_vulnbox_connected == True)).count()
    teams_online_once = Team.query.filter((Team.vpn_connected == False) & (Team.vpn2_connected == False) & (Team.wg_vulnbox_connected == False),
                                          Team.vpn_last_connect != None).count()
    teams_offline = Team.query.filter((Team.vpn_connected == False) & (Team.vpn2_connected == False) & (Team.wg_vulnbox_connected == False),
                                      Team.vpn_last_connect == None).count()

    # format: dt_bytes, dt_syns, dg_bytes, dg_syns, ut_bytes, ut_syns, ug_bytes, ug_syns
    # list of last X time points, ascending
    last = int(request.args.get('last', 0))
    trafficstats = []
    trafficstats_keys = []
    for line in TeamTrafficStats.query_sum_lite().filter(TeamTrafficStats.time > datetime.datetime.fromtimestamp(last)) \
        .filter(TeamTrafficStats.time <= text('NOW()')).filter(
        TeamTrafficStats.time >= text("NOW() - interval '12 hours'")) \
        .group_by(TeamTrafficStats.time).order_by(TeamTrafficStats.time.desc()).limit(60).all():
        trafficstats_keys.append(line[0].timestamp())
        trafficstats.append(list(map(int, line[1:])))

    return jsonify({
        'state': vpn.get_state().value, 'banned': banned_teams, 'permissions': open_teams,
        'teams_online': teams_online, 'teams_online_once': teams_online_once, 'teams_offline': teams_offline,
        'traffic_stats': trafficstats[::-1],
        'traffic_stats_keys': trafficstats_keys[::-1]
    })


@app.route('/overview/set_vpn', methods=['POST'])
def overview_set_vpn() -> ResponseReturnValue:
    vpn = VPNControl()
    body: dict[str, Any] = request.json  # type: ignore
    if 'state' in body:
        vpn.set_state(VpnStatus(body['state']))
    if 'ban' in body:
        vpn.ban_team(body['ban']['team_id'], body['ban']['tick'])
    if 'unban' in body:
        vpn.unban_team(body['unban'])
    if 'add_permission' in body:
        vpn.add_permission_team(body['add_permission'])
    if 'remove_permission' in body:
        vpn.remove_permission_team(body['remove_permission'])
    return 'OK'


@app.route('/packages')
@app.route('/packages/')
def packages() -> ResponseReturnValue:
    session = db_session()
    package_count = session.query(func.count(distinct(CheckerFilesystem.package))).scalar()
    file_count, file_size = session.query(func.count(CheckerFile.id),
                                          func.sum(func.length(CheckerFile.content))).first()  # type: ignore
    return render_template(
        'packages.html',
        package_count=package_count, file_count=file_count, file_size=round((file_size or 0) / 1024),
        services=Service.query.order_by(Service.name).all(), teams=Team.query.order_by(Team.name).all()
    )


@app.route('/packages/update', methods=['POST'])
def packages_update() -> ResponseReturnValue:
    service_mgr = ServiceRepoManager()
    messages = []
    body: dict[str, Any] = request.json  # type: ignore

    if 'service' in body and body['service']:
        services: List[Service] = Service.query.filter(Service.id == int(body['service'])).all()
    elif 'service_file' in body:
        services = Service.query.filter(text(":filename LIKE checker_script_dir || '%'")).params(filename=body['service_file']).all()
    else:
        services = Service.query.all()
    changed_packages = []
    for service in services:
        if service.checker_script_dir:
            if not os.path.exists(service.checker_script_dir):
                messages.append(f'[{service.name}] Folder does not exist: "{service.checker_script_dir}"')
                continue
            # upload package
            package, setup_package, is_new = service_mgr.upload_checker_scripts(service.checker_script_dir)
            # set if changed
            if package != service.package:
                if is_new:
                    messages.append('[{}] Created new package: {}'.format(service.name, package))
                else:
                    messages.append('[{}] Switching to package: {}'.format(service.name, package))
                service.package = package
                changed_packages.append(package)
            else:
                messages.append('[{}] No updates.'.format(service.name))
            checker_script = service.checker_script.split(':')[0]
            if not os.path.exists(os.path.join(service.checker_script_dir, checker_script)):
                messages.append(f'[{service.name}] Checker script "{checker_script}" not found in path "{service.checker_script_dir}"')
            # report stored setup script
            if setup_package != service.setup_package:
                service.setup_package = setup_package
                messages.append(f'[{service.name}] Init script from package: {setup_package}')

    # notify workers, so they will preload these packages
    if changed_packages:
        celery_worker.preload_packages.apply_async(args=(changed_packages,), time_limit=120, soft_time_limit=100)

    db_session().commit()
    messages.append('OK')

    return jsonify(messages)


@app.route('/packages/push', methods=['POST'])
def packages_push() -> ResponseReturnValue:
    packages_db = db_session().query(Service.package).all()
    packages = [x for x, in packages_db if x]

    celery_worker.preload_packages.apply_async(args=(packages,), time_limit=90, soft_time_limit=60)

    return jsonify('Workers notified about {} packages'.format(len(packages)))


@app.route('/packages/run', methods=['POST'])
def packages_run() -> ResponseReturnValue:
    command: str = request.json['command']  # type: ignore
    if not isinstance(command, str):
        return 'No string', 400
    if command:
        print(command)
        task = celery_worker.run_command.apply_async(args=(command,), time_limit=120, soft_timeout=100)
        print(task)
        return jsonify(task.id)
    return jsonify(False)


@app.route('/packages/test', methods=['POST'])
def packages_test() -> ResponseReturnValue:
    body: dict[str, Any] = cast(dict, request.json)
    team_id: int = body.get('team_id', config.SCORING.nop_team_id)  # type: ignore
    team = Team.query.filter(Team.id == team_id).one()
    if 'service_id' in body:
        service_id: int = body['service_id']  # type: ignore
        service = Service.query.filter(Service.id == service_id).one()
    else:
        try:
            service = Service.query.filter(text(":filename LIKE checker_script_dir || '%'")).params(filename=body['service_file']).one()
        except NoResultFound:
            return Response(f'File "{body["service_file"]}" does not belong to a known service', status=400)
    tick: int = body.get('round', 0)  # type: ignore
    if not tick:
        min_round = db_session().query(func.min(CheckerResult.tick)).filter(CheckerResult.team_id == team.id) \
            .filter(CheckerResult.service_id == service.id).scalar()
        tick = min_round - 1 if min_round is not None and min_round < 0 else -1

    # Check for changed files
    if service.checker_script_dir:
        if not os.path.exists(service.checker_script_dir):
            message = f'Folder "{service.checker_script_dir}" does not exist.'
            package = None
        else:
            dbfs = DBFilesystem()
            package, is_new = dbfs.move_folder_to_package(service.checker_script_dir)
            if package == service.package:
                message = 'Testing with CURRENT script'
            elif is_new:
                message = 'Testing with NEW script "{}"'.format(package)
            else:
                message = 'Testing with OLD script "{}"'.format(package)
    else:
        message = 'Script not managed by package'
        package = None

    from controlserver.dispatcher import Dispatcher
    task, result = Dispatcher.default.dispatch_test_script(team, service, tick, package)
    return jsonify({
        'task': task.id,
        'result_id': result.id,
        'message': message,
        'ident': '{}/{} ({})'.format(service.name, team.name, tick)
    })


@app.route('/checker_status')
@app.route('/checker_status/')
@app.route('/checker_status/<int:tick>')
def checker_status(tick: int | None = None) -> ResponseReturnValue:
    from controlserver.timer import Timer
    from controlserver.dispatcher import Dispatcher
    if not tick:
        tick = Timer.current_tick

    session = db_session()
    count = session.query(func.count(CheckerResult.id)).filter(CheckerResult.tick == tick) \
        .filter(CheckerResult.status != 'PENDING').filter(CheckerResult.status != 'REVOKED').scalar()
    combinations = Dispatcher.default.get_tick_combinations(tick)
    if not combinations:
        return render_template('404.html', message='Round {} has not yet been dispatched.'.format(tick)), 404
    services = Service.query.order_by(Service.name).all()

    # Big table statistics
    results: List[CheckerResult] = session.query(CheckerResult.service_id, CheckerResult.status, CheckerResult.time,
                                                 CheckerResult.finished,
                                                 CheckerResult.run_over_time) \
        .filter(CheckerResult.tick == tick).order_by(CheckerResult.finished).all()
    stats_dispatched: dict[int, int] = defaultdict(lambda: 0)  # service => count
    stats_results: dict[int, int] = defaultdict(lambda: 0)  # service => count of results
    stats_finished: dict[int, int] = defaultdict(lambda: 0)  # service => count of non-pending results
    stats_time: dict[int, float] = defaultdict(lambda: 0.0)  # service => sum of execution time
    stats_time_count: dict[int, int] = defaultdict(lambda: 0)  # service => number of execution times
    stats_toolate: dict[int, int] = defaultdict(lambda: 0)  # service => number of too lates
    stats_status: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(lambda: 0))  # service => status => count
    total_status: dict[str, int] = defaultdict(lambda: 0)
    for team_id, service_id in combinations:
        stats_dispatched[service_id] += 1
    for result in results:
        stats_results[result.service_id] += 1
        if result.status != 'REVOKED' and result.status != 'PENDING':
            stats_finished[result.service_id] += 1
        if result.time:
            stats_time[result.service_id] += result.time  # type: ignore[operator]
            stats_time_count[result.service_id] += 1
        stats_status[result.service_id][result.status] += 1
        total_status[result.status] += 1
        if result.run_over_time:
            stats_toolate[result.service_id] += 1
    for service in services:
        stats_status[service.id]['PENDING'] += stats_dispatched[service.id] - stats_results[service.id]
        total_status['PENDING'] += stats_dispatched[service.id] - stats_results[service.id]
    total_time = sum(stats_time.values())
    total_time_count = sum(stats_time_count.values())

    # graph data
    redis = get_redis_connection()
    bucketsize = 5
    tick_start = int(redis.get(f'round:{tick}:start') or 0)
    tick_end = int(redis.get(f'round:{tick}:end') or 0)
    first_finished = None
    last_finished = None
    for r in results:
        if r.finished is not None:
            ts1 = int(floor(r.finished.timestamp()))
            first_finished = ts1 if not first_finished or ts1 < first_finished else first_finished
            ts2 = int(ceil(r.finished.timestamp()))
            last_finished = ts2 if not last_finished or ts2 > last_finished else last_finished
    # List[round => (last_finished, {status => count})]
    finished_per_tick: List[Tuple[datetime.datetime, dict[str, int]]] = []
    no_finished_timestamp = 0
    t = min(tick_start, first_finished or tick_start)
    i = 0
    finished_per_tick.append((datetime.datetime.fromtimestamp(t), defaultdict(lambda: 0)))
    for result in results:
        if result.finished is None:
            no_finished_timestamp += 1
        else:
            while result.finished.timestamp() >= t:
                t += bucketsize
                finished_per_tick.append((datetime.datetime.fromtimestamp(t), copy.copy(finished_per_tick[i][1])))
                i += 1
            finished_per_tick[i][1][result.status if not result.run_over_time else 'TOOLATE'] += 1
    while t < tick_end and t < time.time():
        t += bucketsize
        finished_per_tick.append((datetime.datetime.fromtimestamp(t), copy.copy(finished_per_tick[i][1])))
        i += 1

    return render_template(
        'checker_status.html', tick=tick, services=services, states=CheckerResult.states,
        count_finished=count or 0, count_dispatched=len(combinations),
        server_time=int(time.time()), tick_start=tick_start,
        tick_start_dt=datetime.datetime.fromtimestamp(tick_start), tick_end=tick_end,
        stats_dispatched=stats_dispatched, stats_finished=stats_finished, stats_time=stats_time,
        stats_status=stats_status,
        stats_time_count=stats_time_count, stats_toolate=stats_toolate, total_toolate=sum(stats_toolate.values()),
        total_time=total_time, total_time_count=total_time_count, total_status=total_status,
        status_format={'SUCCESS': 'success', 'FLAGMISSING': 'info', 'MUMBLE': 'info', 'OFFLINE': 'info',
                       'TIMEOUT': 'warning', 'REVOKED': 'danger',
                       'CRASHED': 'danger'},
        finished_per_tick=finished_per_tick, no_finished_timestamp=no_finished_timestamp,
        first_finished=first_finished, last_finished=last_finished
    )


@app.route('/checker_status/overview/')
@app.route('/checker_status/overview/all')
@app.route('/checker_status/overview')
def checker_status_overview() -> ResponseReturnValue:
    from controlserver.timer import Timer
    from controlserver.dispatcher import Dispatcher

    if request.url_rule.rule.endswith('/all'):  # type: ignore
        first_tick = 1
    else:
        first_tick = max(Timer.current_tick - 30, 1)
    last_tick = Timer.current_tick
    redis = get_redis_connection()
    session = db_session()
    results_ok = session.query(CheckerResult.tick, func.count(CheckerResult.id),
                               func.sum(CheckerResult.run_over_time.cast(Integer))).group_by(
        CheckerResult.tick) \
        .filter(CheckerResult.tick >= first_tick).filter(CheckerResult.tick <= last_tick) \
        .filter(CheckerResult.status.in_(['SUCCESS', 'FLAGMISSING', 'MUMBLE', 'OFFLINE'])).all()
    results_warn = session.query(CheckerResult.tick, func.count(CheckerResult.id)).group_by(CheckerResult.tick) \
        .filter(CheckerResult.tick >= first_tick).filter(CheckerResult.tick <= last_tick) \
        .filter(CheckerResult.status == 'TIMEOUT').all()
    results_error = session.query(CheckerResult.tick, func.count(CheckerResult.id)).group_by(CheckerResult.tick) \
        .filter(CheckerResult.tick >= first_tick).filter(CheckerResult.tick <= last_tick) \
        .filter(CheckerResult.status == 'CRASHED').all()
    results_revoked = session.query(CheckerResult.tick, func.count(CheckerResult.id)).group_by(CheckerResult.tick) \
        .filter(CheckerResult.tick >= first_tick).filter(CheckerResult.tick <= last_tick) \
        .filter(CheckerResult.status == 'REVOKED').all()
    results_last_finished = session.query(CheckerResult.tick, func.max(CheckerResult.finished)).group_by(
        CheckerResult.tick) \
        .filter(CheckerResult.tick >= first_tick).filter(CheckerResult.tick <= last_tick).all()

    ticks = {}
    for i in range(first_tick, Timer.current_tick + 1):
        ticks[i] = {
            'number': i,
            'start': datetime.datetime.fromtimestamp(int(redis.get('round:{}:start'.format(i)) or 0),
                                                     datetime.timezone.utc),  # type: ignore
            'end': datetime.datetime.fromtimestamp(int(redis.get('round:{}:end'.format(i)) or 0),
                                                   datetime.timezone.utc),  # type: ignore
            'time': int(redis.get('round:{}:time'.format(i)) or 0),  # type: ignore
            'dispatched': len(Dispatcher.default.get_tick_combinations(i) or []),
            'tasks_ok': 0,
            'tasks_warn': 0,
            'tasks_error': 0,
            'tasks_revoked': 0,
            'tasks_toolate': 0,
            'last_finished': None
        }
    for i, count, over_time in results_ok:
        ticks[i]['tasks_ok'] = count - over_time
        ticks[i]['tasks_toolate'] = over_time
    for i, count in results_warn:
        ticks[i]['tasks_warn'] = count
    for i, count in results_error:
        ticks[i]['tasks_error'] = count
    for i, count in results_revoked:
        ticks[i]['tasks_revoked'] = count
    for i, last_finished in results_last_finished:
        ticks[i]['last_finished'] = last_finished
    return render_template('checker_status_overview.html', ticks=ticks, first_tick=first_tick)


@app.route('/scripts/recreate_scoreboard', methods=['POST'])
def recreate_scoreboard() -> ResponseReturnValue:
    def recreate_scoreboard_inner() -> None:
        from controlserver.scoring.scoring import ScoringCalculation
        from controlserver.scoring.scoreboard import Scoreboard
        from controlserver.timer import Timer, CTFState
        scoring = ScoringCalculation(config.SCORING)
        scoreboard = Scoreboard(scoring)
        scoreboard.create_scoreboard(0, False, False)
        rn = 0
        end_round: int = Timer.current_tick - 1 if Timer.state == CTFState.RUNNING else Timer.current_tick
        while rn <= end_round:
            scoreboard.create_scoreboard(rn, Timer.state != CTFState.STOPPED or end_round > 0, rn == end_round)
            rn += 1
            end_round = Timer.current_tick - 1 if Timer.state == CTFState.RUNNING else Timer.current_tick

    def do_scoreboard() -> None:
        log_result_of_execution(
            'scoring',
            recreate_scoreboard_inner, args=(),
            success='Scoreboard generated manually, took {:.1f} sec',
            error='Scoreboard failed (manually): {} {}'
        )

    threading.Thread(target=do_scoreboard, name='manual_scoreboard', daemon=True).start()
    return jsonify({'ok': True, 'message': 'Recalculation started'})
