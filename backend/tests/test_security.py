"""Tests for API key enforcement and session ID validation."""
import pytest
from httpx import AsyncClient, ASGITransport
from app.config import get_settings
from .conftest import _make_app


async def _post_session(app, headers=None):
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers=headers or {},
        ) as c:
            return await c.post("/sessions")


@pytest.mark.asyncio
async def test_no_api_key_config_allows_all_requests(fake_redis):
    app = _make_app(fake_redis)
    resp = await _post_session(app)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401(fake_redis):
    app = _make_app(fake_redis, extra_env={"APP_API_KEY": "correct-key"})
    resp = await _post_session(app, headers={"X-Api-Key": "wrong-key"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_correct_api_key_returns_200(fake_redis):
    app = _make_app(fake_redis, extra_env={"APP_API_KEY": "correct-key"})
    resp = await _post_session(app, headers={"X-Api-Key": "correct-key"})
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_missing_api_key_header_returns_401(fake_redis):
    app = _make_app(fake_redis, extra_env={"APP_API_KEY": "correct-key"})
    resp = await _post_session(app)
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
