"""Tests for POST /pipeline/run and GET /pipeline/stream."""
import json
import pytest
from unittest.mock import patch, MagicMock
from .conftest import seed_session

SAMPLE_TRANSCRIPTS = ["User: We need a login page. PM: Agreed, high priority."]
SAMPLE_RESULT = {
    "session_id": "test-session",
    "user_stories": [
        {
            "id": "US-1",
            "type": "story",
            "title": "User login",
            "description": "As a user I want to log in.",
            "acceptance_criteria": [],
            "system_tags": ["auth"],
            "feature_tags": ["login"],
            "priority": "high",
        }
    ],
    "extracted_intents": [{"id": "I-1", "type": "feature", "title": "Login page"}],
    "gap_report": {"conflicts": [], "gaps": [], "coverage_score": 0.9, "summary": "Good"},
    "evaluation_scores": {
        "ac_completeness_pct": 80,
        "feature_tag_f1": 0.9,
        "conflict_detection_f1": 0.8,
        "clarity_score": 4.0,
        "feasibility_score": 4.5,
        "traceability_score": 4.0,
        "overall_score": 4.2,
        "feedback": "Good quality stories.",
    },
    "audit_log": [],
    "retry_count": 0,
    "halt_reason": "",
    "progress": [{"agent": "story_writer", "status": "done", "timestamp": "2026-01-01T00:00:00Z"}],
}


@pytest.mark.asyncio
async def test_run_pipeline_starts(client, fake_redis):
    session_id = await seed_session(client, fake_redis, transcripts=SAMPLE_TRANSCRIPTS)
    with patch("app.api.routes.pipeline.asyncio.create_task"):
        resp = await client.post(f"/pipeline/run/{session_id}", json={})
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


@pytest.mark.asyncio
async def test_run_pipeline_requires_transcripts(client, fake_redis):
    session_id = await seed_session(client, fake_redis)  # no transcripts
    resp = await client.post(f"/pipeline/run/{session_id}", json={})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_run_pipeline_unknown_session(client):
    resp = await client.post("/pipeline/run/no-such-session-abc123", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_results_pending_before_pipeline(client, fake_redis):
    session_id = await seed_session(client, fake_redis, transcripts=SAMPLE_TRANSCRIPTS)
    resp = await client.get(f"/results/{session_id}")
    assert resp.status_code == 200
    assert resp.json()["ready"] is False


@pytest.mark.asyncio
async def test_results_available_after_pipeline(client, fake_redis):
    session_id = await seed_session(client, fake_redis, transcripts=SAMPLE_TRANSCRIPTS)
    ttl = 7 * 24 * 3600
    result = {**SAMPLE_RESULT, "session_id": session_id}
    fake_redis.set(f"session:{session_id}:result".encode(), json.dumps(result).encode(), ex=ttl)
    fake_redis.set(f"session:{session_id}:status".encode(), b"done", ex=ttl)

    resp = await client.get(f"/results/{session_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ready"] is True
    assert len(data["user_stories"]) == 1
    assert data["user_stories"][0]["title"] == "User login"


@pytest.mark.asyncio
async def test_results_excludes_prompt_traces(client, fake_redis):
    session_id = await seed_session(client, fake_redis, transcripts=SAMPLE_TRANSCRIPTS)
    ttl = 7 * 24 * 3600
    result = {**SAMPLE_RESULT, "session_id": session_id, "prompt_traces": ["SECRET"]}
    fake_redis.set(f"session:{session_id}:result".encode(), json.dumps(result).encode(), ex=ttl)
    fake_redis.set(f"session:{session_id}:status".encode(), b"done", ex=ttl)

    resp = await client.get(f"/results/{session_id}")
    assert "prompt_traces" not in resp.json()


@pytest.mark.asyncio
async def test_results_export_json(client, fake_redis):
    session_id = await seed_session(client, fake_redis, transcripts=SAMPLE_TRANSCRIPTS)
    ttl = 7 * 24 * 3600
    result = {**SAMPLE_RESULT, "session_id": session_id}
    fake_redis.set(f"session:{session_id}:result".encode(), json.dumps(result).encode(), ex=ttl)
    fake_redis.set(f"session:{session_id}:status".encode(), b"done", ex=ttl)

    resp = await client.get(f"/results/{session_id}/export?format=json")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_results_export_markdown(client, fake_redis):
    session_id = await seed_session(client, fake_redis, transcripts=SAMPLE_TRANSCRIPTS)
    ttl = 7 * 24 * 3600
    result = {**SAMPLE_RESULT, "session_id": session_id}
    fake_redis.set(f"session:{session_id}:result".encode(), json.dumps(result).encode(), ex=ttl)
    fake_redis.set(f"session:{session_id}:status".encode(), b"done", ex=ttl)

    resp = await client.get(f"/results/{session_id}/export?format=markdown")
    assert resp.status_code == 200
    assert "text/markdown" in resp.headers["content-type"]
