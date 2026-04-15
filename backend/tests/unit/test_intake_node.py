from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agent.nodes.intake import intake_node
from backend.agent.state import create_initial_state
from backend.domain.loader import load_domain
from backend.models.facts import FactConfidence, RawFact
from backend.models.state import PatientIntent


@pytest.fixture
def domain():
    return load_domain("general_medicine")


@pytest.fixture
def mock_client():
    return MagicMock()


def _patch_all(intent, facts):
    """Patch the two async LLM callers (intent + fact extraction)."""
    return (
        patch("backend.agent.nodes.intake.classify_intent", new_callable=AsyncMock, return_value=intent),
        patch("backend.agent.nodes.intake.extract_facts", new_callable=AsyncMock, return_value=facts),
    )


class TestIntakeNode:
    @pytest.mark.asyncio
    async def test_answering_intent_returns_facts(self, mock_client, domain):
        facts = [RawFact(key="Chief_Complaint", value="headache", confidence=FactConfidence.HIGH)]
        p1, p2 = _patch_all(PatientIntent.ANSWERING, facts)

        with p1, p2:
            state = create_initial_state("general_medicine")
            state["patient_message"] = "I have a headache"

            result = await intake_node(state, client=mock_client, domain=domain)

        assert result["intake_intent"] == PatientIntent.ANSWERING.value
        assert len(result["intake_facts"]) == 1
        assert result["intake_facts"][0].key == "Chief_Complaint"
        assert result["pending_explanation"] is None

    @pytest.mark.asyncio
    async def test_asking_explanation_discards_facts(self, mock_client, domain):
        facts = [RawFact(key="Chief_Complaint", value="headache", confidence=FactConfidence.HIGH)]
        p1, p2 = _patch_all(PatientIntent.ASKING_EXPLANATION, facts)

        with p1, p2:
            state = create_initial_state("general_medicine")
            state["patient_message"] = "What does that mean?"

            result = await intake_node(state, client=mock_client, domain=domain)

        assert result["intake_intent"] == PatientIntent.ASKING_EXPLANATION.value
        assert result["intake_facts"] == []
        assert result["pending_explanation"] == "What does that mean?"

    @pytest.mark.asyncio
    async def test_mixed_intent_keeps_facts_and_sets_pending(self, mock_client, domain):
        facts = [RawFact(key="Time_Course", value="3 days", confidence=FactConfidence.HIGH)]
        p1, p2 = _patch_all(PatientIntent.MIXED, facts)

        with p1, p2:
            state = create_initial_state("general_medicine")
            state["patient_message"] = "It started 3 days ago, but what is that test for?"

            result = await intake_node(state, client=mock_client, domain=domain)

        assert result["intake_intent"] == PatientIntent.MIXED.value
        assert len(result["intake_facts"]) == 1
        assert result["pending_explanation"] is not None

    @pytest.mark.asyncio
    async def test_crisis_intent_passes_through(self, mock_client, domain):
        p1, p2 = _patch_all(PatientIntent.CRISIS, [])

        with p1, p2:
            state = create_initial_state("general_medicine")
            state["patient_message"] = "I want to hurt myself"

            result = await intake_node(state, client=mock_client, domain=domain)

        assert result["intake_intent"] == PatientIntent.CRISIS.value
        assert result["pending_explanation"] is None

    @pytest.mark.asyncio
    async def test_volunteered_keys_detected(self, mock_client, domain):
        facts = [
            RawFact(key="Chief_Complaint", value="headache", confidence=FactConfidence.HIGH),
            RawFact(key="Fever", value="yes, high", confidence=FactConfidence.HIGH),
        ]
        p1, p2 = _patch_all(PatientIntent.ANSWERING, facts)

        with p1, p2:
            state = create_initial_state("general_medicine")
            state["patient_message"] = "I have a headache and a high fever"
            state["last_question_asked"] = "Chief_Complaint"

            result = await intake_node(state, client=mock_client, domain=domain)

        assert "Fever" in result["new_volunteered_keys"]

    @pytest.mark.asyncio
    async def test_greeting_intent_clears_pending(self, mock_client, domain):
        p1, p2 = _patch_all(PatientIntent.GREETING, [])

        with p1, p2:
            state = create_initial_state("general_medicine")
            state["patient_message"] = "Hello doctor"

            result = await intake_node(state, client=mock_client, domain=domain)

        assert result["intake_intent"] == PatientIntent.GREETING.value
        assert result["pending_explanation"] is None
