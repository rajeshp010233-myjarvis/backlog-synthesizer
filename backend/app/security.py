from fastapi import Header, HTTPException, status
from app.config import get_settings


async def require_api_key(x_api_key: str = Header(default="", alias="X-Api-Key")) -> None:
    """Validates the X-Api-Key header when APP_API_KEY is configured.

    In development (APP_API_KEY unset), all requests are allowed through.
    In production, every route that depends on this will return 401 on a bad key.
    """
    settings = get_settings()
    if settings.app_api_key and x_api_key != settings.app_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
