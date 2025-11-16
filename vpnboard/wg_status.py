import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from ipaddress import IPv4Address, IPv4Network
from typing import Any

from pyroute2 import WireGuard
from pyroute2.netlink.exceptions import NetlinkError


# INTERFACE_NAME = 'tun'  # for wireguard-sync scripts
INTERFACE_NAME = 'tt-'  # for ctfroute


def eprint(*args: Any, **kwargs: Any) -> None:
    print(*args, file=sys.stderr, **kwargs)


@dataclass
class WgPeerStatus:
    address: str  # CIDR
    connected: bool = False
    last_handshake: datetime | None = None
    remote_addr: str | None = None
    remote_port: int | None = None


@dataclass
class WgStatus:
    team_id: int
    peers: list[WgPeerStatus] = field(default_factory=list)

    @property
    def connection_count(self) -> int:
        count = 0
        for peer in self.peers:
            if peer.connected:
                count += 1
        return count

    def get_peer_for(self, ip: str) -> WgPeerStatus | None:
        addr = IPv4Address(ip)
        for peer in self.peers:
            if addr in IPv4Network(peer.address, strict=False):
                return peer
        return None


def get_wireguard_status(team_id: int, wg: WireGuard | None = None) -> WgStatus:
    if wg is None:
        wg = WireGuard()
    try:
        infos = wg.info(f'{INTERFACE_NAME}{team_id}')
    except NetlinkError as e:
        raise ValueError(e)
    result = WgStatus(team_id)
    infos_dict: dict[str, dict] = dict(infos[0]['attrs'])
    if 'WGDEVICE_A_PEERS' not in infos_dict:
        return result

    for peer_container in infos_dict['WGDEVICE_A_PEERS']:
        try:
            peer_attrs: dict = {attr.name: attr.value for attr in peer_container['attrs']}
            peer_status = WgPeerStatus(address=peer_attrs['WGPEER_A_ALLOWEDIPS'][0]['addr'])
            last_handshake_ts = peer_attrs['WGPEER_A_LAST_HANDSHAKE_TIME']['tv_sec']
            if last_handshake_ts > 0:
                peer_status.last_handshake = datetime.fromtimestamp(last_handshake_ts, tz=timezone.utc)
                # handshake happens every 120sec roughly. We consider a team offline iff it misses two handshakes
                if peer_status.last_handshake > datetime.now(tz=timezone.utc) - timedelta(seconds=245):
                    peer_status.connected = True
            if 'WGPEER_A_ENDPOINT' in peer_attrs:
                peer_status.remote_addr = peer_attrs['WGPEER_A_ENDPOINT'].get('addr', None)
                peer_status.remote_port = peer_attrs['WGPEER_A_ENDPOINT'].get('port', None)
            result.peers.append(peer_status)
        except (KeyError, IndexError) as e:
            eprint(e)
            pass
    return result


'''
demo = {'attrs': [('WGPEER_A_PUBLIC_KEY', b'6oICpgkHX+t6z03lC69p70AOkicJVTCwUpYecCn9YyE='),
                  ('WGPEER_A_PRESHARED_KEY', b'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='),
                  ('WGPEER_A_LAST_HANDSHAKE_TIME', {'tv_sec': 1732402547, 'tv_nsec': 307237903, 'latest handshake': 'Sat Nov 23 22:55:47 2024'}),
                  ('WGPEER_A_PERSISTENT_KEEPALIVE_INTERVAL', 0), ('WGPEER_A_TX_BYTES', 644), ('WGPEER_A_RX_BYTES', 2348),
                  ('WGPEER_A_PROTOCOL_VERSION', 1), ('WGPEER_A_ENDPOINT', {'family': 2, 'port': 32870, 'addr': '109.250.6.249', '__pad': ()}), (
                      'WGPEER_A_ALLOWEDIPS', [
                          {'attrs': [('WGALLOWEDIP_A_CIDR_MASK', 32), ('WGALLOWEDIP_A_FAMILY', 2), ('WGALLOWEDIP_A_IPADDR', '0a:20:0b:88')],
                           'addr': '10.32.11.136/32'}], 32768)]}

demo2 = {'attrs': [('WGPEER_A_PUBLIC_KEY', b'c6D2DKqtLd0FEuKahVZEXjhoeBKUU+2aLe70knmkTTU='),
                   ('WGPEER_A_PRESHARED_KEY', b'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA='),
                   ('WGPEER_A_LAST_HANDSHAKE_TIME', {'tv_sec': 0, 'tv_nsec': 0, 'latest handshake': 'Thu Jan  1 00:00:00 1970'}),
                   ('WGPEER_A_PERSISTENT_KEEPALIVE_INTERVAL', 0), ('WGPEER_A_TX_BYTES', 0), ('WGPEER_A_RX_BYTES', 0),
                   ('WGPEER_A_PROTOCOL_VERSION', 1), ('WGPEER_A_ALLOWEDIPS', [
        {'attrs': [('WGALLOWEDIP_A_CIDR_MASK', 32), ('WGALLOWEDIP_A_FAMILY', 2), ('WGALLOWEDIP_A_IPADDR', '0a:20:0b:86')],
         'addr': '10.32.11.134/32'}], 32768)]}
'''
