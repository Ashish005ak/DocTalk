from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.api.routes import session_manager
from backend.cost.tracker import cost_tracker

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str) -> None:
    """Session-scoped WebSocket handler for real-time consultation."""

    if not session_manager.has_session(session_id):
        logger.warning("WS_REJECT  session_id=%s  reason=unknown_session", session_id)
        await websocket.close(code=4004, reason="Unknown session")
        return

    await websocket.accept()
    logger.info("WS_CONNECT  session_id=%s", session_id)

    try:
        await websocket.send_json({
            "type": "connected",
            "session_id": session_id,
        })

        while True:
            raw = await websocket.receive_text()

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "error",
                    "message": "Invalid JSON",
                })
                continue

            text = data.get("text", "").strip()
            if not text:
                await websocket.send_json({
                    "type": "error",
                    "message": "Message requires non-empty 'text' field.",
                })
                continue

            logger.info(
                "WS_MESSAGE  session_id=%s  message_len=%d",
                session_id,
                len(text),
            )

            await websocket.send_json({"type": "thinking"})

            try:
                result = await session_manager.send_message(session_id, text)
                await websocket.send_json({
                    "type": "response",
                    "text": result["text"],
                    "phase": result["phase"],
                    "state": result["state"],
                    "consultation_ended": result.get("consultation_ended", False),
                })
                logger.info(
                    "WS_RESPONSE  session_id=%s  response_len=%d  phase=%s",
                    session_id,
                    len(result["text"]),
                    result["phase"],
                )
            except Exception as exc:
                logger.exception(
                    "WS_ERROR  session_id=%s  error=%s", session_id, exc
                )
                await websocket.send_json({
                    "type": "error",
                    "message": "An error occurred processing your message.",
                })

    except WebSocketDisconnect:
        cost_tracker.finalize_session(session_id)
        logger.info("WS_DISCONNECT  session_id=%s", session_id)
