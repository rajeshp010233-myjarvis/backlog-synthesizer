import json
import os
from pathlib import Path
import httpx


async def fetch_jira_tickets(project_key: str) -> list[dict]:
    base_url = os.getenv("JIRA_BASE_URL", "")
    token = os.getenv("JIRA_TOKEN", "")
    use_mock = os.getenv("USE_MOCK_BACKLOG", "true").lower() == "true"

    if not base_url or not token or use_mock:
        mock_path = Path(__file__).parent.parent / "data" / "mock_tickets.json"
        with open(mock_path) as f:
            tickets = json.load(f)
        return [t for t in tickets if t["id"].startswith(project_key)]

    url = f"{base_url}/rest/api/3/search"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    params = {"jql": f"project = {project_key} ORDER BY created DESC", "maxResults": 100}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()

    return [
        {
            "id": issue["key"],
            "type": issue["fields"]["issuetype"]["name"].lower(),
            "title": issue["fields"]["summary"],
            "description": issue["fields"].get("description") or "",
            "status": issue["fields"]["status"]["name"].lower(),
            "tags": [label for label in issue["fields"].get("labels", [])],
        }
        for issue in data.get("issues", [])
    ]


async def fetch_github_issues(owner: str, repo: str) -> list[dict]:
    token = os.getenv("GITHUB_TOKEN", "")
    url = f"https://api.github.com/repos/{owner}/{repo}/issues"
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params={"state": "open", "per_page": 100})
        resp.raise_for_status()
        issues = resp.json()

    return [
        {
            "id": f"GH-{issue['number']}",
            "title": issue["title"],
            "body": issue.get("body") or "",
            "state": issue["state"],
            "labels": [lbl["name"] for lbl in issue.get("labels", [])],
            "url": issue["html_url"],
        }
        for issue in issues
        if "pull_request" not in issue
    ]
