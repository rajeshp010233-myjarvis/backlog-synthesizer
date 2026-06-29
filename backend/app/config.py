import re
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # --- LLM providers ---
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # --- Pipeline defaults ---
    default_provider: str = "openai"
    orchestrator_model: str = "gpt-4o"
    specialist_model: str = "gpt-4o"
    evaluator_model: str = "gpt-4o-mini"

    # --- Infrastructure ---
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    redis_url: str = "redis://localhost:6379"
    redis_password: str = ""

    # --- Jira ---
    jira_base_url: str = ""
    jira_email: str = ""
    jira_token: str = ""
    jira_project_key: str = "QE"

    # --- Security ---
    app_api_key: str = ""           # If set, all API routes require X-Api-Key header
    cors_origins: str = "http://localhost:5173,http://localhost:80"

    # --- Observability ---
    langsmith_api_key: str = ""
    langsmith_project: str = "backlog-synthesizer"

    # --- Feature flags ---
    use_mock_backlog: bool = True
    pipeline_timeout_seconds: int = 600   # hard cap per pipeline run
    max_retries: int = 2

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # unknown env vars are silently skipped instead of crashing

    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def session_id_is_valid(self, session_id: str) -> bool:
        """Restrict session IDs to safe characters to prevent Redis key injection."""
        return bool(re.fullmatch(r"[a-zA-Z0-9_\-]{8,64}", session_id))


@lru_cache
def get_settings() -> Settings:
    return Settings()
