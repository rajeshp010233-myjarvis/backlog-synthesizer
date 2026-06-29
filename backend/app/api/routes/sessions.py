"""Server-side session management.

Sessions are created here with a cryptographically random ID so that
callers cannot guess or enumerate other users' sessions.
"""
import json
import secrets
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Request
from app.security import require_api_key

router = APIRouter(prefix="/sessions", tags=["sessions"])

SESSION_TTL  = 7 * 24 * 3600   # 7 days — long enough to appear in history
HISTORY_KEY  = "history:entries"
HISTORY_MAX  = 50               # keep the most recent 50 runs


@router.post("", dependencies=[Depends(require_api_key)])
async def create_session(request: Request) -> dict:
    """Generate a new session ID and register it in Redis."""
    session_id = secrets.token_urlsafe(32)
    created_at = datetime.now(timezone.utc).isoformat()
    await request.app.state.redis.set(
        f"session:{session_id}:created", "1", ex=SESSION_TTL
    )
    # Seed the history entry — completed_at / stats filled in by pipeline
    entry = {
        "session_id":  session_id,
        "created_at":  created_at,
        "status":      "created",
    }
    r = request.app.state.redis
    await r.lpush(HISTORY_KEY, json.dumps(entry))
    await r.ltrim(HISTORY_KEY, 0, HISTORY_MAX - 1)
    return {"session_id": session_id}


@router.get("/history", dependencies=[Depends(require_api_key)])
async def get_history(request: Request) -> dict:
    """Return the most recent pipeline runs with summary metadata."""
    r = request.app.state.redis
    raw_entries = await r.lrange(HISTORY_KEY, 0, HISTORY_MAX - 1)
    entries = []
    for raw in raw_entries:
        try:
            entries.append(json.loads(raw))
        except Exception:
            pass
    return {"history": entries}
