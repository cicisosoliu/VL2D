from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine

from vl2d.config import Settings, get_settings
from vl2d.models import Base

_engines: dict[str, Engine] = {}
_sessionmakers: dict[str, sessionmaker[Session]] = {}


def get_engine(settings: Settings | None = None) -> Engine:
    settings = settings or get_settings()
    if settings.database_url not in _engines:
        engine = create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            future=True,
        )

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record) -> None:  # type: ignore[no-untyped-def]
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

        _engines[settings.database_url] = engine
    return _engines[settings.database_url]


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    settings = settings or get_settings()
    if settings.database_url not in _sessionmakers:
        _sessionmakers[settings.database_url] = sessionmaker(
            bind=get_engine(settings),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )
    return _sessionmakers[settings.database_url]


def init_db(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    settings.ensure_dirs()
    engine = get_engine(settings)
    Base.metadata.create_all(bind=engine)
    with engine.begin() as connection:
        connection.execute(text("PRAGMA journal_mode=WAL"))


def get_db() -> Generator[Session, None, None]:
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_db_caches() -> None:
    for engine in _engines.values():
        engine.dispose()
    _engines.clear()
    _sessionmakers.clear()

