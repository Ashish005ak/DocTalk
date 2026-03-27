from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

logger = logging.getLogger(__name__)


class WebSocketManager:
    """
    Manages all active WebSocket connections.

    Clients are tracked by a generated client_id (UUID4 hex).
    Broadcasts send to all active connections; send() targets a single client.
    Stale/disconnected sockets are silently evicted on send failure.
    """

    def __init__(self) -> None:
        self._clients: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket) -> str:
        """Accept the connection and return a unique client_id."""
        await websocket.accept()
        client_id = uuid.uuid4().hex
        self._clients[client_id] = websocket
        logger.info("Client connected: %s  (total=%d)", client_id[:8], len(self._clients))
        return client_id

    async def disconnect(self, client_id: str) -> None:
        """Remove a client. Safe to call even if already disconnected."""
        ws = self._clients.pop(client_id, None)
        if ws is not None:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.close()
            except Exception:
                pass
        logger.info("Client disconnected: %s  (total=%d)", client_id[:8], len(self._clients))

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Send a JSON message to every connected client."""
        msg_type = message.get("type", "unknown")
        client_count = len(self._clients)
        if client_count == 0:
            return
        logger.debug("Broadcasting '%s' to %d client(s)", msg_type, client_count)
        payload = json.dumps(message)
        stale: list[str] = []
        for client_id, ws in list(self._clients.items()):
            try:
                await ws.send_text(payload)
            except (WebSocketDisconnect, RuntimeError, Exception):
                stale.append(client_id)

        if stale:
            logger.info("Evicting %d stale client(s) after broadcast", len(stale))
        for client_id in stale:
            await self.disconnect(client_id)

    async def send(self, client_id: str, message: dict[str, Any]) -> None:
        """Send a JSON message to a specific client."""
        ws = self._clients.get(client_id)
        if ws is None:
            return
        try:
            await ws.send_text(json.dumps(message))
        except (WebSocketDisconnect, RuntimeError, Exception):
            await self.disconnect(client_id)

    @property
    def connection_count(self) -> int:
        return len(self._clients)
