"""Tests for POST /sessions and GET /sessions/history."""
import pytest


@pytest.mark.asyncio
async def test_create_session_returns_id(client):
    resp = await client.post("/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert "session_id" in data
    assert len(data["session_id"]) >= 8


@pytest.mark.asyncio
async def test_create_session_id_is_unique(client):
    ids = {(await client.post("/sessions")).json()["session_id"] for _ in range(5)}
    assert len(ids) == 5


@pytest.mark.asyncio
async def test_session_registered_in_redis(client, fake_redis):
    resp = await client.post("/sessions")
    session_id = resp.json()["session_id"]
    exists = await fake_redis.exists(f"session:{session_id}:created")
    assert exists == 1


@pytest.mark.asyncio
async def test_history_empty_at_start(client):
    resp = await client.get("/sessions/history")
    assert resp.status_code == 200
    assert resp.json()["history"] == []


@pytest.mark.asyncio
async def test_history_contains_created_sessions(client):
    await client.post("/sessions")
    await client.post("/sessions")
    resp = await client.get("/sessions/history")
    assert resp.status_code == 200
    assert len(resp.json()["history"]) == 2


@pytest.mark.asyncio
async def test_history_entry_has_required_fields(client):
    await client.post("/sessions")
    entry = (await client.get("/sessions/history")).json()["history"][0]
    assert "session_id" in entry
    assert "created_at" in entry
    assert "status" in entry


@pytest.mark.asyncio
async def test_api_key_required_when_configured(fake_redis):
    """Without the key header the endpoint must return 401."""
    from httpx import AsyncClient, ASGITransport
    from .conftest import _make_app

    app = _make_app(fake_redis, extra_env={"APP_API_KEY": "test-secret"})
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as unauthed:
            resp = await unauthed.post("/sessions")
            assert resp.status_code == 401
