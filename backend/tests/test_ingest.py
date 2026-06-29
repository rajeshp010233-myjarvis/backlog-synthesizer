"""Tests for /ingest/* upload endpoints."""
import json
import pytest
from .conftest import create_session


def _txt_file(name: str, content: str = "Hello world transcript."):
    return ("files", (name, content.encode(), "text/plain"))


def _json_file(data: list):
    return ("file", ("backlog.json", json.dumps(data).encode(), "application/json"))


# ── Transcripts ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_transcript_txt(client, fake_redis):
    session_id = await create_session(client)
    resp = await client.post(
        f"/ingest/transcripts/{session_id}",
        files=[_txt_file("t1.txt")],
    )
    assert resp.status_code == 200
    stored = json.loads(await fake_redis.get(f"session:{session_id}:transcripts"))
    assert len(stored) == 1
    assert "Hello world" in stored[0]


@pytest.mark.asyncio
async def test_upload_multiple_transcripts(client, fake_redis):
    session_id = await create_session(client)
    resp = await client.post(
        f"/ingest/transcripts/{session_id}",
        files=[_txt_file("a.txt", "First"), _txt_file("b.txt", "Second")],
    )
    assert resp.status_code == 200
    stored = json.loads(await fake_redis.get(f"session:{session_id}:transcripts"))
    assert len(stored) == 2


@pytest.mark.asyncio
async def test_upload_invalid_extension_rejected(client):
    session_id = await create_session(client)
    resp = await client.post(
        f"/ingest/transcripts/{session_id}",
        files=[("files", ("evil.exe", b"bad", "application/octet-stream"))],
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_upload_unknown_session_returns_404(client):
    resp = await client.post(
        "/ingest/transcripts/nonexistent-session-id-12345",
        files=[_txt_file("t.txt")],
    )
    assert resp.status_code == 404


# ── Wiki ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_wiki_txt(client, fake_redis):
    session_id = await create_session(client)
    resp = await client.post(
        f"/ingest/wiki/{session_id}",
        files=[_txt_file("wiki.txt", "Product wiki page content.")],
    )
    assert resp.status_code == 200
    stored = json.loads(await fake_redis.get(f"session:{session_id}:wiki"))
    assert len(stored) >= 1


# ── Backlog ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_backlog_json(client, fake_redis):
    session_id = await create_session(client)
    tickets = [{"id": "T-1", "title": "Existing ticket", "type": "story"}]
    resp = await client.post(
        f"/ingest/backlog/{session_id}",
        files=[_json_file(tickets)],
    )
    assert resp.status_code == 200
    stored = json.loads(await fake_redis.get(f"session:{session_id}:tickets"))
    assert stored[0]["id"] == "T-1"


@pytest.mark.asyncio
async def test_upload_backlog_wrong_type_rejected(client):
    session_id = await create_session(client)
    resp = await client.post(
        f"/ingest/backlog/{session_id}",
        files=[_txt_file("backlog.txt")],
    )
    assert resp.status_code in (415, 422)  # 415 from ext check, 422 from FastAPI validation
