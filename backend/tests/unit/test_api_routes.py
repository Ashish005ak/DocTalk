from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from backend.main import app


@pytest.fixture
def _mock_session_manager():
    """Patch the session_manager singleton used by the routes module."""
    mock_mgr = MagicMock()
    mock_mgr.active_count = 0
    with patch("backend.api.routes.session_manager", mock_mgr), \
         patch("backend.api.websocket.session_manager", mock_mgr):
        yield mock_mgr


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client, _mock_session_manager):
        _mock_session_manager.active_count = 3
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["sessions"] == 3


class TestCreateSession:
    @pytest.mark.asyncio
    async def test_create_session_success(self, client, _mock_session_manager):
        _mock_session_manager.create_session.return_value = (
            "abc123",
            "Hello, I'm your AI health assistant.",
        )
        resp = await client.post("/api/session?domain_id=general_medicine")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == "abc123"
        assert "Hello" in data["opening_message"]
        _mock_session_manager.create_session.assert_called_once_with("general_medicine")

    @pytest.mark.asyncio
    async def test_create_session_unknown_domain(self, client, _mock_session_manager):
        _mock_session_manager.create_session.side_effect = FileNotFoundError("not found")
        resp = await client.post("/api/session?domain_id=unknown_domain")
        assert resp.status_code == 404


class TestGetSessionState:
    @pytest.mark.asyncio
    async def test_get_state_success(self, client, _mock_session_manager):
        _mock_session_manager.get_session_state.return_value = {
            "phase": "exploring",
            "turn_count": 2,
            "information_gathered": {"Chief_Complaint": "headache"},
            "denied_symptoms": [],
            "hypothesis": None,
            "confidence": "low",
            "remaining_gaps": ["Onset"],
            "confirmed_red_flag_ids": [],
            "conversation_history": [],
        }
        resp = await client.get("/api/session/test-sid/state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["phase"] == "exploring"
        assert data["turn_count"] == 2

    @pytest.mark.asyncio
    async def test_get_state_unknown_session(self, client, _mock_session_manager):
        _mock_session_manager.get_session_state.side_effect = KeyError("Unknown session: bad-id")
        resp = await client.get("/api/session/bad-id/state")
        assert resp.status_code == 404


class TestTranscribe:
    @pytest.mark.asyncio
    async def test_transcribe_empty_file(self, client, _mock_session_manager):
        import sys

        mock_mod = MagicMock()
        with patch.dict(sys.modules, {
            "faster_whisper": MagicMock(),
            "backend.audio.transcriber": mock_mod,
        }):
            resp = await client.post(
                "/api/transcribe",
                files={"file": ("test.webm", b"", "audio/webm")},
            )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_transcribe_success(self, client, _mock_session_manager):
        import sys

        mock_mod = MagicMock()
        mock_mod.transcribe.return_value = "hello world"
        with patch.dict(sys.modules, {
            "faster_whisper": MagicMock(),
            "backend.audio.transcriber": mock_mod,
        }), patch("asyncio.to_thread", new_callable=AsyncMock, return_value="hello world"):
            resp = await client.post(
                "/api/transcribe",
                files={"file": ("test.webm", b"\x00\x01\x02", "audio/webm")},
            )
        assert resp.status_code == 200
        assert resp.json()["text"] == "hello world"
