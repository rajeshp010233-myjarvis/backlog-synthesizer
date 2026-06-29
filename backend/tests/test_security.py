"""Tests for API key enforcement and session ID validation."""
import pytest
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport
from app.main import create_app
from app.config import get_settings


@pytest.mark.asyncio
async def test_no_api_key_config_allows_all_requests(client):
    """When APP_API_KEY is not set every request should pass through."""
    resp = await client.post("/sessions")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_wrong_api_key_returns_401():
    with patch.dict("os.environ", {"APP_API_KEY": "correct-key"}):
        get_settings.cache_clear()
        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Api-Key": "wrong-key"},
        ) as c:
            resp = await c.post("/sessions")
            assert resp.status_code == 401
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_correct_api_key_returns_200():
    with patch.dict("os.environ", {"APP_API_KEY": "correct-key"}):
        get_settings.cache_clear()
        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Api-Key": "correct-key"},
        ) as c:
            resp = await c.post("/sessions")
            assert resp.status_code == 200
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_missing_api_key_header_returns_401():
    with patch.dict("os.environ", {"APP_API_KEY": "correct-key"}):
        get_settings.cache_clear()
        app = create_app()
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            resp = await c.post("/sessions")
            assert resp.status_code == 401
        get_settings.cache_clear()


def test_session_id_valid_format():
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
