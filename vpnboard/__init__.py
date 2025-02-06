from abc import ABC, abstractmethod
from dataclasses import dataclass

from controlserver.models import Team
from vpnboard.wg_status import WgStatus


@dataclass
class VpnStatus:
    team: Team
    wg: WgStatus | None = None
    router_ping_ms: float | None = None
    testbox_ping_ms: float | None = None
    testbox_ok: bool = False
    testbox_err: str | None = None
    vulnbox_ping_ms: float | None = None  # only filled if explicitly selected

    @property
    def connected(self) -> bool:
        return self.team.vpn_connected or self.team.vpn2_connected or self.team.wg_boxes_connected


class VpnStatusHandler(ABC):
    @abstractmethod
    def update(self, states: list[VpnStatus], banned_teams: set[int], check_vulnboxes: bool, start: float) -> None:
        raise NotImplementedError()
