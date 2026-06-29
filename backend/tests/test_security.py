"""Tests for API key enforcement and session ID validation."""
import pytest
from contextlib import asynccontextmanager
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from app.config import get_settings


def _make_app(fake_redis, api_key: str = ""):
    from app.main import create_app

    env = {"APP_API_KEY": api_key} if api_key else {}
    with patch.dict("os.environ", env):
        get_settings.cache_clear()
        app = create_app()

    @asynccontextmanager
    async def _lifespan(app):
        app.state.redis = fake_redis
        yield

    app.router.lifespan_context = _lifespan
    get_settings.cache_clear()
    return app


@pytest.mark.asyncio
async def test_no_api_key_config_allows_all_requests(fake_redis):
    app = _make_app(fake_redis, api_key="")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/sessions")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401(fake_redis):
    app = _make_app(fake_redis, api_key="correct-key")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Api-Key": "wrong-key"},
    ) as c:
        resp = await c.post("/sessions")
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_correct_api_key_returns_200(fake_redis):
    app = _make_app(fake_redis, api_key="correct-key")
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-Api-Key": "correct-key"},
    ) as c:
        resp = await c.post("/sessions")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_missing_api_key_header_returns_401(fake_redis):
    app = _make_app(fake_redis, api_key="correct-key")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/sessions")
        assert resp.status_code == 401


def test_session_id_valid_format():
    get_settings.cache_clear()
    s = get_settings()
    assert s.session_id_is_valid("abc12345") is True
    assert s.session_id_is_valid("ABC-xyz_1234567890") is True


def test_session_id_rejects_short():
    s = get_settings()
    assert s.session_id_is_valid("abc") is False


def test_session_id_rejects_path_traversal():
    s = get_settings()
    assert s.session_id_is_valid("../../etc/passwd") is False
    assert s.session_id_is_valid("session/../admin") is False


def test_session_id_rejects_special_chars():
    s = get_settings()
    assert s.session_id_is_valid("hello world") is False
    assert s.session_id_is_valid("id;DROP TABLE") is False
