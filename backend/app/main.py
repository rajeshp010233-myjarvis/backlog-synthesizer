"""Application factory.

Separating create_app() from the module-level `app` instance makes the
factory testable and keeps startup/shutdown side-effects inside the
lifespan context manager.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.api.routes import ingest, pipeline, results, jira_actions, sessions
from app.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    pool = aioredis.ConnectionPool.from_url(
        settings.redis_url,
        max_connections=20,
        decode_responses=False,
    )
    app.state.redis = aioredis.Redis(connection_pool=pool)
    logger.info("Redis connection pool initialised (max_connections=20)")
    yield
    await app.state.redis.aclose()
    await pool.aclose()
    logger.info("Redis connection pool closed")


def create_app() -> FastAPI:
    settings = get_settings()

    # In production (APP_API_KEY set), hide the auto-generated docs
    docs_url = "/docs" if not settings.app_api_key else None
    redoc_url = "/redoc" if not settings.app_api_key else None

    app = FastAPI(
        title="Backlog Synthesizer API",
        version="1.0.0",
        docs_url=docs_url,
        redoc_url=redoc_url,
        lifespan=lifespan,
    )

    # Rate limiting — 60 requests/minute per IP by default
    limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # CORS — origins loaded from config to keep prod/dev aligned
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(sessions.router)
    app.include_router(ingest.router)
    app.include_router(pipeline.router)
    app.include_router(results.router)
    app.include_router(jira_actions.router)

    @app.get("/health", include_in_schema=False)
    async def health():
        try:
            await app.state.redis.ping()
            redis_ok = True
        except Exception:
            redis_ok = False
        return {"status": "ok", "redis": redis_ok}

    return app


app = create_app()
