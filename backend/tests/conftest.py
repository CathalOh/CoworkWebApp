from __future__ import annotations

import os
import tempfile

# Default: sqlite. Set TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app to run against Postgres
# (exercises partitions, the append-only trigger, pgvector and the advisory-locked hash chain).
os.environ.update({
    "ENV": "test", "DATABASE_URL": os.environ.get("TEST_DATABASE_URL") or ("sqlite+aiosqlite:///" + tempfile.mkdtemp() + "/test.db"),
    "REDIS_URL": "memory://",
    "AGENT_RUNTIME": "mock", "MODEL_PROVIDER": "mock", "AUTH_DEV_BYPASS": "true", "SANDBOX_BACKEND": "none",
    "WORKSPACES_ROOT": tempfile.mkdtemp(), "OBJECT_STORE_PATH": tempfile.mkdtemp(), "APPROVAL_TIMEOUT_SECONDS": "5",
"SECRET_KEY": "test-secret-key-0123456789abcdef", "RATE_LIMIT_PER_MINUTE": "100000",
})

import asyncio  # noqa: E402

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import get_engine, reset_engine  # noqa: E402
from app.models import Base  # noqa: E402
from app.orchestration.events import InMemoryEventBus, set_event_bus  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def _schema():
    get_settings.cache_clear()
    engine = get_engine()
    if engine.dialect.name == "postgresql":
        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        await asyncio.get_event_loop().run_in_executor(None, lambda: (command.downgrade(cfg, "base"), command.upgrade(cfg, "head")))
    else:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    from app.seed import seed

    await seed()
    yield
    await reset_engine()


@pytest.fixture(autouse=True)
def _bus():
    set_event_bus(InMemoryEventBus())


@pytest.fixture
async def app():
    from app.main import app as _app

    async with _app.router.lifespan_context(_app):
        yield _app


@pytest.fixture
async def client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def login(client: AsyncClient, email: str = "user@example.com", roles: list[str] | None = None) -> dict:
    r = await client.post("/v1/auth/dev-login", json={"email": email, "roles": roles or ["user"]})
    assert r.status_code == 200, r.text
    me = r.json()
    client.headers["X-CSRF-Token"] = me["csrf_token"]
    return me


@pytest.fixture
async def user_client(client):
    await login(client, "user@example.com")
    return client


@pytest.fixture
async def admin_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await login(c, "admin@example.com", ["org_admin", "developer"])
        yield c
