import json
from pathlib import Path
import httpx
from app.config import get_settings

MOCK_TICKETS_PATH = Path(__file__).parent.parent / "data" / "mock_tickets.json"


def load_mock_tickets() -> list[dict]:
    if MOCK_TICKETS_PATH.exists():
        return json.loads(MOCK_TICKETS_PATH.read_text())
    return [
        {
            "id": "PROJ-1",
            "type": "story",
            "title": "User authentication via SSO",
            "description": "Implement SAML-based SSO for enterprise users",
            "status": "in-progress",
            "tags": ["auth", "enterprise"],
        },
        {
            "id": "PROJ-2",
            "type": "bug",
            "title": "Dashboard loads slowly for large datasets",
            "description": "Performance degradation when dataset exceeds 10k rows",
            "status": "open",
            "tags": ["performance", "dashboard"],
        },
        {
            "id": "PROJ-3",
            "type": "epic",
            "title": "Reporting Module",
            "description": "Build reporting and export capabilities",
            "status": "backlog",
            "tags": ["reporting"],
        },
    ]


async def fetch_jira_tickets(project_key: str) -> list[dict]:
    settings = get_settings()
    if not settings.jira_base_url or not settings.jira_email or not settings.jira_token:
        raise ValueError("Jira credentials not configured (JIRA_BASE_URL, JIRA_EMAIL, JIRA_TOKEN required)")
    url = f"{settings.jira_base_url}/rest/api/3/search"
    # Jira Cloud uses Basic Auth: email + API token (same as jira_writer.py)
    auth = (settings.jira_email, settings.jira_token)
    params = {"jql": f"project={project_key} ORDER BY created DESC", "maxResults": 100,
              "fields": "summary,description,issuetype,status,labels,priority"}
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params, auth=auth)
        resp.raise_for_status()
        issues = resp.json().get("issues", [])
    return [
        {
            "id": i["key"],
            "type": i["fields"]["issuetype"]["name"].lower(),
            "title": i["fields"]["summary"],
            "description": i["fields"].get("description") or "",
            "status": i["fields"]["status"]["name"],
            "priority": (i["fields"].get("priority") or {}).get("name", "medium").lower(),
            "tags": i["fields"].get("labels", []),
        }
        for i in issues
    ]


async def get_tickets(project_key: str | None = None) -> list[dict]:
    settings = get_settings()
    key = project_key or settings.jira_project_key or "PROJ"
    if settings.use_mock_backlog:
        return load_mock_tickets()
    return await fetch_jira_tickets(key)
