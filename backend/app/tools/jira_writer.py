"""
Creates Jira issues from approved user stories.
Evidence (transcript source, speaker, quote, intent) is embedded
in each ticket description so traceability is preserved inside Jira.
"""
import httpx
from app.config import get_settings

PRIORITY_MAP = {"high": "High", "medium": "Medium", "low": "Low"}
TYPE_MAP = {"epic": "Epic", "story": "Story", "task": "Task", "bug": "Bug"}


def _adf_text(text: str) -> dict:
    return {"type": "text", "text": text}


def _adf_para(text: str) -> dict:
    return {"type": "paragraph", "content": [_adf_text(text)]}


def _adf_heading(text: str, level: int = 3) -> dict:
    return {"type": "heading", "attrs": {"level": level}, "content": [_adf_text(text)]}


def _adf_bullet(items: list[str]) -> dict:
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [{"type": "paragraph", "content": [_adf_text(item)]}],
            }
            for item in items
        ],
    }


def _build_adf(story: dict, evidence: list[dict]) -> dict:
    """Builds an ADF document with story details + source evidence section."""
    content = []

    # User story sentence
    content.append(_adf_para(story.get("description", "")))

    # Acceptance criteria
    ac_list = story.get("acceptance_criteria", [])
    if ac_list:
        content.append(_adf_heading("Acceptance Criteria"))
        for ac in ac_list:
            given = ac.get("given", "")
            when = ac.get("when", "")
            then = ac.get("then", "")
            content.append(_adf_para(f"Given {given}"))
            content.append(_adf_para(f"When {when}"))
            content.append(_adf_para(f"Then {then}"))
            edge_cases = ac.get("edge_cases", [])
            if edge_cases:
                content.append(_adf_para("Edge cases:"))
                content.append(_adf_bullet(edge_cases))

    # Tags
    tags = story.get("system_tags", []) + story.get("feature_tags", [])
    if tags:
        content.append(_adf_heading("Tags"))
        content.append(_adf_para(", ".join(tags)))

    # Source evidence — the traceability chain
    if evidence:
        content.append(_adf_heading("Source Evidence", level=2))
        content.append(_adf_para(
            "This story was synthesised from the following transcript extracts:"
        ))
        for ev in evidence:
            content.append(_adf_heading(
                f"Transcript: {ev.get('source_transcript', 'unknown')} "
                f"| Speaker: {ev.get('speaker_role', 'unknown')}",
                level=3,
            ))
            quote = ev.get("source_quote", "")
            if quote:
                content.append({
                    "type": "blockquote",
                    "content": [_adf_para(quote)],
                })
            content.append(_adf_para(
                f"Intent: [{ev.get('id', '')}] {ev.get('title', '')} "
                f"— {ev.get('type', '')} | Priority: {ev.get('priority', '')}"
            ))
            desc = ev.get("description", "")
            if desc:
                content.append(_adf_para(desc))

    return {"type": "doc", "version": 1, "content": content}


async def create_jira_issue(
    story: dict,
    evidence: list[dict],
    project_key: str,
) -> dict:
    """
    Creates a single Jira issue and returns:
    { story_id, jira_key, jira_url, status }
    """
    settings = get_settings()
    url = f"{settings.jira_base_url}/rest/api/3/issue"
    auth = (settings.jira_email, settings.jira_token)

    issue_type = TYPE_MAP.get(story.get("type", "story"), "Story")
    priority = PRIORITY_MAP.get(story.get("priority", "medium"), "Medium")
    adf_body = _build_adf(story, evidence)

    labels = (story.get("system_tags", []) + story.get("feature_tags", []))[:10]
    # Jira labels cannot contain spaces
    labels = [lbl.replace(" ", "_") for lbl in labels]

    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": story.get("title", "Untitled story"),
            "description": adf_body,
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
            "labels": labels,
        }
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(url, json=payload, auth=auth)
        resp.raise_for_status()
        data = resp.json()

    jira_key = data.get("key", "")
    jira_url = f"{settings.jira_base_url}/browse/{jira_key}"
    return {
        "story_id": story.get("id"),
        "jira_key": jira_key,
        "jira_url": jira_url,
        "status": "created",
    }
