from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from backend.config import settings
from backend.session.manager import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])

session_manager = SessionManager()


# ---------------------------------------------------------------------------
# POST /api/session
# ---------------------------------------------------------------------------

@router.post("/session")
async def create_session(domain_id: str = settings.default_domain):
    """Create a new consultation session and return its ID + opening message."""
    try:
        sid, opening = session_manager.create_session(domain_id)
    except FileNotFoundError:
        logger.warning("ROUTE_SESSION_CREATE  unknown domain_id=%s", domain_id)
        raise HTTPException(status_code=404, detail=f"Unknown domain: {domain_id}")
    except Exception as exc:
        logger.exception("ROUTE_SESSION_CREATE  failed domain_id=%s", domain_id)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info("ROUTE_SESSION_CREATE  session_id=%s  domain_id=%s", sid, domain_id)
    return {"session_id": sid, "opening_message": opening}


# ---------------------------------------------------------------------------
# GET /api/session/{session_id}/state
# ---------------------------------------------------------------------------

@router.get("/session/{session_id}/state")
async def get_session_state(session_id: str):
    """Return the current clinical state snapshot for the frontend."""
    try:
        state = session_manager.get_session_state(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Unknown session: {session_id}")

    return state


# ---------------------------------------------------------------------------
# POST /api/transcribe
# ---------------------------------------------------------------------------

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe an uploaded audio clip using Faster Whisper."""
    from backend.audio import transcriber

    suffix = Path(file.filename or "audio.webm").suffix or ".webm"
    try:
        raw = await file.read()
    except Exception as exc:
        logger.error("Failed to read uploaded audio file: %s", exc)
        raise HTTPException(
            status_code=400, detail=f"Failed to read uploaded file: {exc}"
        ) from exc

    if len(raw) == 0:
        logger.warning("Received empty audio file for transcription")
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

    logger.info(
        "ROUTE_TRANSCRIBE  filename='%s'  size=%d bytes",
        file.filename or "unknown",
        len(raw),
    )

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp.name
    try:
        tmp.write(raw)
        tmp.close()
        text = await asyncio.to_thread(transcriber.transcribe, tmp_path)
    except Exception as exc:
        logger.exception("Transcription failed for file '%s'", file.filename)
        raise HTTPException(
            status_code=500, detail=f"Transcription failed: {exc}"
        ) from exc
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    logger.info(
        "ROUTE_TRANSCRIBE  complete  chars=%d  filename='%s'",
        len(text),
        file.filename or "unknown",
    )
    return {"text": text}


# ---------------------------------------------------------------------------
# GET /api/health
# ---------------------------------------------------------------------------

@router.get("/health")
async def health_check():
    """Liveness check."""
    return {"status": "ok", "sessions": session_manager.active_count}
