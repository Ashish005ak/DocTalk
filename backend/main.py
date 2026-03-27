from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.config import settings
from backend.context.context_engine import ContextEngine
from backend.context.context_models import ContextObject
from backend.context.llm_client import LLMClientFactory, LLMError
from backend.domains.loader import DomainLoader
from backend.domains.models import DomainProfile
from backend.models.utterance import (
    SessionConfig,
    SessionState,
    Transcript,
    TranscriptMeta,
    Utterance,
)
from backend.simulation.preview_buffer import PreviewBuffer
from backend.simulation.replay_engine import ReplayEngine, ReplayState
from backend.simulation.transcript_validator import (
    TranscriptValidationError,
    validate_transcript_dict,
    validate_transcript_file,
)
from backend.suggestions.feedback_logger import FeedbackLogger
from backend.suggestions.suggestion_models import FeedbackSummary, SuggestionOutput
from backend.websocket.manager import WebSocketManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(name)s  %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application & singletons
# ---------------------------------------------------------------------------

app = FastAPI(title="ConvoNudge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ws_manager = WebSocketManager()
engine = ReplayEngine()
preview_buffer = PreviewBuffer(engine)
domain_loader = DomainLoader()

_custom_transcripts: dict[str, Transcript] = {}
_session_config: SessionConfig | None = None
_context_engine: ContextEngine | None = None
_feedback_logger: FeedbackLogger = FeedbackLogger()
_latest_suggestions: SuggestionOutput | None = None


# ---------------------------------------------------------------------------
# Engine → WebSocket bridge
# ---------------------------------------------------------------------------

async def _on_utterance(utt: Utterance) -> None:
    msg_type = "utterance_preview" if utt.is_preview else "utterance_commit"
    await ws_manager.broadcast({"type": msg_type, "data": utt.model_dump()})

    if not utt.is_preview and _context_engine is not None:
        asyncio.create_task(_context_engine.on_utterance(utt))

    if not utt.is_preview and utt.speaker == "interviewer":
        _feedback_logger.check_adapted(utt.text)


async def _on_state_change(state: ReplayState, turn: int) -> None:
    speed = engine.speed
    transcript_id = engine.transcript.id if engine.transcript else None
    await ws_manager.broadcast(
        {
            "type": "replay_state",
            "data": {
                "state": state,
                "turn": turn,
                "speed": speed,
                "transcript_id": transcript_id,
            },
        }
    )


preview_buffer.on_utterance(_on_utterance)
preview_buffer.on_state_change(_on_state_change)


async def _on_context_updated(ctx: ContextObject) -> None:
    await ws_manager.broadcast({
        "type": "context_updated",
        "data": ctx.model_dump(),
    })


async def _on_suggestions_updated(output: SuggestionOutput) -> None:
    global _latest_suggestions
    _latest_suggestions = output
    _feedback_logger.register_suggestions(output)
    await ws_manager.broadcast({
        "type": "suggestions_updated",
        "data": output.model_dump(),
    })


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_builtin_transcripts() -> dict[str, Transcript]:
    transcripts: dict[str, Transcript] = {}
    path = settings.transcripts_path
    if not path.exists():
        logger.warning("Transcripts directory not found: %s", path)
        return transcripts
    for json_file in path.glob("*.json"):
        try:
            t = validate_transcript_file(json_file)
            transcripts[t.id] = t
        except Exception as exc:
            logger.warning("Could not load transcript %s: %s", json_file.name, exc)
    return transcripts


_builtin_transcripts: dict[str, Transcript] = {}


@app.on_event("startup")
async def _startup() -> None:
    global _builtin_transcripts
    _builtin_transcripts = _load_builtin_transcripts()
    logger.info("Loaded %d built-in transcript(s): %s",
                len(_builtin_transcripts), list(_builtin_transcripts.keys()))
    logger.info("Domain profiles available: %s", domain_loader.available_ids())
    logger.info("LLM provider configured: '%s' (key set: %s)",
                LLMClientFactory.configured_provider(),
                LLMClientFactory.has_api_key())


def _all_transcripts() -> dict[str, Transcript]:
    return {**_builtin_transcripts, **_custom_transcripts}


def _get_transcript(transcript_id: str) -> Transcript:
    t = _all_transcripts().get(transcript_id)
    if t is None:
        raise HTTPException(status_code=404, detail=f"Transcript '{transcript_id}' not found.")
    return t


# ---------------------------------------------------------------------------
# REST — Transcripts
# ---------------------------------------------------------------------------

@app.get("/api/transcripts", response_model=list[TranscriptMeta])
async def list_transcripts() -> list[TranscriptMeta]:
    """List all available transcripts (built-in + uploaded) with metadata."""
    return [t.meta for t in _all_transcripts().values()]


@app.get("/api/transcripts/{transcript_id}", response_model=Transcript)
async def get_transcript(transcript_id: str) -> Transcript:
    """Return the full transcript JSON for a given id."""
    return _get_transcript(transcript_id)


@app.post("/api/transcripts/upload", response_model=TranscriptMeta, status_code=201)
async def upload_transcript(file: UploadFile) -> TranscriptMeta:
    """Upload a custom transcript JSON file."""
    if not file.filename or not file.filename.endswith(".json"):
        raise HTTPException(status_code=400, detail="File must be a .json file.")
    try:
        raw = await file.read()
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc

    try:
        transcript = validate_transcript_dict(data)
    except TranscriptValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc

    _custom_transcripts[transcript.id] = transcript
    logger.info("Custom transcript uploaded: '%s'", transcript.id)
    return transcript.meta


@app.post("/api/transcripts/upload-json", response_model=TranscriptMeta, status_code=201)
async def upload_transcript_json(data: dict[str, Any]) -> TranscriptMeta:
    """Upload a custom transcript as a raw JSON body (for paste-in from the UI)."""
    try:
        transcript = validate_transcript_dict(data)
    except TranscriptValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc

    _custom_transcripts[transcript.id] = transcript
    logger.info("Custom transcript uploaded via JSON body: '%s'", transcript.id)
    return transcript.meta


# ---------------------------------------------------------------------------
# REST — Session
# ---------------------------------------------------------------------------

@app.post("/api/session/configure", response_model=SessionConfig)
async def configure_session(config: SessionConfig) -> SessionConfig:
    """Set session parameters and prepare the engine."""
    global _session_config, _context_engine, _latest_suggestions

    is_chat = config.mode == "chat"

    if is_chat and not settings.chat_mode_enabled:
        logger.warning("Chat mode requested but feature flag is disabled")
        raise HTTPException(status_code=403, detail="Chat mode is not enabled on this server.")
    if is_chat and config.domain != "medical":
        logger.warning("Chat mode requested for unsupported domain '%s'", config.domain)
        raise HTTPException(status_code=400, detail="Chat mode is currently only available for the medical domain.")

    session_id: str
    if is_chat:
        session_id = f"chat-{uuid.uuid4().hex[:12]}"
    else:
        transcript = _get_transcript(config.transcript_id)  # type: ignore[arg-type]
        engine.load(transcript)
        engine.set_speed(config.speed)
        preview_buffer.notify_transcript_loaded(transcript)
        session_id = config.transcript_id  # type: ignore[assignment]

    _session_config = config
    _latest_suggestions = None
    _feedback_logger.reset()

    try:
        profile = domain_loader.get_profile(config.domain)
    except KeyError:
        logger.warning("Domain '%s' not found — using generic profile for context engine", config.domain)
        profile = domain_loader.get_profile("generic")

    try:
        llm_client = LLMClientFactory.get_client()
        _context_engine = ContextEngine(
            profile, llm_client, session_id=session_id, mode=config.mode,
        )
        _context_engine.subscribe(_on_context_updated)
        _context_engine.subscribe_suggestions(_on_suggestions_updated)
        logger.info("ContextEngine attached for session '%s' mode='%s'", session_id, config.mode)
    except (LLMError, ImportError) as exc:
        logger.warning("Could not create ContextEngine (LLM not available): %s", exc)
        _context_engine = None

    await ws_manager.broadcast({"type": "session_start", "data": config.model_dump()})

    if is_chat and profile.opening_message:
        opening_utt = Utterance(
            id=f"doc-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc).strftime("%H:%M:%S.000"),
            speaker="interviewer",
            text=profile.opening_message,
        )
        await ws_manager.broadcast({"type": "utterance_commit", "data": opening_utt.model_dump()})
        if _context_engine is not None:
            _context_engine._utterances.append(opening_utt)
            _context_engine._questions.append(opening_utt.text)
        logger.info("Chat opening message broadcast: '%s'", profile.opening_message)

    logger.info("Session configured: mode='%s' domain='%s' session_id='%s'",
                config.mode, config.domain, session_id)
    return config


@app.get("/api/session/state", response_model=SessionState)
async def get_session_state() -> SessionState:
    """Return current session state."""
    transcript = engine.transcript
    return SessionState(
        state=engine.state,
        transcript_id=transcript.id if transcript else None,
        domain=_session_config.domain if _session_config else None,
        turn_count=len(transcript.utterances) if transcript else 0,
        current_turn=engine.current_index,
        speed=engine.speed,
    )


# ---------------------------------------------------------------------------
# REST — Context
# ---------------------------------------------------------------------------

@app.get("/api/context", response_model=ContextObject)
async def get_context() -> ContextObject:
    """Return the current context object."""
    if _context_engine is None:
        return ContextObject(session_id=_session_config.transcript_id if _session_config else "")
    return _context_engine.current_context


# ---------------------------------------------------------------------------
# REST — Suggestions
# ---------------------------------------------------------------------------

@app.get("/api/suggestions")
async def get_suggestions() -> dict:
    """Return the latest suggestion output (for late-joining clients or refresh)."""
    if _latest_suggestions is None:
        return {"trigger_utt": "", "context_summary": "", "suggestions": []}
    return _latest_suggestions.model_dump()


@app.get("/api/suggestions/feedback", response_model=FeedbackSummary)
async def get_suggestion_feedback() -> FeedbackSummary:
    """Return feedback summary for the current session."""
    return _feedback_logger.summary


# ---------------------------------------------------------------------------
# REST — Domains
# ---------------------------------------------------------------------------

@app.get("/api/domains", response_model=list[DomainProfile])
async def list_domains() -> list[DomainProfile]:
    """List all available domain profiles."""
    return domain_loader.list_profiles()


@app.get("/api/domains/{domain_id}", response_model=DomainProfile)
async def get_domain(domain_id: str) -> DomainProfile:
    """Return a single domain profile by id."""
    try:
        profile = domain_loader.get_profile(domain_id)
    except KeyError as exc:
        logger.warning("Domain profile not found: '%s'", domain_id)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    logger.info("Domain profile requested: '%s' (framework=%s)", profile.id, profile.framework)
    return profile


# ---------------------------------------------------------------------------
# REST — LLM Status
# ---------------------------------------------------------------------------

@app.get("/api/llm/status")
async def llm_status() -> dict:
    """Return the configured LLM provider and whether its API key is set."""
    provider = LLMClientFactory.configured_provider()
    return {
        "provider": provider,
        "has_api_key": LLMClientFactory.has_api_key(provider),
        "available_providers": LLMClientFactory.available_providers(),
    }


# ---------------------------------------------------------------------------
# REST — Feature Flags
# ---------------------------------------------------------------------------

@app.get("/api/features")
async def get_features() -> dict:
    """Return feature flags for the frontend."""
    return {"chat_mode_enabled": settings.chat_mode_enabled}


# ---------------------------------------------------------------------------
# WebSocket — /ws
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    client_id = await ws_manager.connect(websocket)

    await ws_manager.send(client_id, {
        "type": "connection_ack",
        "data": {"client_id": client_id, "connections": ws_manager.connection_count},
    })

    if _session_config:
        await ws_manager.send(client_id, {"type": "session_start", "data": _session_config.model_dump()})

    state_data = {
        "state": engine.state,
        "turn": engine.current_index,
        "speed": engine.speed,
        "transcript_id": engine.transcript.id if engine.transcript else None,
    }
    await ws_manager.send(client_id, {"type": "replay_state", "data": state_data})

    if _latest_suggestions:
        await ws_manager.send(client_id, {
            "type": "suggestions_updated",
            "data": _latest_suggestions.model_dump(),
        })

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                await ws_manager.send(client_id, {"type": "error", "data": {"message": "Invalid JSON"}})
                continue

            action = message.get("action")
            await _handle_ws_action(client_id, action, message)

    except WebSocketDisconnect:
        await ws_manager.disconnect(client_id)


async def _handle_ws_action(client_id: str, action: str | None, message: dict[str, Any]) -> None:
    """Dispatch an inbound WebSocket action to the engine."""
    logger.info("WS action received: client=%s action='%s'", client_id[:8], action)
    if action == "start":
        if engine.state in ("idle", "finished", "paused"):
            if engine.state == "paused":
                engine.resume()
            else:
                engine.start()
        await ws_manager.send(client_id, {"type": "ack", "data": {"action": "start"}})

    elif action == "pause":
        engine.pause()
        await ws_manager.send(client_id, {"type": "ack", "data": {"action": "pause"}})

    elif action == "resume":
        engine.resume()
        await ws_manager.send(client_id, {"type": "ack", "data": {"action": "resume"}})

    elif action == "stop":
        engine.stop()
        if _context_engine is not None:
            _context_engine.reset()
        _feedback_logger.reset()
        global _latest_suggestions
        _latest_suggestions = None
        await ws_manager.broadcast({"type": "session_end"})

    elif action == "set_speed":
        speed = message.get("speed")
        if speed not in (0.5, 1.0, 2.0, 4.0):
            await ws_manager.send(client_id, {
                "type": "error",
                "data": {"message": f"Invalid speed '{speed}'. Must be 0.5, 1.0, 2.0, or 4.0."},
            })
            return
        engine.set_speed(float(speed))
        await ws_manager.broadcast({"type": "replay_state", "data": {
            "state": engine.state,
            "turn": engine.current_index,
            "speed": engine.speed,
            "transcript_id": engine.transcript.id if engine.transcript else None,
        }})

    elif action == "load_transcript":
        transcript_id = message.get("transcript_id")
        try:
            transcript = _get_transcript(transcript_id)
        except HTTPException as exc:
            await ws_manager.send(client_id, {"type": "error", "data": {"message": exc.detail}})
            return
        engine.load(transcript)
        preview_buffer.notify_transcript_loaded(transcript)
        await ws_manager.broadcast({"type": "replay_state", "data": {
            "state": engine.state,
            "turn": 0,
            "speed": engine.speed,
            "transcript_id": transcript.id,
        }})

    elif action == "chat_message":
        text = message.get("text", "").strip()
        if not text:
            await ws_manager.send(client_id, {
                "type": "error",
                "data": {"message": "chat_message requires non-empty 'text'."},
            })
            return
        if _context_engine is None:
            await ws_manager.send(client_id, {
                "type": "error",
                "data": {"message": "No active chat session."},
            })
            return

        now_ts = datetime.now(timezone.utc).strftime("%H:%M:%S.000")

        patient_utt = Utterance(
            id=f"pat-{uuid.uuid4().hex[:8]}",
            timestamp=now_ts,
            speaker="responder",
            text=text,
        )
        logger.info("Chat patient message: client=%s len=%d", client_id[:8], len(text))
        await ws_manager.broadcast({"type": "utterance_commit", "data": patient_utt.model_dump()})

        try:
            doctor_text = await _context_engine.chat_reply(patient_utt)
        except Exception:
            logger.exception("chat_reply failed — sending graceful fallback to patient")
            doctor_text = "I'm sorry, could you repeat that? I had a momentary lapse."

        doc_utt = Utterance(
            id=f"doc-{uuid.uuid4().hex[:8]}",
            timestamp=datetime.now(timezone.utc).strftime("%H:%M:%S.000"),
            speaker="interviewer",
            text=doctor_text,
        )
        logger.info("Chat doctor reply: len=%d", len(doctor_text))
        await ws_manager.broadcast({"type": "utterance_commit", "data": doc_utt.model_dump()})

    elif action == "use_suggestion":
        suggestion_id = message.get("suggestion_id", "")
        if _feedback_logger.mark_used(suggestion_id):
            await ws_manager.send(client_id, {
                "type": "ack",
                "data": {"action": "use_suggestion", "suggestion_id": suggestion_id},
            })
        else:
            await ws_manager.send(client_id, {
                "type": "error",
                "data": {"message": f"Could not mark suggestion '{suggestion_id}' as used."},
            })

    else:
        await ws_manager.send(client_id, {
            "type": "error",
            "data": {"message": f"Unknown action '{action}'."},
        })
