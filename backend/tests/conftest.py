"""Test configuration.

Engine tests are pure. API and scenario tests use the `mesh_test` database in the compose
Postgres (localhost:5434), migrated once per session as the owner and truncated + re-seeded
before each test. The app itself connects as the restricted `mesh_app` role, as in prod.
"""

import os

TEST_DB_APP = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://mesh_app:mesh_app@localhost:5434/mesh_test"
)
TEST_DB_OWNER = os.environ.get(
    "TEST_MIGRATION_DATABASE_URL", "postgresql+psycopg://mesh:mesh@localhost:5434/mesh_test"
)
os.environ["DATABASE_URL"] = TEST_DB_APP
os.environ["MIGRATION_DATABASE_URL"] = TEST_DB_OWNER
os.environ.setdefault("JWT_SECRET", "test-secret-not-for-production-0123456789abcdef")
os.environ["WORKER_ENABLED"] = "false"
os.environ["DEMO_MODE"] = "true"

from collections.abc import Iterator  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import Engine, create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

import app.models  # noqa: E402, F401
from app.core import db  # noqa: E402
from app.core.ratelimit import login_by_email, login_by_ip  # noqa: E402


@pytest.fixture(scope="session")
def migrated() -> Iterator[None]:
    from alembic import command
    from alembic.config import Config

    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option(
        "script_location", os.path.join(os.path.dirname(__file__), "..", "migrations")
    )
    cfg.attributes["url"] = TEST_DB_OWNER
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(scope="session")
def app_engine(migrated: None) -> Iterator[Engine]:
    engine = create_engine(TEST_DB_APP, pool_pre_ping=True)
    db.set_engine(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def owner_engine(migrated: None) -> Iterator[Engine]:
    engine = create_engine(TEST_DB_OWNER)
    yield engine
    engine.dispose()


@pytest.fixture
def fresh_db(app_engine: Engine, owner_engine: Engine) -> Engine:
    """Empty database plus the base seed (members A-F, users, rates, balances, window)."""
    from app.modules.demo.seed import seed, truncate_all

    with Session(owner_engine) as s, s.begin():
        truncate_all(s)
    with Session(app_engine) as s, s.begin():
        seed(s)
    login_by_ip.reset()
    login_by_email.reset()
    return app_engine


@pytest.fixture
def session(fresh_db: Engine) -> Iterator[Session]:
    with Session(fresh_db, expire_on_commit=False) as s:
        yield s
