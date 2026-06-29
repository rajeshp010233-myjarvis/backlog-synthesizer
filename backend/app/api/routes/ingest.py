"""File ingestion routes.

Security controls applied here:
- API key required on every endpoint (require_api_key dependency).
- Session ID validated against the server-created sessions in Redis.
- File size capped at MAX_FILE_BYTES (10 MB).
- File type restricted to per-endpoint allowlists.
"""
import json
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from app.config import get_settings
from app.security import require_api_key
from app.tools.document_parser import parse_document

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/ingest",
    tags=["ingest"],
    dependencies=[Depends(require_api_key)],
)

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB

_ALLOWED: dict[str, set[str]] = {
    "transcripts": {".pdf", ".txt", ".docx"},
    "wiki":        {".html", ".htm", ".pdf", ".txt"},
    "backlog":     {".json"},
}


async def _validate_session(session_id: str, request: Request) -> None:
    if not get_settings().session_id_is_valid(session_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid session ID format.")
    exists = await request.app.state.redis.exists(f"session:{session_id}:created")
    if not exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")


def _validate_file(upload: UploadFile, raw: bytes, endpoint: str) -> None:
    ext = Path(upload.filename or "").suffix.lower()
    allowed = _ALLOWED[endpoint]
    if ext not in allowed:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type {ext!r} not allowed for {endpoint}. Allowed: {sorted(allowed)}",
        )
    if len(raw) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty.")
    if len(raw) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB limit.",
        )


@router.post("/transcripts/{session_id}")
async def upload_transcripts(
    session_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
) -> dict:
    await _validate_session(session_id, request)
    texts: list[str] = []
    for f in files:
        raw = await f.read()
        _validate_file(f, raw, "transcripts")
        texts.append(parse_document(f.filename or "file.txt", raw))
        logger.info("Ingested transcript %s (%d bytes) for session %s", f.filename, len(raw), session_id)

    await request.app.state.redis.set(
        f"session:{session_id}:transcripts", json.dumps(texts), ex=7200
    )
    return {"session_id": session_id, "files_ingested": len(texts)}


@router.post("/wiki/{session_id}")
async def upload_wiki(
    session_id: str,
    request: Request,
    files: list[UploadFile] = File(...),
) -> dict:
    await _validate_session(session_id, request)
    texts: list[str] = []
    for f in files:
        raw = await f.read()
        _validate_file(f, raw, "wiki")
        texts.append(parse_document(f.filename or "file.html", raw))

    await request.app.state.redis.set(
        f"session:{session_id}:wiki", json.dumps(texts), ex=7200
    )
    return {"session_id": session_id, "files_ingested": len(texts)}


@router.post("/backlog/{session_id}")
async def upload_backlog(
    session_id: str,
    request: Request,
    file: UploadFile = File(...),
) -> dict:
    await _validate_session(session_id, request)
    raw = await file.read()
    _validate_file(file, raw, "backlog")

    try:
        tickets = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File must be valid JSON.")

    if not isinstance(tickets, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Backlog JSON must be a list of ticket objects.",
        )

    await request.app.state.redis.set(
        f"session:{session_id}:tickets", json.dumps(tickets), ex=7200
    )
    return {"session_id": session_id, "tickets_loaded": len(tickets)}
