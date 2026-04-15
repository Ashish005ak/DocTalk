from __future__ import annotations

import pytest

from backend.agent.nodes.crisis import crisis_node, _EMERGENCY_RESPONSE
from backend.agent.state import create_initial_state
from backend.models.state import MoveType


@pytest.fixture
def _mock_deps():
    """Provide dummy client and domain -- crisis node uses neither."""
    from unittest.mock import MagicMock
    return MagicMock(), MagicMock()


class TestCrisisNode:
    @pytest.mark.asyncio
    async def test_returns_emergency_response(self, _mock_deps):
        client, domain = _mock_deps
        state = create_initial_state("general_medicine")
        state["patient_message"] = "I want to hurt myself"

        result = await crisis_node(state, client=client, domain=domain)

        assert result["doctor_response"] == _EMERGENCY_RESPONSE
        assert "emergency" in result["doctor_response"].lower()
        assert "911" in result["doctor_response"]

    @pytest.mark.asyncio
    async def test_appends_utterances(self, _mock_deps):
        client, domain = _mock_deps
        state = create_initial_state("general_medicine")
        state["patient_message"] = "I feel like ending it all"
        state["turn_count"] = 3

        result = await crisis_node(state, client=client, domain=domain)

        history = result["conversation_history"]
        assert len(history) == 2
        assert history[0].speaker == "patient"
        assert history[0].text == "I feel like ending it all"
        assert history[0].turn == 3
        assert history[1].speaker == "doctor"
        assert history[1].text == _EMERGENCY_RESPONSE
        assert history[1].turn == 3

    @pytest.mark.asyncio
    async def test_increments_turn_count(self, _mock_deps):
        client, domain = _mock_deps
        state = create_initial_state("general_medicine")
        state["turn_count"] = 5

        result = await crisis_node(state, client=client, domain=domain)

        assert result["turn_count"] == 6

    @pytest.mark.asyncio
    async def test_sets_crisis_move(self, _mock_deps):
        client, domain = _mock_deps
        state = create_initial_state("general_medicine")

        result = await crisis_node(state, client=client, domain=domain)

        assert result["conversation_move"].type == MoveType.CRISIS_RESPONSE
