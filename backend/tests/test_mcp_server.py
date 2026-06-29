"""Tests for MCP server tools (unit-level — no real HTTP calls)."""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── Helpers ────────────────────────────────────────────────────────────────────

def _mock_response(data: dict, status: int = 200):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = data
    m.raise_for_status = MagicMock()
    return m


# ── create_session ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_create_session_returns_id():
    from mcp_server.server import create_session

    with patch("mcp_server.server.httpx.AsyncClient") as MockClient:
        mock_resp = _mock_response({"session_id": "abc-123"})
        MockClient.return_value.__aenter__.return_value.post = AsyncMock(return_value=mock_resp)
        result = await create_session()
        data = json.loads(result)
        assert data["session_id"] == "abc-123"


# ── get_stories ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_get_stories_done_session():
    from mcp_server.server import get_stories

    payload = {
        "ready": True,
        "status": "done",
        "user_stories": [{"id": "US-1", "title": "Login"}],
    }
    with patch("mcp_server.server.httpx.AsyncClient") as MockClient:
        mock_resp = _mock_response(payload)
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        result = await get_stories("my-session")
        stories = json.loads(result)
        assert len(stories) == 1
        assert stories[0]["title"] == "Login"


@pytest.mark.asyncio
async def test_mcp_get_stories_not_ready():
    from mcp_server.server import get_stories

    payload = {"ready": False, "status": "running"}
    with patch("mcp_server.server.httpx.AsyncClient") as MockClient:
        mock_resp = _mock_response(payload)
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        result = await get_stories("my-session")
        data = json.loads(result)
        assert "error" in data


# ── get_gap_report ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_get_gap_report_done_session():
    from mcp_server.server import get_gap_report

    gap = {"conflicts": [], "gaps": [], "coverage_score": 0.85, "summary": "Good"}
    payload = {"ready": True, "status": "done", "gap_report": gap}
    with patch("mcp_server.server.httpx.AsyncClient") as MockClient:
        mock_resp = _mock_response(payload)
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        result = await get_gap_report("my-session")
        data = json.loads(result)
        assert data["coverage_score"] == 0.85


# ── get_pipeline_status ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_get_pipeline_status():
    from mcp_server.server import get_pipeline_status

    payload = {"ready": True, "status": "done"}
    with patch("mcp_server.server.httpx.AsyncClient") as MockClient:
        mock_resp = _mock_response(payload)
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        result = await get_pipeline_status("my-session")
        data = json.loads(result)
        assert data["status"] == "done"
        assert data["ready"] is True


# ── list_sessions ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_list_sessions():
    from mcp_server.server import list_sessions

    history = [{"session_id": "s1", "status": "done"}, {"session_id": "s2", "status": "running"}]
    with patch("mcp_server.server.httpx.AsyncClient") as MockClient:
        mock_resp = _mock_response({"history": history})
        MockClient.return_value.__aenter__.return_value.get = AsyncMock(return_value=mock_resp)
        result = await list_sessions()
        data = json.loads(result)
        assert len(data) == 2


# ── Auth middleware ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mcp_auth_middleware_rejects_bad_key():
    import os
    from unittest.mock import patch as upatch
    from starlette.testclient import TestClient

    with upatch.dict(os.environ, {"MCP_API_KEY": "secret", "APP_API_KEY": "secret"}):
        # Re-import to pick up env
        import importlib
        import mcp_server.server as srv
        importlib.reload(srv)

        client = TestClient(srv.sse_app, raise_server_exceptions=False)
        resp = client.get("/sse", headers={"x-api-key": "wrong"})
        assert resp.status_code == 401


@pytest.mark.asyncio
async def test_mcp_auth_middleware_allows_correct_key():
    import os
    from unittest.mock import patch as upatch
    from starlette.testclient import TestClient

    with upatch.dict(os.environ, {"MCP_API_KEY": "secret", "APP_API_KEY": "secret"}):
        import importlib
        import mcp_server.server as srv
        importlib.reload(srv)

        client = TestClient(srv.sse_app, raise_server_exceptions=False)
        # SSE endpoint streams — we just check it doesn't 401
        resp = client.get("/sse", headers={"x-api-key": "secret"})
        assert resp.status_code != 401
