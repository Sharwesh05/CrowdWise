"""Database engine, session factory and declarative base."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import DateTime, TypeDecorator, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.core.config import settings


def _engine_kwargs() -> dict:
    if settings.is_sqlite:
        # check_same_thread=False so FastAPI's threadpool can share the connection;
        # SQLite is only ever the zero-infra dev/test fallback.
        return {"connect_args": {"check_same_thread": False}, "pool_pre_ping": True}
    return {"pool_pre_ping": True, "pool_size": 10, "max_overflow": 20}


engine = create_engine(settings.database_url, future=True, **_engine_kwargs())

if settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - trivial
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Timestamps that are always timezone-aware UTC, on every backend.

    PostgreSQL returns aware datetimes for TIMESTAMPTZ; SQLite (the dev/test
    fallback) returns naive ones. Normalising here means application code can
    subtract two timestamps without caring which database it is talking to.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class Base(DeclarativeBase):
    """Declarative base with created/updated timestamp helpers."""


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


@contextmanager
def advisory_lock(key: int) -> Iterator[bool]:
    """Hold an exclusive right to do something, across processes.

    Both the API and the `worker` container run the same background jobs, so a
    sweep that must not run twice at once needs a coordination point neither
    process owns. A `threading.Lock` cannot see another process; the database
    can.

    Yields False rather than waiting — the caller is competing with another
    worker that is already draining the same queue, so there is nothing to wait
    for. The lock is taken on a dedicated connection so the unlock is guaranteed
    to reach the session holding it: returning a connection to the pool resets it
    with ROLLBACK, which session-level advisory locks survive. Postgres releases
    them when the connection drops, so a killed worker cannot wedge the job.

    On SQLite — the test and zero-infra fallback, always single-process — this is
    a no-op that always grants.
    """
    if engine.dialect.name != "postgresql":
        yield True
        return

    conn = engine.connect()
    acquired = False
    try:
        acquired = bool(
            conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar()
        )
        yield acquired
    finally:
        if acquired:
            conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})
            conn.commit()
        conn.close()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def session_scope() -> Session:
    """Session for background workers and scripts (caller manages lifecycle)."""
    return SessionLocal()
