"""Server-side session management.

Sessions are created here with a cryptographically random ID so that
callers cannot guess or enumerate other users' sessions.
"""
import secrets
from fastapi import APIRouter, Depends, Request
from app.security import require_api_key

router = APIRouter(prefix="/sessions", tags=["sessions"])

SESSION_TTL = 7200  # 2 hours


@router.post("", dependencies=[Depends(require_api_key)])
async def create_session(request: Request) -> dict:
    """Generate a new session ID and register it in Redis.

    The client must use the returned session_id for all subsequent
    upload, pipeline, and result calls.
    """
    session_id = secrets.token_urlsafe(32)
    await request.app.state.redis.set(
        f"session:{session_id}:created", "1", ex=SESSION_TTL
    )
    return {"session_id": session_id}
