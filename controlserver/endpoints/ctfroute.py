import time
from datetime import timezone, datetime, timedelta

from flask import Blueprint, jsonify, make_response, Response

from controlserver.endpoints.ctfroute_external import CtfRouteState, Gate, ConnGate, Period
from controlserver.timer import CTFState
from controlserver.vpncontrol import VPNControl, VpnStatus

app = Blueprint("ctfroute", __name__)


def _is_close_to_now(ts: int) -> bool:
    return abs(time.time() - ts) < 5.0  # 5sec is the grace time of timed events


def _is_in_future(ts: int) -> bool:
    return ts > time.time() - 5.0


def _get_game_start_time() -> datetime | None:
    from controlserver.timer import Timer

    if Timer.start_at and _is_in_future(Timer.start_at) and (Timer.state != CTFState.RUNNING or _is_close_to_now(Timer.start_at)):
        return datetime.fromtimestamp(Timer.start_at, tz=timezone.utc)

    return None


def _get_end_of_tick(tick: int | None) -> datetime | None:
    from controlserver.timer import Timer

    open_at: datetime | None = _get_game_start_time()

    # already running
    if Timer.state == CTFState.RUNNING and tick and tick >= Timer.current_tick and Timer.tick_end:
        ts = Timer.tick_end + (tick - Timer.current_tick) * Timer.tick_time
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    # start scheduled
    elif Timer.state != CTFState.RUNNING and tick and tick >= Timer.current_tick and open_at:
        return open_at + timedelta(seconds=(tick - Timer.current_tick) * Timer.tick_time)

    return None


def add_per_team_gates(state: CtfRouteState) -> None:
    """Bans etc"""
    vpn = VPNControl()
    for team_id, end_tick in vpn.get_banned_team_ids():
        state.gates.append(ConnGate(
            id=f"ban-team-{team_id}",
            period=Period(to_time=_get_end_of_tick(end_tick)),
            conn_src=f"team-{team_id}",
        ))


def add_vpn_gates(state: CtfRouteState) -> None:
    """Network open/close etc"""
    from controlserver.timer import Timer

    # determine important timestamps
    open_at: datetime | None = _get_game_start_time()
    open_vulnbox_at: datetime | None = open_at
    close_at: datetime | None = None
    # open network time set
    if Timer.open_vulnbox_access_at and _is_in_future(Timer.open_vulnbox_access_at):
        open_vulnbox_at = datetime.fromtimestamp(Timer.open_vulnbox_access_at, tz=timezone.utc)
        if open_at and open_vulnbox_at > open_at:  # game start also opens VPN
            open_vulnbox_at = open_at
    # end after current tick
    if Timer.desired_state == CTFState.STOPPED and Timer.state == CTFState.RUNNING and Timer.tick_end:
        close_at = datetime.fromtimestamp(Timer.tick_end, tz=timezone.utc)
    # end after programmed tick
    elif Timer.stop_after_tick:
        close_at = _get_end_of_tick(Timer.stop_after_tick)

    vpn_state = VPNControl().get_state()
    if vpn_state == VpnStatus.OFF:
        state.gates.append(ConnGate(
            id="vpn-state-off",
            expression="meta l4proto != icmp",
            period=Period(to_time=open_at),
        ))
    if vpn_state == VpnStatus.TEAMS_ONLY or vpn_state == VpnStatus.TEAMS_ONLY_NO_VULNBOX:
        state.gates.append(ConnGate(
            id="vpn-state-teams-only",
            conn_src="any-team",
            conn_dst="other-team",
            expression="ip daddr != @g-gameservers",
            period=Period(to_time=open_at),
        ))
        if vpn_state == VpnStatus.TEAMS_ONLY_NO_VULNBOX:
            state.gates.append(ConnGate(
                id="vpn-state-teams-only-no-vulnbox",
                conn_src="any-team",
                conn_dst="any-vulnbox",
                period=Period(to_time=open_vulnbox_at),
            ))
    # planned network close
    if vpn_state == VpnStatus.ON and close_at:
        state.gates.append(ConnGate(
            id="vpn-state-teams-only-after-game",
            conn_src="any-team",
            conn_dst="other-team",
            expression="ip daddr != @g-gameservers",
            period=Period(from_time=close_at),
        ))


@app.route("/api/ctfroute/full", methods=["GET"])
def api_ctfroute_full() -> Response:
    state: CtfRouteState = CtfRouteState()
    add_per_team_gates(state)
    add_vpn_gates(state)
    return jsonify(state.model_dump(mode='json'))


@app.route("/api/ctfroute/teams", methods=["GET"])
def api_ctfroute_teams() -> Response:
    state: CtfRouteState = CtfRouteState()
    add_per_team_gates(state)
    return jsonify(state.model_dump(mode='json'))


@app.route("/api/ctfroute/times", methods=["GET"])
def api_ctfroute_times() -> Response:
    state: CtfRouteState = CtfRouteState()
    add_vpn_gates(state)
    return jsonify(state.model_dump(mode='json'))
