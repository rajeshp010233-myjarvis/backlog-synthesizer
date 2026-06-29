"""Shared pytest fixtures for all backend tests.

Uses fakeredis so no real Redis instance is needed during CI.
The FastAPI app is created fresh for each test session via the
standard httpx AsyncClient / TestClient pattern.
"""
import json
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient, ASGITransport

from app.main import create_app
from app.config import get_settings


# ── Fake Redis ─────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_redis():
    """In-memory dict-backed fake that covers the Redis commands we use."""
    import fakeredis.aioredis as fakeredis
    return fakeredis.FakeRedis(decode_responses=False)


# ── App + HTTP client ──────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(fake_redis):
    """Async HTTP client wired to the FastAPI app with a fake Redis."""
    app = create_app()
    app.state.redis = fake_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest_asyncio.fixture
async def authed_client(fake_redis):
    """Client with APP_API_KEY set — all requests carry the key header."""
    with patch.dict("os.environ", {"APP_API_KEY": "test-secret"}):
        # Bust the lru_cache so the patched env is picked up
        get_settings.cache_clear()
        app = create_app()
        app.state.redis = fake_redis

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Api-Key": "test-secret"},
        ) as ac:
            yield ac

        get_settings.cache_clear()


# ── Helpers ────────────────────────────────────────────────────────────────────

async def create_session(client) -> str:
    """Create a session and return its ID."""
    resp = await client.post("/sessions")
    assert resp.status_code == 200
    return resp.json()["session_id"]


async def seed_session(client, fake_redis, transcripts=None, wiki=None) -> str:
    """Create a session and pre-populate Redis with transcript/wiki data."""
    session_id = await create_session(client)
    ttl = 7 * 24 * 3600
    if transcripts is not None:
        await fake_redis.set(
            f"session:{session_id}:transcripts",
            json.dumps(transcripts).encode(),
            ex=ttl,
        )
    if wiki is not None:
        await fake_redis.set(
            f"session:{session_id}:wiki",
            json.dumps(wiki).encode(),
            ex=ttl,
        )
    return session_id
