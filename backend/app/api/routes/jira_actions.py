"""Human-in-the-loop Jira write-back.

The frontend sends only the story IDs the human explicitly approved.
project_key is always taken from server-side config — the client cannot
override it, preventing cross-project ticket injection.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.config import get_settings
from app.security import require_api_key
from app.tools.jira_writer import create_jira_issue

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/jira",
    tags=["jira"],
    dependencies=[Depends(require_api_key)],
)


class CreateStoriesRequest(BaseModel):
    approved_story_ids: list[str]


async def _validate_session(session_id: str, request: Request) -> None:
    if not get_settings().session_id_is_valid(session_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session ID format.")
    exists = await request.app.state.redis.exists(f"session:{session_id}:created")
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")


def _build_evidence(story: dict, intents: list[dict]) -> list[dict]:
    intent_ids = story.get("source_intent_ids", [])
    if not intent_ids:
        transcript = story.get("source_transcript", "")
        return [i for i in intents if i.get("source_transcript") == transcript or not transcript][:3]
    intent_map = {i.get("id"): i for i in intents}
    return [intent_map[iid] for iid in intent_ids if iid in intent_map]


@router.post("/create-stories/{session_id}")
async def create_stories_in_jira(
    session_id: str,
    body: CreateStoriesRequest,
    request: Request,
) -> dict:
    await _validate_session(session_id, request)

    if not body.approved_story_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No story IDs provided.")

    r = request.app.state.redis
    result_raw = await r.get(f"session:{session_id}:result")
    if not result_raw:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session result not found.")

    result      = json.loads(result_raw)
    all_stories = result.get("user_stories", [])
    all_intents = result.get("extracted_intents", [])

    approved = {s["id"]: s for s in all_stories if s.get("id") in body.approved_story_ids}
    if not approved:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="None of the provided story IDs match this session.")

    # project_key always comes from server config — never from client input
    project_key = get_settings().jira_project_key

    created: list[dict] = []
    failed:  list[dict] = []

    for story_id in body.approved_story_ids:
        story = approved.get(story_id)
        if not story:
            continue
        try:
            ticket = await create_jira_issue(
                story=story,
                evidence=_build_evidence(story, all_intents),
                project_key=project_key,
            )
            created.append(ticket)
            logger.info("Jira ticket created: %s (session %s)", ticket.get("key"), session_id)
        except Exception as exc:
            logger.error("Jira ticket creation failed for story %s: %s", story_id, exc)
            failed.append({"story_id": story_id, "error": str(exc)})

    existing_raw = await r.get(f"session:{session_id}:jira_tickets")
    existing = json.loads(existing_raw) if existing_raw else []
    existing.extend(created)
    await r.set(f"session:{session_id}:jira_tickets", json.dumps(existing), ex=86400)

    return {
        "session_id":    session_id,
        "created":       created,
        "failed":        failed,
        "total_created": len(created),
    }


@router.get("/tickets/{session_id}")
async def get_created_tickets(session_id: str, request: Request) -> dict:
    await _validate_session(session_id, request)
    raw = await request.app.state.redis.get(f"session:{session_id}:jira_tickets")
    return {"session_id": session_id, "tickets": json.loads(raw) if raw else []}
