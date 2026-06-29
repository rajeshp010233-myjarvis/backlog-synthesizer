"""
MCP server exposing Jira/GitHub as resources and pipeline tools.

Run standalone:  python -m mcp_server.server
Or via SSE:      uvicorn mcp_server.server:sse_app --port 8002

Authentication
--------------
Set MCP_API_KEY in backend/.env (same value as APP_API_KEY).
Claude Desktop callers must pass:  x-api-key: <MCP_API_KEY>

Claude Desktop config (~/.config/claude/claude_desktop_config.json):
{
  "mcpServers": {
    "backlog-synthesizer": {
      "url": "http://localhost:8002/sse",
      "headers": { "x-api-key": "<MCP_API_KEY>" }
    }
  }
}
"""
import json
import os

import httpx
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Mount

from .resources import fetch_jira_tickets, fetch_github_issues

BACKEND_URL   = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", os.getenv("APP_API_KEY", ""))
MCP_API_KEY   = os.getenv("MCP_API_KEY",   os.getenv("APP_API_KEY", ""))


def _backend_headers() -> dict:
    """Headers required to call the secured backend REST API."""
    h = {"Content-Type": "application/json"}
    if BACKEND_API_KEY:
        h["X-Api-Key"] = BACKEND_API_KEY
    return h


# ── Auth middleware ────────────────────────────────────────────────────────────

class ApiKeyMiddleware(BaseHTTPMiddleware):
    """Reject requests that don't carry the correct x-api-key header.

    Health-check path (/health) is always allowed so load-balancers can probe.
    When MCP_API_KEY is empty the server runs unauthenticated (dev/local only).
    """
    async def dispatch(self, request: Request, call_next):
        if not MCP_API_KEY:
            return await call_next(request)
        if request.url.path in ("/health",):
            return await call_next(request)
        incoming = request.headers.get("x-api-key", "")
        if incoming != MCP_API_KEY:
            return Response("Unauthorized", status_code=401)
        return await call_next(request)


# ── MCP server ─────────────────────────────────────────────────────────────────

mcp = FastMCP(
    name="backlog-synthesizer",
    instructions=(
        "Provides access to Jira tickets, GitHub issues, and the Backlog Synthesizer "
        "pipeline. Typical workflow:\n"
        "1. create_session  → get a session_id\n"
        "2. Upload transcripts/wiki via the REST /ingest/* endpoints (or ask the user to do so)\n"
        "3. run_pipeline(session_id)  → trigger analysis\n"
        "4. get_stories(session_id) / get_gap_report(session_id)  → read results\n\n"
        "Use the Jira/GitHub resources to browse the existing backlog before running the pipeline."
    ),
)


# ── Resources ──────────────────────────────────────────────────────────────────

@mcp.resource("jira://tickets/{project_key}")
async def jira_tickets_resource(project_key: str) -> str:
    """All tickets in a Jira project (mock or live depending on USE_MOCK_BACKLOG)."""
    tickets = await fetch_jira_tickets(project_key)
    return json.dumps(tickets, indent=2)


@mcp.resource("github://issues/{owner}/{repo}")
async def github_issues_resource(owner: str, repo: str) -> str:
    """Open issues in a GitHub repository."""
    issues = await fetch_github_issues(owner, repo)
    return json.dumps(issues, indent=2)


# ── Tools ──────────────────────────────────────────────────────────────────────

@mcp.tool()
async def create_session() -> str:
    """Create a new pipeline session and return its session_id.

    Call this first. Pass the returned session_id to all other tools.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{BACKEND_URL}/sessions",
            headers=_backend_headers(),
        )
        resp.raise_for_status()
        session_id = resp.json()["session_id"]
        return json.dumps({"session_id": session_id})


@mcp.tool()
async def run_pipeline(session_id: str) -> str:
    """Trigger the Backlog Synthesizer pipeline for the given session.

    Transcripts (and optionally wiki / backlog) must be uploaded via the
    /ingest/* REST endpoints before calling this tool.
    Returns immediately — poll get_stories / get_gap_report for results.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{BACKEND_URL}/pipeline/run/{session_id}",
            headers=_backend_headers(),
            json={},
        )
        resp.raise_for_status()
        return json.dumps(resp.json())


@mcp.tool()
async def get_pipeline_status(session_id: str) -> str:
    """Check whether the pipeline has finished for a session.

    Returns status: 'running' | 'done' | 'error' and ready: true/false.
    Poll this after run_pipeline before calling get_stories.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{BACKEND_URL}/results/{session_id}",
            headers=_backend_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        return json.dumps({
            "session_id": session_id,
            "status":     data.get("status"),
            "ready":      data.get("ready", False),
        })


@mcp.tool()
async def get_stories(session_id: str) -> str:
    """Return the generated user stories for a completed pipeline run.

    Each story includes title, description, acceptance criteria (Given/When/Then),
    priority, and feature/system tags.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{BACKEND_URL}/results/{session_id}",
            headers=_backend_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ready"):
            return json.dumps({"error": f"Pipeline not complete yet. Status: {data.get('status')}"})
        stories = data.get("user_stories", [])
        return json.dumps(stories, indent=2)


@mcp.tool()
async def get_gap_report(session_id: str) -> str:
    """Return the gap and conflict report for a completed pipeline run.

    Includes conflicts (new story overlaps an existing ticket), gaps
    (themes not covered), and an overall coverage score.
    """
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{BACKEND_URL}/results/{session_id}",
            headers=_backend_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ready"):
            return json.dumps({"error": f"Pipeline not complete yet. Status: {data.get('status')}"})
        return json.dumps(data.get("gap_report", {}), indent=2)


@mcp.tool()
async def get_evaluation_scores(session_id: str) -> str:
    """Return the quality evaluation scores for a completed pipeline run.

    Includes AC completeness, clarity, traceability, and overall score (0-5).
    """
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{BACKEND_URL}/results/{session_id}",
            headers=_backend_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ready"):
            return json.dumps({"error": f"Pipeline not complete yet. Status: {data.get('status')}"})
        return json.dumps(data.get("evaluation_scores", {}), indent=2)


@mcp.tool()
async def list_sessions() -> str:
    """List recent pipeline runs with their status and summary stats."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{BACKEND_URL}/sessions/history",
            headers=_backend_headers(),
        )
        resp.raise_for_status()
        return json.dumps(resp.json().get("history", []), indent=2)


# ── ASGI app ───────────────────────────────────────────────────────────────────

sse_app = Starlette(
    routes=[
        Mount("/", app=mcp.sse_app()),
    ],
)
sse_app.add_middleware(ApiKeyMiddleware)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("MCP_PORT", "8002"))
    uvicorn.run("mcp_server.server:sse_app", host="0.0.0.0", port=port, reload=False)
