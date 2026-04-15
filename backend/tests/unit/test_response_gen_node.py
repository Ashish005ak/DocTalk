from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agent.nodes.response_gen import response_gen_node
from backend.agent.state import create_initial_state
from backend.domain.loader import load_domain
from backend.models.move import ConversationMove
from backend.models.state import MoveType, PatientIntent


@pytest.fixture
def domain():
    return load_domain("general_medicine")


@pytest.fixture
def client():
    return MagicMock()


class TestResponseGenNode:
    @pytest.mark.asyncio
    async def test_question_move_calls_generate_question(self, client, domain):
        with patch("backend.agent.nodes.response_gen.generate_question", new_callable=AsyncMock) as mock_q:
            mock_q.return_value = "Where is the pain located?"
            state = create_initial_state("general_medicine")
            state["conversation_move"] = ConversationMove(type=MoveType.QUESTION, target_gap="Site")

            result = await response_gen_node(state, client=client, domain=domain)

        assert result["doctor_response"] == "Where is the pain located?"
        mock_q.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_summarize_move_calls_generate_summary(self, client, domain):
        with patch("backend.agent.nodes.response_gen.generate_summary", new_callable=AsyncMock) as mock_s:
            mock_s.return_value = "## Summary\n- Headache reported"
            state = create_initial_state("general_medicine")
            state["conversation_move"] = ConversationMove(type=MoveType.SUMMARIZE)

            result = await response_gen_node(state, client=client, domain=domain)

        assert "Summary" in result["doctor_response"]
        mock_s.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_explain_move_calls_generate_explanation(self, client, domain):
        with patch("backend.agent.nodes.response_gen.generate_explanation", new_callable=AsyncMock) as mock_e:
            mock_e.return_value = "We ask this because..."
            state = create_initial_state("general_medicine")
            state["conversation_move"] = ConversationMove(type=MoveType.EXPLAIN, target_gap="Onset")
            state["intake_intent"] = PatientIntent.ASKING_EXPLANATION.value

            result = await response_gen_node(state, client=client, domain=domain)

        assert result["doctor_response"] == "We ask this because..."
        mock_e.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_mixed_explain_blends_with_question(self, client, domain):
        with (
            patch("backend.agent.nodes.response_gen.generate_explanation", new_callable=AsyncMock) as mock_e,
            patch("backend.agent.nodes.response_gen.generate_question", new_callable=AsyncMock) as mock_q,
        ):
            mock_e.return_value = "That's a great question."
            mock_q.return_value = "How long have you had this?"
            state = create_initial_state("general_medicine")
            state["conversation_move"] = ConversationMove(type=MoveType.EXPLAIN, target_gap="Time_Course")
            state["intake_intent"] = PatientIntent.MIXED.value
            state["pending_explanation"] = "Why do you ask?"

            result = await response_gen_node(state, client=client, domain=domain)

        assert "That's a great question." in result["doctor_response"]
        assert "How long have you had this?" in result["doctor_response"]
        mock_e.assert_awaited_once()
        mock_q.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_concern_move_calls_generate_question(self, client, domain):
        with patch("backend.agent.nodes.response_gen.generate_question", new_callable=AsyncMock) as mock_q:
            mock_q.return_value = "I understand your worry. Let's continue."
            state = create_initial_state("general_medicine")
            state["conversation_move"] = ConversationMove(
                type=MoveType.ACKNOWLEDGE_CONCERN, target_gap="Onset",
            )

            result = await response_gen_node(state, client=client, domain=domain)

        assert "understand" in result["doctor_response"].lower()
        mock_q.assert_awaited_once()
