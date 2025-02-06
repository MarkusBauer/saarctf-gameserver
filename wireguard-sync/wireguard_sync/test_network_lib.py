from json import load
from pathlib import Path
from random import sample, seed
from typing import Generator, cast

import pytest
from pyroute2 import NDB, WireGuard

from wireguard_sync.network_lib import (
    Peer as LibPeer,
)
from wireguard_sync.network_lib import (
    add_peer,
    get_peers,
    initialize_interface,
    remove_interface,
    remove_peer,
    sync,
    sync_peers,
)

from .rest_api import Interface, Peer

seed(42)


@pytest.fixture
def api_response() -> Interface:
    """
    Read the test_api.json file and return the Interface object

    :return: Interface object
    """
    with open(Path(__file__).parent / "test-api.json", encoding="utf-8") as f:
        return cast(Interface, load(f))


@pytest.fixture
def wg_interface(api_response: Interface) -> Generator[str, None, None]:
    """
    Create a wireguard interface for testing the rest_api module

    :param api_response: Interface object

    :return: Interface object
    """
    ifname = initialize_interface(
        api_response,
        "WDasXfdJKmlVqt3ihd+rZCjwCX4c+jJrsxoUErq4kWQ=",
    )

    yield ifname

    remove_interface(ifname)


def test_create_interface(wg_interface: str) -> None:
    """
    Test the create_interface method

    :param wg_interface: Interface object
    """
    with NDB() as ndb:
        assert wg_interface in list(ndb.interfaces.keys())


def test_add_peer(wg_interface: str, api_response: Interface) -> None:
    """
    Test the add_peer method

    :param wg_interface: Interface object
    :param api_response: Interface object
    """
    wg = WireGuard()
    peers = api_response["peers"]
    for peer in peers:
        key_slot = peer["key_slot"]
        add_peer(wg_interface, LibPeer.from_api(peer))

        wg_peer = wg.info(wg_interface)[0].get("WGDEVICE_A_PEERS")[-1]
        assert key_slot["public_key"] == wg_peer.get("WGPEER_A_PUBLIC_KEY").decode()
        assert peer["cidr"] == wg_peer.get("WGPEER_A_ALLOWEDIPS")[0]["addr"]
    assert len(peers) == len(wg.info(wg_interface)[0].get("WGDEVICE_A_PEERS"))


def test_remove_peer(wg_interface: str, api_response: Interface) -> None:
    """
    Test the remove_peer method

    :param wg_interface: Interface object
    :param api_response: Interface object
    """
    wg = WireGuard()
    peer = api_response["peers"][0]
    add_peer(wg_interface, LibPeer.from_api(peer))

    remove_peer(wg_interface, LibPeer.from_api(peer))

    assert wg.info(wg_interface)[0].get("WGDEVICE_A_PEERS") is None


def test_get_peers(wg_interface: str, api_response: Interface) -> None:
    """
    Test the get_peers method

    :param wg_interface: Interface object
    :param api_response: Interface object
    """
    lib_peers = set(LibPeer.from_api(peer) for peer in api_response["peers"])
    for peer in lib_peers:
        add_peer(wg_interface, peer)
    recovered_peers = get_peers(wg_interface)
    assert lib_peers == recovered_peers


def test_sync_interface(wg_interface: str, api_response: Interface) -> None:
    """
    Test the sync_interface method

    :param wg_interface: Interface object
    :param api_response: Interface object
    """
    lib_peers = [LibPeer.from_api(peer) for peer in api_response["peers"]]
    initial_peer_amount = len(lib_peers) // 2
    for peer in sample(lib_peers, initial_peer_amount):
        add_peer(wg_interface, peer)
    new_peer: Peer = {"key_slot": {"public_key": "MlufzoJkrT5aWGizEyTMCZ+TguveaB314zENP25LNSs="}, "cidr": "10.10.11.128/32"}
    add_peer(wg_interface, LibPeer.from_api(new_peer))

    existing_peers = get_peers(wg_interface)
    assert len(existing_peers) == initial_peer_amount + 1

    sync_peers(wg_interface, api_response)

    recovered_peers = get_peers(wg_interface)
    assert set(lib_peers) == set(recovered_peers)


def test_sync_non_existing_interface(api_response: Interface) -> None:
    """
    Test the sync_interface method with a non-existing interface

    :param api_response: Interface object
    """
    with pytest.raises(Exception):
        sync(api_response)
