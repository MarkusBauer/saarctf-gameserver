"""
Library to manage WireGuard interfaces and configurations
"""

import base64
from errno import ENODEV
from logging import getLogger
from typing import NamedTuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from pyroute2 import NDB, WireGuard
from pyroute2.netlink.exceptions import NetlinkError

import wireguard_sync.rest_api as api
from wireguard_sync.exceptions import InterfaceDoesNotExist

LOGGER = getLogger(__name__)


class KeyPair(NamedTuple):
    public_key: str
    private_key: str


def generate_key_pair() -> KeyPair:
    private_key = x25519.X25519PrivateKey.generate()
    public_key = private_key.public_key()
    public_key_bytes = public_key.public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)
    public_key_base64 = base64.b64encode(public_key_bytes).decode("utf-8")
    private_key_bytes = private_key.private_bytes_raw()
    private_key_base64 = base64.b64encode(private_key_bytes).decode("utf-8")
    return KeyPair(public_key=public_key_base64, private_key=private_key_base64)


def get_interface_name(interface: api.Interface) -> str:
    return f"tun{interface['id']}"


class Peer(NamedTuple):
    public_key: str
    cidr: str

    def to_api(self) -> api.Peer:
        return {
            "key_slot": {
                "public_key": self.public_key,
            },
            "cidr": self.cidr,
        }

    @classmethod
    def from_api(cls, api: api.Peer) -> "Peer":
        return cls(public_key=api["key_slot"]["public_key"], cidr=api["cidr"])


def initialize_interface(interface: api.Interface, private_key: str) -> str:
    """
    Initialize the wireguard interface (idempotent)

    :param interface: Interface object

    :return: Interface name
    """
    ifname = get_interface_name(interface)
    with WireGuard() as wg, NDB() as ndb:
        if ifname not in ndb.interfaces:
            LOGGER.info(f"Creating wireguard interface {ifname}")
            with ndb.interfaces.create(kind="wireguard", ifname=ifname) as link:
                link.add_ip(interface["cidr"])
                link.set(state="up")

            wg.set(interface=ifname, listen_port=interface["port"])

        wg_key = wg.info(ifname)[0].get("WGDEVICE_A_PRIVATE_KEY")
        if wg_key is None or wg_key.decode() != private_key:
            LOGGER.info(f"Setting private key for {ifname}")
            wg.set(ifname, private_key=private_key)

    return ifname


def remove_interface(ifname: str) -> None:
    """
    Remove the wireguard interface

    :param ifname: Interface name
    """
    with NDB() as ndb:
        with ndb.interfaces[ifname] as link:
            link.remove()


def add_peer(ifname: str, peer: Peer) -> None:
    """
    Add a peer to the wireguard interface

    :param ifname: Interface name
    :param peer: Peer object
    """
    peer_conf = {"public_key": peer.public_key, "allowed_ips": [peer.cidr]}
    with WireGuard() as wg:
        try:
            wg.set(ifname, peer=peer_conf)
        except ValueError:
            LOGGER.exception(f"Failed to set wg peer {peer}")


def remove_peer(ifname: str, peer: Peer) -> None:
    """
    Remove a peer from the wireguard interface

    :param peer: Peer object
    """
    peer_config = {"public_key": peer.public_key, "remove": True}
    with WireGuard() as wg:
        try:
            wg.set(ifname, peer=peer_config)
        except ValueError:
            LOGGER.exception(f"Failed to set wg peer {peer}")


def get_peers(wg_interface: str) -> set[Peer]:
    """
    Get all peers from the wireguard interface

    :param wg_interface: Interface name

    :return: List of Peer objects
    """
    recovered_peers = set()
    with WireGuard() as wg:
        for sub_info in wg.info(wg_interface):
            peer_info = sub_info.get("WGDEVICE_A_PEERS")
            if peer_info is None:
                continue
            for peers in peer_info:
                for i in range(len(peers)):  # Not directly iterable!
                    peer = peers[i]
                    allowed_ips = peer.get("WGPEER_A_ALLOWEDIPS")
                    try:
                        recovered_peers.add(
                            Peer(
                                public_key=peer.get("WGPEER_A_PUBLIC_KEY").decode(),
                                cidr=allowed_ips[0]["addr"],
                            )
                        )
                    except (KeyError, IndexError):
                        LOGGER.warning(f'Invalid peer for {wg_interface}. allowed_ips={allowed_ips}')
    return recovered_peers


def sync(interface: api.Interface) -> None:
    """
    Sync the wireguard interface with the described interface

    :param interface: Interface object
    """
    ifname = get_interface_name(interface)
    try:
        sync_peers(ifname, interface)
    except NetlinkError as e:
        if e.code == ENODEV:
            raise InterfaceDoesNotExist(ifname) from e
        LOGGER.exception(f"Failed to sync peers for {ifname}")
        raise e


def sync_peers(ifname: str, interface: api.Interface) -> None:
    """
    Sync the wireguard interface peers with the described peers

    :param ifname: Interface name
    :param interface: Interface object

    :return: None
    """
    requested_peers = set(Peer.from_api(api_peer) for api_peer in interface["peers"])
    existing_peers = get_peers(ifname)

    # First remove...
    for peer in existing_peers.difference(requested_peers):
        remove_peer(ifname, peer)

    # then add, otherwise there might be conflicting addresses!
    for peer in requested_peers.difference(existing_peers):
        add_peer(ifname, peer)

    new_peers = get_peers(ifname)
    if new_peers != requested_peers:
        LOGGER.error(f"Peer mismatch after sync on {ifname}")
