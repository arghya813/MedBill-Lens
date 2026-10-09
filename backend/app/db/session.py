"""Database engine and session management.

SQLite is used for local development. Nothing in the application is
SQLite-specific: swap ``DATABASE_URL`` for a PostgreSQL DSN and the models,
repositories and services continue to work unchanged.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    pass


def _build_engine() -> Engine:
    url = settings.database_url
    kwargs: dict = {"echo": settings.sql_echo, "future": True}
    if url.startswith("sqlite"):
        # check_same_thread=False is required by FastAPI's threadpool usage.
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)

    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, _record):  # pragma: no cover - driver glue
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.close()

    return engine


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create tables. Safe to call repeatedly."""
    from app import models  # noqa: F401  (import registers mappers)

    Base.metadata.create_all(bind=engine)
    _ensure_country_columns()


def _ensure_country_columns() -> None:
    """Backfill ``country`` columns on databases created before they existed.

    There is no migration framework in this project; new nullable-or-defaulted
    columns arrive here instead. Each statement is a no-op when the column is
    already present, so this is safe to run on every startup.
    """
    from sqlalchemy import text

    statements = (
        "ALTER TABLE benchmark_prices ADD COLUMN country_code VARCHAR(8) DEFAULT 'IN'",
        "ALTER TABLE bills ADD COLUMN country VARCHAR(8)",
    )
    with engine.begin() as connection:
        for statement in statements:
            try:
                connection.execute(text(statement))
            except Exception:  # noqa: BLE001 - column already exists
                continue
