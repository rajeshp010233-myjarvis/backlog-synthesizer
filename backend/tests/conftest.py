"""Shared pytest fixtures for all backend tests.

Uses fakeredis — no real Redis needed.
Stubs langgraph/chromadb/LLM SDKs so CI doesn't need those heavy packages.
"""
import json
import sys
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

import pytest_asyncio
from httpx import AsyncClient, ASGITransport


# ── Stub heavy dependencies before any app import ─────────────────────────────

def _stub(name: str) -> MagicMock:
    mod = MagicMock()
    sys.modules[name] = mod
    return mod


for _pkg in [
    "langgraph", "langgraph.graph", "langgraph.checkpoint",
    "langgraph.checkpoint.memory",
    "chromadb", "chromadb.config",
    "openai", "anthropic",
    "google", "google.generativeai",
    "langsmith",
]:
    if _pkg not in sys.modules:
        _stub(_pkg)

# compiled_graph must be a concrete mock so the pipeline route can import it
_orch = MagicMock()
_orch.compiled_graph = MagicMock()
sys.modules.setdefault("app.agents.orchestrator", _orch)


# ── App factory ───────────────────────────────────────────────────────────────

def _make_app(redis_instance, extra_env: dict | None = None):
    """Build a minimal FastAPI app with fake Redis injected via lifespan.

    extra_env keys are written directly into os.environ and cleared after
    the app object is constructed — but get_settings() is called fresh each
    request via its dependency, so the env must stay set for the test duration.
    Callers that pass extra_env must restore os.environ themselves if needed;
    within a single test function this is fine.
    """
    import os
    from app.config import get_settings

    # Apply env overrides persistently (for the test duration)
    env = extra_env or {}
    for k, v in env.items():
        os.environ[k] = v
    get_settings.cache_clear()

    @asynccontextmanager
    async def _lifespan(app):
        app.state.redis = redis_instance
        yield
        # Restore env after test
        for k in env:
            os.environ.pop(k, None)
        get_settings.cache_clear()

    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.middleware import SlowAPIMiddleware
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from app.api.routes import ingest, pipeline, results, jira_actions, sessions

    app = FastAPI(title="Backlog Synthesizer Test", lifespan=_lifespan)
    limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(sessions.router)
    app.include_router(ingest.router)
    app.include_router(pipeline.router)
    app.include_router(results.router)
    app.include_router(jira_actions.router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def fake_redis():
    """Async fakeredis — matches the await redis.set(...) calls in route handlers."""
    import fakeredis.aioredis as aioredis
    r = aioredis.FakeRedis(decode_responses=False)
    yield r
    await r.aclose()


@pytest_asyncio.fixture
async def client(fake_redis):
    app = _make_app(fake_redis)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture
async def authed_client(fake_redis):
    app = _make_app(fake_redis, extra_env={"APP_API_KEY": "test-secret"})
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"X-Api-Key": "test-secret"},
        ) as ac:
            yield ac


# ── Helpers ────────────────────────────────────────────────────────────────────

async def create_session(client) -> str:
    resp = await client.post("/sessions")
    assert resp.status_code == 200, f"create_session failed: {resp.text}"
    return resp.json()["session_id"]


async def seed_session(client, fake_redis, transcripts=None, wiki=None) -> str:
    session_id = await create_session(client)
    ttl = 7 * 24 * 3600
    if transcripts is not None:
        await fake_redis.set(
            f"session:{session_id}:transcripts".encode(),
            json.dumps(transcripts).encode(),
            ex=ttl,
        )
    if wiki is not None:
        await fake_redis.set(
            f"session:{session_id}:wiki".encode(),
            json.dumps(wiki).encode(),
            ex=ttl,
        )
    return session_id
