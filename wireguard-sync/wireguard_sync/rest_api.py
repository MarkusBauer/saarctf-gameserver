"""
This module contains the type definitions for the REST API.
"""

from typing import TypedDict


class KeySlot(TypedDict):
    public_key: str


class Peer(TypedDict):
    key_slot: KeySlot
    cidr: str


class MinimalInterface(TypedDict):
    id: int


class Interface(MinimalInterface):
    cidr: str
    public_key: str | None
    last_modified: str | None
    peers: list[Peer]
    port: int
