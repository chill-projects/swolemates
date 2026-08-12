"""Test fixtures.

Tests run against a real Postgres — the same engine as production — in a separate
`_test` database that is migrated with Alembic on every run. Migrating rather than
calling create_all() means CI exercises the migration path, which is the thing that
must not break during a blue-green deploy.

DATABASE_URL must point at a running Postgres: `make db` locally, a service container
in CI.
"""

import os
import pathlib
from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

TEST_USER = "test_user_alice"
OTHER_USER = "test_user_bob"


BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _admin_database_url() -> str:
    """Where to connect to create the test database.

    Read through Settings rather than os.environ so this works from `make test` (which
    relies on backend/.env, written by `make db`) as well as from CI (a plain env var).
    """
    from app.config import get_settings

    url = get_settings().normalize_database_url()
    if "://" not in url or url.rsplit("/", 1)[-1].partition("?")[0] == "":
        pytest.exit("DATABASE_URL is not usable. Run `make db` first, or see SETUP.md.", 1)
    return url


def _derive_test_url(base: str) -> str:
    url, _, query = base.partition("?")
    dbname = url.rstrip("/").rsplit("/", 1)[-1]
    if not dbname.endswith("_test"):
        url = url.rstrip("/").rsplit("/", 1)[0] + f"/{dbname}_test"
    return url + (f"?{query}" if query else "")


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> str:
    """Create and migrate a dedicated test database once per session.

    Migrating rather than create_all() means every run exercises the same path Railway's
    pre-deploy step takes, so a broken migration fails here rather than mid-deploy.
    """
    from app.config import get_settings

    admin_url = _admin_database_url()
    test_url = _derive_test_url(admin_url)
    dbname = test_url.partition("?")[0].rsplit("/", 1)[-1]

    admin = create_engine(admin_url)
    with admin.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{dbname}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    admin.dispose()

    os.environ["DATABASE_URL"] = test_url
    os.environ["ENVIRONMENT"] = "test"
    get_settings.cache_clear()

    command.upgrade(Config(str(BACKEND_ROOT / "alembic.ini")), "head")
    return test_url


@pytest.fixture
async def session(migrated_database: str) -> AsyncIterator[AsyncSession]:
    """A session rolled back after each test, so tests never see each other's rows."""
    engine = create_async_engine(
        migrated_database, poolclass=None, connect_args={"options": "-c timezone=utc"}
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
        await s.rollback()
    await engine.dispose()


@pytest.fixture
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An HTTP client wired to the app, authenticated as TEST_USER."""
    from app.auth import Principal, require_principal, require_user
    from app.db import get_session
    from app.main import app

    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[require_user] = lambda: TEST_USER
    app.dependency_overrides[require_principal] = lambda: Principal(sub=TEST_USER, claims={})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
