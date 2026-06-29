"""Pipeline orchestration routes."""
import json
import asyncio
import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agents.orchestrator import compiled_graph
from app.config import get_settings
from app.security import require_api_key
from app.tools.backlog_provider import get_tickets


def _user_friendly_error(exc: Exception) -> str:
    """Convert raw exceptions into short, actionable messages for the UI."""
    msg = str(exc)
    if "insufficient_quota" in msg or "quota exceeded" in msg.lower():
        return "LLM quota exceeded — add credits to your provider account, then try again."
    if "rate_limit" in msg.lower():
        return "LLM rate limit hit — please wait a moment and try again."
    if "authentication" in msg.lower() or "api key" in msg.lower() or "invalid key" in msg.lower():
        return "LLM API key is invalid — check your backend/.env configuration."
    if "timed out" in msg.lower():
        return "Pipeline timed out — try with fewer or shorter transcripts."
    # Cap raw messages so the UI doesn't overflow
    return msg[:200] if len(msg) > 200 else msg

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/pipeline",
    tags=["pipeline"],
    dependencies=[Depends(require_api_key)],
)

# SSE stream will stop after this many seconds regardless of pipeline state
SSE_TIMEOUT_SECONDS = 900  # 15 minutes


class AgentModelConfig(BaseModel):
    provider: str = "openai"
    model: str


class PipelineRunRequest(BaseModel):
    agent_model_configs: dict[str, AgentModelConfig] = Field(default_factory=dict)


async def _validate_session(session_id: str, request: Request) -> None:
    if not get_settings().session_id_is_valid(session_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session ID format.")
    exists = await request.app.state.redis.exists(f"session:{session_id}:created")
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")


@router.post("/run/{session_id}")
async def run_pipeline(
    session_id: str,
    request: Request,
    body: PipelineRunRequest = Body(default_factory=PipelineRunRequest),
) -> dict:
    await _validate_session(session_id, request)

    r = request.app.state.redis
    transcripts_raw = await r.get(f"session:{session_id}:transcripts")
    if not transcripts_raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No transcripts found for this session. Upload transcripts first.",
        )

    wiki_raw    = await r.get(f"session:{session_id}:wiki")
    tickets_raw = await r.get(f"session:{session_id}:tickets")

    # If no backlog file was uploaded, auto-fetch from Jira (or fall back to mock).
    if tickets_raw:
        existing_tickets = json.loads(tickets_raw)
        tickets_source = "uploaded_file"
    else:
        try:
            existing_tickets = await get_tickets()
            tickets_source = "jira_live" if not get_settings().use_mock_backlog else "mock"
            logger.info("session=%s — loaded %d ticket(s) from %s", session_id, len(existing_tickets), tickets_source)
        except Exception as exc:
            logger.warning("session=%s — backlog fetch failed (%s), proceeding with empty backlog", session_id, exc)
            existing_tickets = []
            tickets_source = "none"

    initial_state = {
        "session_id":          session_id,
        "transcript_texts":    json.loads(transcripts_raw),
        "wiki_texts":          json.loads(wiki_raw) if wiki_raw else [],
        "existing_tickets":    existing_tickets,
        "agent_model_configs": {k: v.model_dump() for k, v in body.agent_model_configs.items()},
        "audit_log":           [],
        "errors":              [],
        "progress":            [],
        "retry_count":         0,
        "evaluator_feedback":  "",
        "last_overall_score":  0.0,
        "prompt_traces":       [],
        "story_iterations":    [],
        "halt_reason":         "",
    }

    asyncio.create_task(_run_and_store(session_id, initial_state, request.app.state.redis))
    return {"session_id": session_id, "status": "started"}


async def _run_and_store(session_id: str, initial_state: dict, redis) -> None:
    from datetime import datetime, timezone
    from app.api.routes.sessions import HISTORY_KEY, HISTORY_MAX, SESSION_TTL

    settings   = get_settings()
    session_ttl = SESSION_TTL

    async def _update_history(patch: dict) -> None:
        """Find the session's history entry and merge patch fields into it."""
        raw_entries = await redis.lrange(HISTORY_KEY, 0, HISTORY_MAX - 1)
        for i, raw in enumerate(raw_entries):
            try:
                entry = json.loads(raw)
                if entry.get("session_id") == session_id:
                    entry.update(patch)
                    await redis.lset(HISTORY_KEY, i, json.dumps(entry))
                    return
            except Exception:
                pass

    try:
        await redis.set(f"session:{session_id}:status", "running", ex=session_ttl)
        await _update_history({"status": "running"})

        result = await asyncio.wait_for(
            asyncio.to_thread(compiled_graph.invoke, initial_state),
            timeout=settings.pipeline_timeout_seconds,
        )

        # Build timing summary from harness chain entries
        chain = [e for e in result.get("audit_log", []) if e.get("tool") == "harness_chain"]
        agent_timings = {e["agent"]: e.get("elapsed_s") for e in chain if e.get("agent")}
        total_elapsed = round(sum(e.get("elapsed_s", 0) for e in chain), 2)

        await redis.set(f"session:{session_id}:result", json.dumps(result), ex=session_ttl)
        await redis.set(f"session:{session_id}:status", "done", ex=session_ttl)

        await _update_history({
            "status":          "done",
            "completed_at":    datetime.now(timezone.utc).isoformat(),
            "story_count":     len(result.get("user_stories", [])),
            "intent_count":    len(result.get("extracted_intents", [])),
            "overall_score":   result.get("evaluation_scores", {}).get("overall_score"),
            "retry_count":     result.get("retry_count", 0),
            "total_elapsed_s": total_elapsed,
            "agent_timings":   agent_timings,
            "halt_reason":     result.get("halt_reason", ""),
        })
        logger.info("Pipeline completed for session %s", session_id)

    except asyncio.TimeoutError:
        msg = "Pipeline timed out — try with fewer or shorter transcripts."
        logger.error("Pipeline timed out for session %s after %ds", session_id, settings.pipeline_timeout_seconds)
        await redis.set(f"session:{session_id}:status", f"error:{msg}", ex=3600)
        await _update_history({"status": "error", "error": msg, "completed_at": datetime.now(timezone.utc).isoformat()})
    except Exception as exc:
        msg = _user_friendly_error(exc)
        logger.exception("Pipeline failed for session %s: %s", session_id, exc)
        await redis.set(f"session:{session_id}:status", f"error:{msg}", ex=3600)
        await _update_history({"status": "error", "error": msg, "completed_at": datetime.now(timezone.utc).isoformat()})


@router.get("/stream/{session_id}")
async def stream_progress(session_id: str, request: Request):
    await _validate_session(session_id, request)

    async def event_generator():
        r = request.app.state.redis
        last_len = 0
        elapsed = 0
        interval = 1

        while elapsed < SSE_TIMEOUT_SECONDS:
            status_raw = await r.get(f"session:{session_id}:status")
            current_status = (status_raw or b"pending").decode()

            result_raw = await r.get(f"session:{session_id}:result")
            if result_raw:
                progress = json.loads(result_raw).get("progress", [])
                for p in progress[last_len:]:
                    yield f"data: {json.dumps({'type': 'progress', 'payload': p})}\n\n"
                last_len = len(progress)

            if current_status == "done":
                yield f"data: {json.dumps({'type': 'done', 'session_id': session_id})}\n\n"
                return
            if current_status.startswith("error:"):
                yield f"data: {json.dumps({'type': 'error', 'message': current_status[6:]})}\n\n"
                return

            yield f"data: {json.dumps({'type': 'status', 'status': current_status})}\n\n"
            await asyncio.sleep(interval)
            elapsed += interval

        yield f"data: {json.dumps({'type': 'error', 'message': 'Stream timeout — check results endpoint.'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
