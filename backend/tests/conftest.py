"""Shared pytest fixtures.

Every test runs against a throwaway SQLite file and a temporary storage
directory so the suite never touches a developer's working database.

The environment is configured at *import* time rather than in a fixture:
pytest imports this file first, but test modules import ``app.core.config`` at
module level during collection. A fixture would run too late, so ``settings``
would already have been built from the developer's own ``.env``.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

_TMP_ROOT = Path(tempfile.mkdtemp(prefix="medbill-tests-"))

os.environ["MEDBILL_DATABASE_URL"] = f"sqlite:///{(_TMP_ROOT / 'test.db').as_posix()}"
os.environ["MEDBILL_STORAGE_DIR"] = str(_TMP_ROOT / "storage")
os.environ["MEDBILL_DEMO_MODE"] = "true"
os.environ["MEDBILL_SEED_DEMO_BENCHMARKS"] = "true"
os.environ["MEDBILL_AI_PROVIDER"] = "demo"
os.environ["MEDBILL_RATE_LIMIT_ENABLED"] = "false"
# Keep the suite independent of any developer API key or .env leftovers.
os.environ.pop("MEDBILL_AI_API_KEY", None)
os.environ.pop("MEDBILL_AI_BASE_URL", None)


@pytest.fixture(scope="session", autouse=True)
def isolated_database_url() -> str:
    """Fail loudly if the suite ever ends up pointed at a real database."""
    url = os.environ["MEDBILL_DATABASE_URL"]
    assert _TMP_ROOT.name in url, f"tests must not use {url}"
    return url


@pytest.fixture(scope="session")
def session_factory():
    from app.db.session import SessionLocal, init_db

    init_db()
    return SessionLocal


@pytest.fixture()
def db(session_factory):
    """A session that is rolled back after every test."""
    from app.models import Base

    session = session_factory()
    try:
        yield session
        session.rollback()
    finally:
        session.close()
    # Keep the schema; drop rows written by the test.
    session = session_factory()
    try:
        for table in reversed(Base.metadata.sorted_tables):
            session.execute(table.delete())
        session.commit()
    finally:
        session.close()


@pytest.fixture(scope="session")
def seeded_benchmarks(session_factory):
    from app.services.seeding import seed_benchmarks

    with session_factory() as session:
        seed_benchmarks(session)
    return True


@pytest.fixture()
def client(seeded_benchmarks):
    """A TestClient with the lifespan run (schema + demo dataset)."""
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client
