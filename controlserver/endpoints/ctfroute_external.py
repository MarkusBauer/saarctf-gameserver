"""
TODO: currently copy/paste, until ctfroute (or its models) are public

These classes are used to (de)serialize the state from/to external systems.

E.g., Yaml config files, etc.
"""
import re
from abc import ABC
from enum import StrEnum
from functools import cached_property
from ipaddress import IPv4Address, IPv4Network
from typing import Annotated, Generic, Literal, Optional, Self, TypeVar, assert_never, Any

from pydantic import AwareDatetime, Field, model_validator, BaseModel, ConfigDict, AliasGenerator
from pydantic.alias_generators import to_camel

# Some ids are used in interface names, we want to keep those ergonomic.
IFNAME_PATTERN = re.compile(r"^[a-zA-Z0-9-_]+$")

# We are using netfilter named sets to refer to network entities (e.g. teams) in rules.
# Names of sets may at most be 16 chars long. To avoid collisions, we prefix them based
# on their origin.
# Furthermore, we use team ids for the names of their wireguard interfaces.
NFT_SET_NAME_MAX_LEN = 16
IFNAME_MAX_LEN = 15
NFT_SET_PREFIX_MAX_LEN = IFNAME_PREFIX_MAX_LEN = 3

NET_ENT_MAX_LEN = IFNAME_MAX_LEN - IFNAME_PREFIX_MAX_LEN
assert NET_ENT_MAX_LEN <= (NFT_SET_NAME_MAX_LEN - NFT_SET_PREFIX_MAX_LEN)


# Special magic values for network entities in gate definitions
class NetRefKeyword(StrEnum):
    known = "known"  # Any known entity
    unknown = "unknown"  # Ip addresses not assigned to anything
    any_vulnbox = "any-vulnbox"
    any_team = "any-team"
    # May be used in conjunction with any-team
    same_team = "same-team"
    other_team = "other-team"
    # TODO These might be handy for custom rules
    # local_teams = "local-teams"
    # remote_teams = "local-teams"


for kw in NetRefKeyword:
    # We use these as nft set names!
    assert len(kw) < NFT_SET_NAME_MAX_LEN


# Prefixes for net entities in gates. We shorten the prefixes before submitting them to
# nft - see NFTSetPrefix
class NetRefPrefix(StrEnum):
    team = "team-"  # Teams entire network
    vulnbox = "vulnbox-"  # Vulnbox of team
    game = "game-"  # Custom net entities


# A Net entity reference is either one of the keywords or a prefix followed by an id
_KWORDS = "|".join(NetRefKeyword)
_PREFIXES = "|".join(NetRefPrefix)
NET_REF_PATTERN = re.compile(rf"^{_KWORDS}|(({_PREFIXES})(.{{1,{NET_ENT_MAX_LEN}}}))$")

# Entity ids are treated as strings internally to discourage writing code that relies on
# numeric properties of ids. However, we don't want to be petty when reading desired
# state from external sources, e.g. requiring quotes on numeric ids in yaml, so we
# coerce numbers to strings.
TeamId = Annotated[
    str,
    Field(
        coerce_numbers_to_str=True,
        max_length=NET_ENT_MAX_LEN,
        # Team ids are used in interface names...
        pattern=IFNAME_PATTERN,
    ),
]
RouterId = Annotated[str, Field(coerce_numbers_to_str=True)]
GateId = Annotated[str, Field(coerce_numbers_to_str=True)]
NetEntityId = Annotated[
    str,
    Field(
        coerce_numbers_to_str=True,
        max_length=NET_ENT_MAX_LEN,
        # As of writing NetEntity IDs aren't used in interface names, but it might
        # become a thing. It's easier to just be consistent with team ids
        pattern=IFNAME_PATTERN,
    ),
]


class CtfRouteBaseModel(BaseModel, ABC):
    model_config = ConfigDict(
        extra="forbid",
        populate_by_name=True,
        alias_generator=AliasGenerator(
            validation_alias=to_camel,
            serialization_alias=to_camel,
        ),
    )


class TeamConnectivity(CtfRouteBaseModel, ABC):
    driver: str


class Anonymization(CtfRouteBaseModel, ABC):
    driver: str


class WireGuardPeer(CtfRouteBaseModel):
    allowed_ips: IPv4Network
    public_key: str
    private_key: Optional[str] = None


class WireGuardTeamConnectivity(TeamConnectivity):
    driver: Literal["wireguard"] = "wireguard"
    public_key: str
    private_key: str
    port: int
    peers: list[WireGuardPeer] = Field(default_factory=list)


class NetfilterAnonymization(Anonymization):
    driver: Literal["netfilter"] = "netfilter"


# Additional network entities that can be configured for your game
class NetEntity(CtfRouteBaseModel):
    id: NetEntityId
    # Optional so you can define gates / rules with them before actually
    # populating their ip addresses
    addresses: Optional[set[IPv4Network]] = Field(default_factory=set)
    # Interface over which this entity will be reached
    # Necessary if you wish to shape the traffic to / from this entity
    interface: Optional[str] = None


class HTBClassTemplate(CtfRouteBaseModel):
    original: Optional[str] = None
    reply: Optional[str] = None
    params: Optional[str] = None
    qdisc: Optional[str] = None

    @model_validator(mode="after")
    def check_params(self) -> Self:
        params_set = self.params is not None
        dir_params_set = self.original is not None and self.reply is not None

        if not params_set ^ dir_params_set:
            raise ValueError(
                "Either params or original and reply need to be set on a"
                " HTBClass(Template)"
            )

        return self


class HTBClass(HTBClassTemplate):
    # Addresses
    addresses: Optional[set[IPv4Network]] = None
    # Nft expressions
    match: Optional[set[str]] = None


class TrafficControl(CtfRouteBaseModel):
    default: HTBClassTemplate
    classes: Optional[list[HTBClass]] = None


class TeamTrafficControl(TrafficControl):
    team: HTBClassTemplate
    internal: Optional[HTBClassTemplate] = None
    net_entities: Optional[dict[NetEntityId, HTBClassTemplate | None]] = None


# Settings for the overall ctf network
class CtfNetwork(CtfRouteBaseModel):
    mtu: Optional[int] = None
    entities: Optional[list[NetEntity]] = Field(default_factory=list)
    nft: Optional[str] = None  # additional nft rules
    team_traffic_control: Optional[TeamTrafficControl] = None
    # Maps interface name to TC config
    traffic_control: Optional[dict[str, TrafficControl]] = None


NetRef = Annotated[str, Field(coerce_numbers_to_str=True, pattern=NET_REF_PATTERN)]


class Period(CtfRouteBaseModel):
    # See https://docs.pydantic.dev/2.1/usage/types/datetime/
    from_time: Optional[AwareDatetime] = None
    to_time: Optional[AwareDatetime] = None


class GateType(StrEnum):
    connection = "connection"
    raw = "raw"


class BaseGate(CtfRouteBaseModel, ABC):
    id: GateId
    type: GateType
    period: Optional[Period] = None


class ConnGate(BaseGate):
    type: Literal[GateType.connection] = GateType.connection
    conn_src: NetRef | None = None
    conn_dst: NetRef | None = None
    # Here you can add an nft expression to limit the scope of your gate, e.g.:
    # tcp dport 2000
    expression: Optional[str] = None


class RawGate(BaseGate):
    type: Literal[GateType.raw] = GateType.raw
    rule: str


Gate = ConnGate | RawGate


class Team(CtfRouteBaseModel):
    id: TeamId
    network: IPv4Network
    gateway: IPv4Address | None = None
    vulnbox: IPv4Address | None = None
    meta: dict[str, str] = Field(default_factory=dict)
    connectivity: WireGuardTeamConnectivity = Field(discriminator="driver")
    # Optional because a default may be specified in the config file
    anonymization: Optional[NetfilterAnonymization] = Field(
        discriminator="driver", default=None
    )


class Router(CtfRouteBaseModel):
    id: RouterId
    host: str
    teams: Optional[set[TeamId]] = Field(default_factory=set)
    net_entities: Optional[set[NetEntityId]] = Field(default_factory=set)

    # Optional because a default may be specified in the config file
    connectivity: Optional[Any] = None


TeamT = TypeVar("TeamT", bound=Team)
RouterT = TypeVar("RouterT", bound=Router)
GateT = TypeVar("GateT", bound=Gate)


class GenericCtfRouteState(CtfRouteBaseModel, Generic[TeamT, RouterT, GateT]):
    network: Optional[CtfNetwork] = Field(default_factory=CtfNetwork)
    teams: list[TeamT] = Field(default_factory=list)
    routers: list[RouterT] = Field(default_factory=list)
    gates: list[Annotated[GateT, Field(discriminator="type")]] = Field(
        default_factory=list
    )


class CtfRouteState(GenericCtfRouteState[Team, Router, GateT]): ...


AnyExternalEntity = Router | Team | Gate
