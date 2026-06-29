"""
MCP server exposing JIRA/GitHub as resources and pipeline tools.

Run standalone:  python -m mcp_server.server
Or via SSE:      uvicorn mcp_server.server:sse_app --port 8002
"""
import json
import os
import sys

import httpx
import redis.asyncio as aioredis
from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Mount

from .resources import fetch_jira_tickets, fetch_github_issues

mcp = FastMCP(
    name="backlog-synthesizer",
    instructions=(
        "Provides access to JIRA tickets, GitHub issues, and the Backlog Synthesizer "
        "pipeline tools. Use the JIRA/GitHub resources to browse existing backlog items, "
        "then call run_pipeline to generate enriched user stories from uploaded transcripts."
    ),
)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource("jira://tickets/{project_key}")
async def jira_tickets_resource(project_key: str) -> str:
    """All tickets in a JIRA project (mock or live depending on USE_MOCK_BACKLOG)."""
    tickets = await fetch_jira_tickets(project_key)
    return json.dumps(tickets, indent=2)


@mcp.resource("github://issues/{owner}/{repo}")
async def github_issues_resource(owner: str, repo: str) -> str:
    """Open issues in a GitHub repository."""
    issues = await fetch_github_issues(owner, repo)
    return json.dumps(issues, indent=2)


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def run_pipeline(session_id: str) -> str:
    """
    Trigger the Backlog Synthesizer pipeline for the given session.

    The session must already have transcripts (and optionally wiki / backlog)
    uploaded via the /ingest/* REST endpoints before calling this tool.

    Returns the pipeline status or the final PipelineResult JSON.
    """
    async with httpx.AsyncClient(timeout=300) as client:
        resp = await client.post(f"{BACKEND_URL}/pipeline/run/{session_id}")
        if resp.status_code == 202:
            return f"Pipeline started for session {session_id}. Poll get_stories / get_gap_report for results."
        resp.raise_for_status()
        return resp.text


@mcp.tool()
async def get_stories(session_id: str) -> str:
    """
    Return the generated user stories for a completed pipeline run.

    Each story includes title, role, goal, benefit, and
    Given/When/Then acceptance criteria.
    """
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        raw = await redis.get(f"pipeline_result:{session_id}")
        if not raw:
            return f"No results found for session {session_id}. Run the pipeline first."
        result = json.loads(raw)
        stories = result.get("stories", [])
        return json.dumps(stories, indent=2)
    finally:
        await redis.aclose()


@mcp.tool()
async def get_gap_report(session_id: str) -> str:
    """
    Return the gap and conflict report for a completed pipeline run.

    The report identifies conflicts (new story overlaps an existing ticket) and
    gaps (existing ticket themes not addressed by new stories).
    """
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        raw = await redis.get(f"pipeline_result:{session_id}")
        if not raw:
            return f"No results found for session {session_id}. Run the pipeline first."
        result = json.loads(raw)
        gap_report = result.get("gap_report", {})
        return json.dumps(gap_report, indent=2)
    finally:
        await redis.aclose()


@mcp.tool()
async def list_sessions() -> str:
    """List all active session IDs stored in Redis."""
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        keys = await redis.keys("pipeline_result:*")
        session_ids = [k.replace("pipeline_result:", "") for k in keys]
        return json.dumps(session_ids, indent=2)
    finally:
        await redis.aclose()


# ---------------------------------------------------------------------------
# ASGI app (SSE transport for Claude Desktop / MCP clients)
# ---------------------------------------------------------------------------

sse_app = Starlette(
    routes=[
        Mount("/", app=mcp.sse_app()),
    ]
)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("MCP_PORT", "8002"))
    uvicorn.run("mcp_server.server:sse_app", host="0.0.0.0", port=port, reload=False)
