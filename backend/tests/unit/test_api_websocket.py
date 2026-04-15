from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from backend.main import app


def _make_mock_manager(*, has_session: bool = True, send_result: dict | None = None):
    mgr = MagicMock()
    mgr.has_session.return_value = has_session
    mgr.active_count = 1
    if send_result is None:
        send_result = {
            "text": "Where is the pain?",
            "phase": "exploring",
            "state": {
                "phase": "exploring",
                "turn_count": 1,
                "information_gathered": {},
                "denied_symptoms": [],
                "hypothesis": None,
                "confidence": "low",
                "remaining_gaps": [],
                "confirmed_red_flag_ids": [],
                "conversation_history": [],
            },
        }
    mgr.send_message = AsyncMock(return_value=send_result)
    return mgr


class TestWebSocketConnect:
    def test_connect_valid_session(self):
        mock_mgr = _make_mock_manager()
        with patch("backend.api.routes.session_manager", mock_mgr), \
             patch("backend.api.websocket.session_manager", mock_mgr):
            client = TestClient(app)
            with client.websocket_connect("/ws/valid-session") as ws:
                msg = ws.receive_json()
                assert msg["type"] == "connected"
                assert msg["session_id"] == "valid-session"

    def test_connect_invalid_session_rejected(self):
        mock_mgr = _make_mock_manager(has_session=False)
        with patch("backend.api.routes.session_manager", mock_mgr), \
             patch("backend.api.websocket.session_manager", mock_mgr):
            client = TestClient(app)
            with pytest.raises(Exception):
                with client.websocket_connect("/ws/bad-session"):
                    pass


class TestWebSocketMessaging:
    def test_send_message_flow(self):
        mock_mgr = _make_mock_manager()
        with patch("backend.api.routes.session_manager", mock_mgr), \
             patch("backend.api.websocket.session_manager", mock_mgr):
            client = TestClient(app)
            with client.websocket_connect("/ws/test-session") as ws:
                connected = ws.receive_json()
                assert connected["type"] == "connected"

                ws.send_json({"text": "I have a headache"})

                thinking = ws.receive_json()
                assert thinking["type"] == "thinking"

                response = ws.receive_json()
                assert response["type"] == "response"
                assert response["text"] == "Where is the pain?"
                assert response["phase"] == "exploring"
                assert "state" in response

    def test_send_empty_text_returns_error(self):
        mock_mgr = _make_mock_manager()
        with patch("backend.api.routes.session_manager", mock_mgr), \
             patch("backend.api.websocket.session_manager", mock_mgr):
            client = TestClient(app)
            with client.websocket_connect("/ws/test-session") as ws:
                ws.receive_json()  # connected
                ws.send_json({"text": ""})
                error = ws.receive_json()
                assert error["type"] == "error"
                assert "non-empty" in error["message"]

    def test_send_invalid_json_returns_error(self):
        mock_mgr = _make_mock_manager()
        with patch("backend.api.routes.session_manager", mock_mgr), \
             patch("backend.api.websocket.session_manager", mock_mgr):
            client = TestClient(app)
            with client.websocket_connect("/ws/test-session") as ws:
                ws.receive_json()  # connected
                ws.send_text("not valid json {{{")
                error = ws.receive_json()
                assert error["type"] == "error"
                assert "Invalid JSON" in error["message"]

    def test_send_message_error_returns_error(self):
        mock_mgr = _make_mock_manager()
        mock_mgr.send_message = AsyncMock(side_effect=RuntimeError("LLM down"))
        with patch("backend.api.routes.session_manager", mock_mgr), \
             patch("backend.api.websocket.session_manager", mock_mgr):
            client = TestClient(app)
            with client.websocket_connect("/ws/test-session") as ws:
                ws.receive_json()  # connected
                ws.send_json({"text": "hello"})
                thinking = ws.receive_json()
                assert thinking["type"] == "thinking"
                error = ws.receive_json()
                assert error["type"] == "error"
