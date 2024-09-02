"""
ORM wrappers for all database tables (using SQLAlchemy).
For a database connection, Flask is needed (import controlserver.app).

"""
import typing
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, List

from flask import Flask, g
from sqlalchemy import func, UniqueConstraint, ForeignKey, inspect, text, MetaData, create_engine, Column, Integer, \
    String, LargeBinary, TIMESTAMP, \
    SmallInteger, BigInteger, Float, Boolean
from sqlalchemy.dialects.postgresql import insert, Insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import relationship, scoped_session, sessionmaker, Query, Session
from sqlalchemy.ext.declarative import declarative_base, DeclarativeMeta
import hashlib
import io

from saarctf_commons.config import config

meta = MetaData()
Base: DeclarativeMeta = declarative_base(metadata=meta)  # type: ignore


class ModelMixin:
    def __str__(self) -> str:
        return self.__class__.__name__ + '<' + ', '.join(
            f'{col.name}={getattr(self, col.name)}' for col in self.__table__.columns) + '>'  # type: ignore

    def __repr__(self) -> str:
        return str(self)


class Database:
    # having these in global variables is kinda ugly. but in contrast to Flask's context, it actually works.
    db_engine: Engine
    db_session_factory: sessionmaker
    db_session: scoped_session
    query: Query


def init_database(app: Flask | None = None) -> None:
    engine = create_engine(config.postgres_sqlalchemy(), echo=False)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = scoped_session(session_factory)
    Base.query = session.query_property()  # type: ignore

    Database.db_engine = engine
    Database.db_session_factory = session_factory
    Database.db_session = session

    if app:
        g.db_engine = engine
        g.db_session = session

        @app.teardown_appcontext
        def shutdown_session(exception: Any = None) -> None:
            session.remove()


def close_database() -> None:
    Database.db_session.close_all()
    Database.db_engine.dispose()
    Database.db_session = None  # type: ignore
    Database.db_engine = None  # type: ignore


def db_session() -> scoped_session:
    return Database.db_session


@contextmanager
def db_session_2() -> typing.Generator[Session, None, None]:
    with Database.db_session_factory() as session:
        yield session


class Serializer(object):
    def serialize(self) -> dict[str, Any]:
        return {c: getattr(self, c) for c in inspect(self).attrs.keys()}

    @staticmethod
    def serialize_list(l: list) -> list[dict]:
        return [m.serialize() for m in l]


class Team(Base, ModelMixin):
    __tablename__ = 'teams'
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    affiliation = Column(String(128), nullable=True, server_default=text('NULL'))
    website = Column(String(128), nullable=True, server_default=text('NULL'))
    logo = Column(String(64), nullable=True, server_default=text('NULL'))  # reference to TeamLogo.hash
    points = relationship("TeamPoints", back_populates="team")
    vpn_connected = Column(Boolean, nullable=False, server_default=text('FALSE'))  # team-hosted VPN
    vpn2_connected = Column(Boolean, nullable=False, server_default=text('FALSE'))  # cloud-hosted vulnbox VPN
    vpn_last_connect = Column(TIMESTAMP(timezone=True), nullable=True, server_default=text('NULL'))
    vpn_last_disconnect = Column(TIMESTAMP(timezone=True), nullable=True, server_default=text('NULL'))
    vpn_connection_count = Column(Integer, nullable=False, server_default=text('0'))  # "cloud"-style VPN connections

    query: 'Query[Team]'

    @property
    def vulnbox_ip(self) -> str:
        return config.NETWORK.team_id_to_vulnbox_ip(self.id)


class TeamLogo(Base):
    """
    Team logos stored in database.
    Each logo is keyed by the md5-hash of the original source image ("hash") before compression.
    """
    __tablename__ = 'team_logos'
    id = Column(Integer, primary_key=True)
    hash = Column(String(64), nullable=False, unique=True, index=True)
    content = Column(LargeBinary, nullable=False)

    target_size = 256

    query: 'Query[TeamLogo]'

    @classmethod
    def store_logo_file(cls, fname: str) -> str:
        """
        Store a source file from disk into database (if not already there).
        :param fname:
        :return: md5-hash that identifies this image later.
        """
        with open(fname, 'rb') as f:
            return cls.store_logo_bytes(f.read())

    @classmethod
    def store_logo_bytes(cls, data: bytes) -> str:
        """
        Store a logo image (given in memory) into database (if not already there).
        :param data:
        :return: md5-hash that identifies this image later.
        """
        imghash = hashlib.md5(data).hexdigest()
        if cls.query.filter(cls.hash == imghash).count() > 0:
            return imghash
        # load, resize and pad logo image
        from PIL import Image
        img = Image.open(io.BytesIO(data))
        w = round(img.width * cls.target_size / max(img.width, img.height))
        h = round(img.height * cls.target_size / max(img.width, img.height))
        img = img.resize((w, h), Image.Resampling.BICUBIC)
        new_img = Image.new('RGBA', (cls.target_size, cls.target_size), (0, 0, 0, 0))
        new_img.paste(img, ((cls.target_size - w) // 2, (cls.target_size - h) // 2))
        # save
        image_bytes = io.BytesIO()
        new_img.save(image_bytes, format='PNG')
        db_session().add(TeamLogo(hash=imghash, content=image_bytes.getvalue()))
        db_session().commit()
        return imghash

    @classmethod
    def save_image(cls, imghash: str | Path, fname: str | Path) -> None:
        """
        Save a database image to disk, identified by md5-hash of the source image.
        Overrides existing files.
        :param imghash: source image's hash
        :param fname: disk path where the file should be saved.
        """
        img = cls.query.filter(cls.hash == imghash).first()
        if not img:
            raise Exception(f'Image missing: {imghash}')
        with open(fname, 'wb') as f:
            f.write(img.content)


class Service(Base, ModelMixin):
    __tablename__ = 'services'
    id = Column(Integer, primary_key=True)
    name = Column(String(128), nullable=False)
    checker_script_dir = Column(String, nullable=True,
                                server_default=text('NULL'))  # path on the master server containing checker files
    checker_script = Column(String, nullable=False)  # filename:classname (relative to the classpath)
    checker_timeout = Column(Integer, nullable=False, server_default=text('30'))
    checker_enabled = Column(Boolean, nullable=False, server_default=text('TRUE'))
    checker_subprocess = Column(Boolean, nullable=False, server_default=text('FALSE'))
    checker_route = Column(String(64), nullable=True, server_default=text('NULL'))
    package = Column(String(32), nullable=True)  # package the checker files have been moved to
    setup_package = Column(String(32), nullable=True, server_default=text('NULL'))  # package containing an init script
    num_payloads = Column(Integer, nullable=False,
                          server_default=text('0'))  # number of possible payloads. 0 = unlimited
    flag_ids = Column(String(128), nullable=True, server_default=text('NULL'))  # flag id types, comma-separated
    flags_per_round = Column(Float, nullable=False,
                             server_default=text('1'))  # number of issued flags per round, used for scoring

    query: 'Query[Service]'


class TeamPoints(Base, ModelMixin):
    """
    The points a team has per service AFTER round has been counted.
    Includes the incremental points from previous rounds.
    """
    __tablename__ = 'team_points'

    id = Column(Integer, primary_key=True)
    round = Column(Integer, nullable=False, index=True)
    team_id = Column(SmallInteger, ForeignKey('teams.id', ondelete="CASCADE"), nullable=False)
    service_id = Column(SmallInteger, ForeignKey('services.id', ondelete="CASCADE"), nullable=False)
    team_points_unique_1 = UniqueConstraint('round', 'team_id', 'service_id', name='team_points_unique_1')
    __table_args__ = (team_points_unique_1,)

    # modify these columns to fit your scoring scheme (and check the methods below)
    flag_captured_count = Column(Integer, nullable=False)  # captured BY this team
    flag_stolen_count = Column(Integer, nullable=False)  # stolen FROM this team
    off_points = Column(Float, nullable=False)
    def_points = Column(Float, nullable=False)
    sla_points = Column(Float, nullable=False)
    sla_delta = Column(Float, nullable=False)

    team = relationship("Team", back_populates="points")

    query: 'Query[TeamPoints]'

    def props_dict(self) -> Dict:
        return {
            'round': self.round,
            'team_id': self.team_id,
            'service_id': self.service_id,
            'flag_captured_count': self.flag_captured_count,
            'flag_stolen_count': self.flag_stolen_count,
            'off_points': self.off_points,
            'def_points': self.def_points,
            'sla_points': self.sla_points,
            'sla_delta': self.sla_delta,
        }

    @classmethod
    def upsert(cls) -> Insert:
        """
        Usage: db_session().execute(TeamPoints.upsert().values(teampoints.props_dict()))
        :return:
        """
        stmt = insert(TeamPoints)
        stmt = stmt.on_conflict_do_update(
            constraint=cls.team_points_unique_1,
            set_={'flag_captured_count': stmt.excluded.flag_captured_count,
                  'flag_stolen_count': stmt.excluded.flag_stolen_count,
                  'off_points': stmt.excluded.off_points, 'def_points': stmt.excluded.def_points,
                  'sla_points': stmt.excluded.sla_points,
                  'sla_delta': stmt.excluded.sla_delta}
        )
        return stmt

    @classmethod
    def efficient_insert(cls, tick: int, items: typing.Collection['TeamPoints | TeamPointsLite'],
                         session: Session | None = None) -> None:
        if len(items) == 0:
            return
        cursor = (session or db_session()).connection().connection.cursor()
        sql = 'INSERT INTO team_points (team_id, service_id, round, flag_captured_count, flag_stolen_count, off_points, def_points, sla_points, sla_delta) ' + \
              'SELECT unnest(%(teams)s) , unnest(%(services)s), {}, unnest(%(flag_captured_count)s), unnest(%(flag_stolen_count)s), ' \
              'unnest(%(off_points)s), unnest(%(def_points)s), unnest(%(sla_points)s), unnest(%(sla_delta)s)'.format(
                  tick)
        cursor.execute(sql, {
            'teams': [x.team_id for x in items],
            'services': [x.service_id for x in items],
            'flag_captured_count': [x.flag_captured_count for x in items],
            'flag_stolen_count': [x.flag_stolen_count for x in items],
            'off_points': [x.off_points for x in items],
            'def_points': [x.def_points for x in items],
            'sla_points': [x.sla_points for x in items],
            'sla_delta': [x.sla_delta for x in items],
        })


class TeamPointsLite:
    def __init__(self, team_id, service_id, round, flag_captured_count: int = 0, flag_stolen_count: int = 0,
                 off_points: float = 0.0, def_points: float = 0.0, sla_points: float = 0.0,
                 sla_delta: float = 0.0) -> None:
        self.team_id = team_id
        self.service_id = service_id
        self.round = round
        self.flag_captured_count: int = flag_captured_count
        self.flag_stolen_count: int = flag_stolen_count
        self.off_points: float = off_points
        self.def_points: float = def_points
        self.sla_points: float = sla_points
        self.sla_delta: float = sla_delta

    @classmethod
    def query(cls, session: Session | None = None):
        if session is None:
            session = db_session()
        return session.query(TeamPoints.team_id, TeamPoints.service_id, TeamPoints.round,
                             TeamPoints.flag_captured_count, TeamPoints.flag_stolen_count,
                             TeamPoints.off_points, TeamPoints.def_points, TeamPoints.sla_points,
                             TeamPoints.sla_delta)


class TeamRanking(Base, ModelMixin):
    """
    Scoreboard position of a team AFTER a round
    """
    __tablename__ = 'team_rankings'
    id = Column(Integer, primary_key=True)
    round = Column(Integer, nullable=False, index=True)
    team_id = Column(SmallInteger, ForeignKey('teams.id', ondelete="CASCADE"), nullable=False)
    rank = Column(Integer, nullable=False)  # rank [1, ...]
    points = Column(Float, nullable=False)  # total points
    __table_args__ = (UniqueConstraint('round', 'team_id', name='team_rankings_unique_1'),)
    team = relationship("Team")

    query: 'Query[TeamRanking]'


class TeamTrafficStats(Base, ModelMixin):
    """
    The points a team has per service AFTER round has been counted
    """
    __tablename__ = 'team_traffic_stats'

    id = Column(Integer, primary_key=True)
    time = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    team_id = Column(SmallInteger, ForeignKey('teams.id', ondelete="CASCADE"), nullable=False)
    __table_args__ = (UniqueConstraint('time', 'team_id', name='team_traffic_stats_unique_1'),)

    # what we save about traffic
    down_teams_packets = Column(BigInteger, nullable=False)
    down_teams_bytes = Column(BigInteger, nullable=False)
    down_teams_syns = Column(BigInteger, nullable=False)
    down_teams_syn_acks = Column(BigInteger, nullable=False)
    down_game_packets = Column(BigInteger, nullable=False)
    down_game_bytes = Column(BigInteger, nullable=False)
    down_game_syns = Column(BigInteger, nullable=False)
    down_game_syn_acks = Column(BigInteger, nullable=False)
    up_teams_packets = Column(BigInteger, nullable=False)
    up_teams_bytes = Column(BigInteger, nullable=False)
    up_teams_syns = Column(BigInteger, nullable=False)
    up_teams_syn_acks = Column(BigInteger, nullable=False)
    up_game_packets = Column(BigInteger, nullable=False)
    up_game_bytes = Column(BigInteger, nullable=False)
    up_game_syns = Column(BigInteger, nullable=False)
    up_game_syn_acks = Column(BigInteger, nullable=False)
    forward_self_packets = Column(BigInteger, nullable=False)
    forward_self_bytes = Column(BigInteger, nullable=False)
    forward_self_syns = Column(BigInteger, nullable=False)
    forward_self_syn_acks = Column(BigInteger, nullable=False)

    query: 'Query[TeamTrafficStats]'

    @classmethod
    def efficient_insert(cls, timestamp: int, items: Dict[int, List[int]]) -> None:
        assert type(timestamp) is int
        cursor = db_session().connection().connection.cursor()
        sql = 'INSERT INTO team_traffic_stats ("time", team_id, ' \
              'down_game_packets, down_game_bytes, down_game_syns, down_game_syn_acks, ' \
              'down_teams_packets, down_teams_bytes, down_teams_syns, down_teams_syn_acks, ' \
              'up_game_packets, up_game_bytes, up_game_syns, up_game_syn_acks, ' + \
              'up_teams_packets, up_teams_bytes, up_teams_syns, up_teams_syn_acks, ' \
              'forward_self_packets, forward_self_bytes, forward_self_syns, forward_self_syn_acks) ' \
              f'SELECT to_timestamp({timestamp}), unnest(%(teams)s), ' \
              'unnest(%(v0)s), unnest(%(v1)s), unnest(%(v2)s), unnest(%(v3)s), ' \
              'unnest(%(v4)s), unnest(%(v5)s), unnest(%(v6)s), unnest(%(v7)s), ' \
              'unnest(%(v8)s), unnest(%(v9)s), unnest(%(v10)s), unnest(%(v11)s), ' \
              'unnest(%(v12)s), unnest(%(v13)s), unnest(%(v14)s), unnest(%(v15)s), ' \
              'unnest(%(v16)s), unnest(%(v17)s), unnest(%(v18)s), unnest(%(v19)s)'
        data: Dict[str, List[int]] = {
            'teams': []
        }
        for i in range(20):
            data[f'v{i}'] = []
        for team_id, values in items.items():
            data['teams'].append(team_id)
            for i, v in enumerate(values):
                data['v' + str(i)].append(v)
        cursor.execute(sql, data)

    @classmethod
    def query_sum(cls):
        return db_session().query(
            func.sum(cls.down_teams_packets),
            func.sum(cls.down_teams_bytes),
            func.sum(cls.down_teams_syns),
            func.sum(cls.down_teams_syn_acks),
            func.sum(cls.down_game_packets),
            func.sum(cls.down_game_bytes),
            func.sum(cls.down_game_syns),
            func.sum(cls.down_game_syn_acks),
            func.sum(cls.up_teams_packets),
            func.sum(cls.up_teams_bytes),
            func.sum(cls.up_teams_syns),
            func.sum(cls.up_teams_syn_acks),
            func.sum(cls.up_game_packets),
            func.sum(cls.up_game_bytes),
            func.sum(cls.up_game_syns),
            func.sum(cls.up_game_syn_acks),
            func.sum(cls.forward_self_packets),
            func.sum(cls.forward_self_bytes),
            func.sum(cls.forward_self_syns),
            func.sum(cls.forward_self_syn_acks)
        )

    @classmethod
    def query_sum_lite(cls):
        return db_session().query(
            cls.time,
            func.sum(cls.down_teams_bytes),
            func.sum(cls.down_teams_syns),
            func.sum(cls.down_game_bytes),
            func.sum(cls.down_game_syns),
            func.sum(cls.up_teams_bytes),
            func.sum(cls.up_teams_syns),
            func.sum(cls.up_game_bytes),
            func.sum(cls.up_game_syns),
        )


class SubmittedFlag(Base, ModelMixin):
    """
    Stolen flags submitted to us. Filled by the submitter script. No foreign references for performance reasons.
    """
    __tablename__ = 'submitted_flags'
    id = Column(Integer, primary_key=True)
    submitted_by = Column(SmallInteger, nullable=False)  # references teams (attacking team)
    team_id = Column(SmallInteger, nullable=False)  # references teams (exploited team)
    service_id = Column(SmallInteger, nullable=False)  # references services
    round_issued = Column(SmallInteger, nullable=False)
    payload = Column(Integer, nullable=False, server_default=text('0'))  # more or less random payload
    round_submitted = Column(SmallInteger, nullable=False, index=True)  # submitted in this round
    is_firstblood = Column(Boolean, nullable=False, server_default=text('FALSE'), index=True)
    ts = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (UniqueConstraint('submitted_by', 'team_id', 'service_id', 'round_issued', 'payload',
                                       name='submitted_flags_unique_1'),)
    submitted_by_team = relationship('Team', foreign_keys=[submitted_by],
                                     primaryjoin='Team.id == SubmittedFlag.submitted_by')
    victim_team = relationship('Team', foreign_keys=[team_id], primaryjoin='Team.id == SubmittedFlag.team_id')

    query: 'Query[SubmittedFlag]'

    @classmethod
    def efficient_insert(cls, items) -> None:
        if len(items) == 0:
            return
        cursor = db_session().connection().connection.cursor()
        sql = f'INSERT INTO {cls.__tablename__} (team_id, service_id, round_issued, payload, submitted_by, round_submitted) ' + \
              'SELECT unnest(%(team_id)s) , unnest(%(service_id)s), unnest(%(round_issued)s), unnest(%(payload)s), ' \
              'unnest(%(submitted_by)s), unnest(%(round_submitted)s)'
        cursor.execute(sql, {
            'team_id': [x.team_id for x in items],
            'service_id': [x.service_id for x in items],
            'round_issued': [x.round_issued for x in items],
            'payload': [x.payload for x in items],
            'submitted_by': [x.submitted_by for x in items],
            'round_submitted': [x.round_submitted for x in items],
        })


class CheckerResult(Base, ModelMixin):
    """
    Results of each checkerscript invocation. Created by the script runner (or the dispatcher if the runner crashed).
    """

    __tablename__ = 'checker_results'
    id = Column(Integer, primary_key=True)
    round = Column(Integer, nullable=False, index=True)
    team_id = Column(SmallInteger, ForeignKey('teams.id', ondelete="CASCADE"), nullable=False)
    service_id = Column(SmallInteger, ForeignKey('services.id', ondelete="CASCADE"), nullable=False)
    checker_results_unique_1 = UniqueConstraint('round', 'team_id', 'service_id', name='checker_results_unique_1')
    __table_args__ = (checker_results_unique_1,)

    # status can be: SUCCESS, FLAGMISSING, MUMBLE, OFFLINE, TIMEOUT, REVOKED, CRASHED, PENDING (this one only for test runs)
    status = Column(String(12), nullable=False, index=True)
    message = Column(String, nullable=True, server_default=text('NULL'))
    time = Column(Float, nullable=True, server_default=text('NULL'))
    integrity = Column(Boolean, nullable=False,
                       server_default=text('FALSE'))  # DEAD BY NOW - true if integrity check has been passed
    stored = Column(Boolean, nullable=False, server_default=text('FALSE'))  # DEAD BY NOW - true if flag could be stored
    retrieved = Column(Boolean, nullable=False,
                       server_default=text('FALSE'))  # DEAD BY NOW - true if flag could be retrieved
    celery_id = Column(String(40), nullable=False)
    output = Column(String, nullable=True, server_default=text('NULL'))
    finished = Column(TIMESTAMP(timezone=True), nullable=True, server_default=text('NULL'))
    # true if the task finished, but was too late (already revoked)
    run_over_time = Column(Boolean, nullable=False, server_default=text('FALSE'), default=False)

    # Additional state: "PENDING" (only possible for test runs)
    states = ['SUCCESS', 'FLAGMISSING', 'MUMBLE', 'OFFLINE', 'TIMEOUT', 'REVOKED', 'CRASHED']

    team = relationship("Team")
    service = relationship("Service")

    query: 'Query[CheckerResult]'

    def __init__(self, **kwargs) -> None:
        super(CheckerResult, self).__init__(**kwargs)
        if self.integrity is None: self.integrity = False
        if self.stored is None: self.stored = False
        if self.retrieved is None: self.retrieved = False

    def props_dict(self) -> dict[str, Any]:
        return {
            'round': self.round,
            'team_id': self.team_id,
            'service_id': self.service_id,
            'status': self.status,
            'message': self.message,
            'time': self.time,
            'integrity': self.integrity,
            'stored': self.stored,
            'retrieved': self.retrieved,
            'celery_id': self.celery_id,
            'output': self.output,
            'run_over_time': self.run_over_time or False,
            'finished': self.finished
        }

    @classmethod
    def upsert(cls, entry: 'CheckerResult| None' = None) -> Insert:
        """
        Usage: db_session().execute(CheckerResult.upsert().values(instance.props_dict()))
        :return:
        """
        stmt = insert(CheckerResult)
        data = {
            'status': stmt.excluded.status,
            'message': stmt.excluded.message,
            'time': stmt.excluded.time,
            'integrity': stmt.excluded.integrity,
            'stored': stmt.excluded.stored,
            'retrieved': stmt.excluded.retrieved,
            'celery_id': stmt.excluded.celery_id,
            'output': stmt.excluded.output
        }
        if entry and entry.run_over_time is not None:
            data['run_over_time'] = stmt.excluded.run_over_time
        if entry and entry.finished is not None:
            data['finished'] = stmt.excluded.finished
        stmt = stmt.on_conflict_do_update(
            constraint=cls.checker_results_unique_1,
            set_=data
        )
        return stmt


class CheckerResultLite:
    def __init__(self, team_id: int, service_id: int, round: int, status: str, run_over_time: bool = False,
                 message: str = '') -> None:
        self.team_id: int = team_id
        self.service_id: int = service_id
        self.round: int = round
        self.status: str = status
        self.run_over_time: bool = run_over_time
        self.message: str = message

    @classmethod
    def efficient_insert(cls, items) -> None:
        if len(items) == 0:
            return
        cursor = db_session().connection().connection.cursor()
        sql = f'INSERT INTO {CheckerResult.__tablename__} (team_id, service_id, round, status, run_over_time, message, celery_id) ' + \
              'SELECT unnest(%(team_id)s) , unnest(%(service_id)s), unnest(%(round)s), unnest(%(status)s), ' \
              'unnest(%(run_over_time)s), unnest(%(message)s), \'\''
        cursor.execute(sql, {
            'team_id': [x.team_id for x in items],
            'service_id': [x.service_id for x in items],
            'round': [x.round for x in items],
            'status': [x.status for x in items],
            'run_over_time': [x.run_over_time for x in items],
            'message': [x.message for x in items],
        })


class LogMessage(Base, Serializer, ModelMixin):
    """
    Collected log information from all the pages
    """
    __tablename__ = 'logmessages'
    id = Column(Integer, primary_key=True)
    created = Column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    component = Column(String(128), nullable=False)
    level = Column(SmallInteger, server_default=text('0'))
    title = Column(String)
    text = Column(String)

    # Log levels (higher = more important)
    DEBUG = 1
    INFO = 5
    IMPORTANT = 10  # for example: "new round starts here"
    NOTIFICATION = 15  # for example: "first blood"
    WARNING = 20
    ERROR = 30

    LEVELS = ['ERROR', 'WARNING', 'NOTIFICATION', 'IMPORTANT', 'INFO', 'DEBUG']

    query: 'Query[LogMessage]'


class CheckerFilesystem(Base, ModelMixin):
    """
    One line for each file/folder in a package. Files are identified by their hash.
    """
    __tablename__ = 'checker_filesystem'
    id = Column(Integer, primary_key=True)
    package = Column(String(32), nullable=False, index=True)
    path = Column(String, nullable=False)
    file_hash = Column(String(32), nullable=True)  # NULL = folder
    __table_args__ = (UniqueConstraint('package', 'path', name='checker_filesystem_unique_1'),)

    query: 'Query[CheckerFilesystem]'


class CheckerFile(Base, ModelMixin):
    """
    Files in a package.
    """
    __tablename__ = 'checker_files'
    id = Column(Integer, primary_key=True)
    file_hash = Column(String(32), nullable=False, index=True)
    content = Column(LargeBinary, nullable=False)
    __table_args__ = (UniqueConstraint('file_hash', name='checker_files_unique_1'),)

    query: 'Query[CheckerFile]'


T = typing.TypeVar('T')


def expect(x: T | None) -> T:
    if not x:
        raise Exception('Missing object')
    return x
