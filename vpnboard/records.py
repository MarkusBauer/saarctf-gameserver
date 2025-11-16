import logging

from saarctf_commons.metric_utils import Metrics, Value
from vpnboard import VpnStatusHandler, VpnStatus


class MetricStatusHandler(VpnStatusHandler):
    def update_all(self, states: list[VpnStatus], banned_teams: set[int], check_vulnboxes: bool, start: float) -> None:
        routers_up = 0
        testbox_up = 0
        vulnbox_up = 0
        for state in states:
            Metrics.record('vpn_connection', 'connected', 1 if state.connected else 0, ts=start, team_id=state.team.id)
            if state.connected:
                metrics: dict[str, Value] = {
                    'router_up': 0 if state.router_ping_ms is None else 1,
                    'testbox_up': 0 if state.testbox_ping_ms is None else 1,
                    'testbox_ok': 0 if state.testbox_ok else 1,
                }
                if state.router_ping_ms is not None:
                    metrics['router_ping_ms'] = state.router_ping_ms
                    routers_up += 1
                if state.testbox_ping_ms is not None:
                    metrics['testbox_ping_ms'] = state.testbox_ping_ms
                    testbox_up += 1
                if check_vulnboxes:
                    metrics['vulnbox_up'] = 0 if state.vulnbox_ping_ms is None else 1
                    if state.vulnbox_ping_ms is not None:
                        vulnbox_up += 1
                    if state.vulnbox_ping_ms:
                        metrics['vulnbox_ping_ms'] = state.vulnbox_ping_ms
                Metrics.record_many('vpn_board', metrics, ts=start, team_id=state.team.id)


class WireguardPeerLogger(VpnStatusHandler):
    def __init__(self) -> None:
        self._logger = logging.getLogger(self.__class__.__name__)

    def update_wireguard(self, states: list[VpnStatus], banned_teams: set[int], check_vulnboxes: bool, start: float) -> None:
        for state in states:
            if state.wg is not None:
                for peer in state.wg.peers:
                    if peer.connected:
                        logging.info(f'connected peer for {peer.address}', extra={
                            'team_id': state.team.id,
                            'address': peer.address,
                            'last_handshake': peer.last_handshake,
                            'remote_addr': peer.remote_addr,
                            'remote_port': peer.remote_port,
                        })

    def update_all(self, states: list[VpnStatus], banned_teams: set[int], check_vulnboxes: bool, start: float) -> None:
        pass
