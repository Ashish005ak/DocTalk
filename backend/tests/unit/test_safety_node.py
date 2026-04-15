from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.agent.nodes.safety import safety_node
from backend.agent.state import create_initial_state
from backend.domain.loader import load_domain
from backend.models.move import ConversationMove
from backend.models.state import MoveType


@pytest.fixture
def domain():
    return load_domain("general_medicine")


@pytest.fixture
def client():
    return MagicMock()


class TestSafetyNode:
    @pytest.mark.asyncio
    async def test_strips_banned_opener(self, client, domain):
        state = create_initial_state("general_medicine")
        state["doctor_response"] = "I understand your concerns. Where does it hurt?"
        state["patient_message"] = "My head hurts"

        result = await safety_node(state, client=client, domain=domain)

        assert not result["doctor_response"].startswith("I understand")
        assert "hurt" in result["doctor_response"]

    @pytest.mark.asyncio
    async def test_replaces_jargon(self, client, domain):
        jargon_domain = load_domain("general_medicine")
        if not jargon_domain.jargon_map:
            pytest.skip("No jargon map in test domain")

        term = next(iter(jargon_domain.jargon_map))
        replacement = jargon_domain.jargon_map[term]

        state = create_initial_state("general_medicine")
        state["doctor_response"] = f"Do you have {term}?"
        state["patient_message"] = "test"

        result = await safety_node(state, client=client, domain=jargon_domain)

        assert replacement in result["doctor_response"]
        assert term not in result["doctor_response"]

    @pytest.mark.asyncio
    async def test_dedup_replaces_repeated_question(self, client, domain):
        state = create_initial_state("general_medicine")
        state["doctor_response"] = "Where does the pain feel?"
        state["patient_message"] = "test"
        state["questions_asked"] = ["Where does the pain feel?"]

        result = await safety_node(state, client=client, domain=domain)

        assert result["doctor_response"] != "Where does the pain feel?"

    @pytest.mark.asyncio
    async def test_increments_turn_count(self, client, domain):
        state = create_initial_state("general_medicine")
        state["doctor_response"] = "How are you feeling?"
        state["patient_message"] = "test"
        state["turn_count"] = 3

        result = await safety_node(state, client=client, domain=domain)

        assert result["turn_count"] == 4

    @pytest.mark.asyncio
    async def test_appends_utterances(self, client, domain):
        state = create_initial_state("general_medicine")
        state["doctor_response"] = "Where is the pain?"
        state["patient_message"] = "I have a headache"
        state["turn_count"] = 1

        result = await safety_node(state, client=client, domain=domain)

        history = result["conversation_history"]
        assert len(history) == 2
        assert history[0].speaker == "patient"
        assert history[0].text == "I have a headache"
        assert history[1].speaker == "doctor"

    @pytest.mark.asyncio
    async def test_extracts_question_sentences(self, client, domain):
        state = create_initial_state("general_medicine")
        state["doctor_response"] = "I see. Can you describe the pain?"
        state["patient_message"] = "test"

        result = await safety_node(state, client=client, domain=domain)

        assert any("describe" in q.lower() for q in result["questions_asked"])

    @pytest.mark.asyncio
    async def test_clears_transient_fields(self, client, domain):
        state = create_initial_state("general_medicine")
        state["doctor_response"] = "Tell me about it."
        state["patient_message"] = "test"
        state["intake_facts"] = ["some_fact"]
        state["intake_intent"] = "mixed"
        state["pending_explanation"] = "something"

        result = await safety_node(state, client=client, domain=domain)

        assert result["intake_facts"] == []
        assert result["intake_intent"] == "answering"
        assert result["pending_explanation"] is None

    @pytest.mark.asyncio
    async def test_sets_last_question_asked_from_move(self, client, domain):
        state = create_initial_state("general_medicine")
        state["doctor_response"] = "Where is the pain?"
        state["patient_message"] = "test"
        state["conversation_move"] = ConversationMove(
            type=MoveType.QUESTION, target_gap="Site",
        )

        result = await safety_node(state, client=client, domain=domain)

        assert result["last_question_asked"] == "Site"

    @pytest.mark.asyncio
    async def test_empty_response_gets_fallback(self, client, domain):
        state = create_initial_state("general_medicine")
        state["doctor_response"] = ""
        state["patient_message"] = "test"

        result = await safety_node(state, client=client, domain=domain)

        assert len(result["doctor_response"]) > 0
