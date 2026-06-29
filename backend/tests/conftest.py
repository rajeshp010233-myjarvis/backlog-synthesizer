"""Shared pytest fixtures for all backend tests.

Uses fakeredis so no real Redis instance is needed during CI.
"""
import json
import pytest
import pytest_asyncio
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport

from app.config import get_settings


# ── Fake Redis ─────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis():
    """Synchronous fakeredis instance that supports async commands."""
    try:
        import fakeredis
        return fakeredis.FakeRedis(decode_responses=False)
    except Exception:
        import fakeredis.aioredis as fakeredis_async
        return fakeredis_async.FakeRedis(decode_responses=False)


# ── App + HTTP client ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(fake_redis):
    """Async HTTP client wired to the FastAPI app with a fake Redis.

    We bypass the lifespan entirely by injecting fake_redis directly onto
    app.state before the first request, so tests never touch a real Redis.
    """
    from app.main import create_app

    app = create_app()

    # Inject fake redis BEFORE the lifespan tries to connect
    # We monkeypatch the lifespan to skip real Redis startup
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _test_lifespan(app):
        app.state.redis = fake_redis
        yield

    app.router.lifespan_context = _test_lifespan

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def authed_client(fake_redis):
    """Client with APP_API_KEY enforced."""
    from app.main import create_app
    from contextlib import asynccontextmanager

    with patch.dict("os.environ", {"APP_API_KEY": "test-secret"}):
        get_settings.cache_clear()

        app = create_app()

        @asynccontextmanager
        async def _test_lifespan(app):
            app.state.redis = fake_redis
            yield

        app.router.lifespan_context = _test_lifespan

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Api-Key": "test-secret"},
        ) as ac:
            yield ac

        get_settings.cache_clear()


# ── Helpers ────────────────────────────────────────────────────────────────────

async def create_session(client) -> str:
    resp = await client.post("/sessions")
    assert resp.status_code == 200, f"create_session failed: {resp.text}"
    return resp.json()["session_id"]


async def seed_session(client, fake_redis, transcripts=None, wiki=None) -> str:
    session_id = await create_session(client)
    ttl = 7 * 24 * 3600
    if transcripts is not None:
        fake_redis.set(
            f"session:{session_id}:transcripts".encode(),
            json.dumps(transcripts).encode(),
            ex=ttl,
        )
    if wiki is not None:
        fake_redis.set(
            f"session:{session_id}:wiki".encode(),
            json.dumps(wiki).encode(),
            ex=ttl,
        )
    return session_id
