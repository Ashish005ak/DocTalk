from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agent.nodes.reason import reason_node
from backend.agent.state import create_initial_state
from backend.domain.loader import load_domain
from backend.llm.clinical_reasoner import ClinicalReasoning, LLMHypothesisEntry
from backend.models.facts import FactConfidence, RawFact
from backend.models.state import Confidence, Phase


@pytest.fixture
def domain():
    return load_domain("general_medicine")


@pytest.fixture
def client():
    return MagicMock()


def _mock_reasoning(**overrides):
    defaults = dict(
        hypotheses=[
            LLMHypothesisEntry(name="URTI", probability=0.4, supporting_evidence="cough, fever", missing_evidence="duration"),
            LLMHypothesisEntry(name="Meningitis", probability=0.3, supporting_evidence="headache, fever", missing_evidence="neck stiffness"),
        ],
        next_question="neck stiffness",
        question_rationale="Neck stiffness would help differentiate meningitis from URTI",
        confidence="low",
        should_summarize=False,
    )
    defaults.update(overrides)
    return ClinicalReasoning(**defaults)


class TestReasonNode:
    @pytest.mark.asyncio
    async def test_empty_facts_produces_hypothesis(self, client, domain):
        reasoning = _mock_reasoning()
        with patch("backend.agent.nodes.reason.generate_reasoning", new_callable=AsyncMock, return_value=reasoning):
            state = create_initial_state("general_medicine")
            state["turn_count"] = 1
            state["intake_facts"] = []

            result = await reason_node(state, client=client, domain=domain)

        assert result["hypothesis"] is not None
        assert result["hypothesis"].leading.name == "URTI"
        assert result["remaining_gaps"] == ["neck stiffness"]

    @pytest.mark.asyncio
    async def test_merges_high_confidence_facts(self, client, domain):
        reasoning = _mock_reasoning()
        with patch("backend.agent.nodes.reason.generate_reasoning", new_callable=AsyncMock, return_value=reasoning):
            state = create_initial_state("general_medicine")
            state["turn_count"] = 1
            state["intake_facts"] = [
                RawFact(key="Chief_Complaint", value="headache", confidence=FactConfidence.HIGH),
                RawFact(key="Age", value="35", confidence=FactConfidence.HIGH),
            ]

            result = await reason_node(state, client=client, domain=domain)

        assert "Chief_Complaint" in result["information_gathered"]
        assert result["information_gathered"]["Chief_Complaint"] == "headache"
        assert "Age" in result["information_gathered"]

    @pytest.mark.asyncio
    async def test_medium_confidence_goes_to_unconfirmed(self, client, domain):
        reasoning = _mock_reasoning()
        with patch("backend.agent.nodes.reason.generate_reasoning", new_callable=AsyncMock, return_value=reasoning):
            state = create_initial_state("general_medicine")
            state["turn_count"] = 1
            state["intake_facts"] = [
                RawFact(key="Fever", value="maybe", confidence=FactConfidence.MEDIUM),
            ]

            result = await reason_node(state, client=client, domain=domain)

        assert "Fever" not in result["information_gathered"]
        assert "Fever" in result["unconfirmed_facts"]

    @pytest.mark.asyncio
    async def test_denied_facts_tracked(self, client, domain):
        reasoning = _mock_reasoning()
        with patch("backend.agent.nodes.reason.generate_reasoning", new_callable=AsyncMock, return_value=reasoning):
            state = create_initial_state("general_medicine")
            state["turn_count"] = 1
            state["intake_facts"] = [
                RawFact(key="Cough", value="", denied=True),
            ]

            result = await reason_node(state, client=client, domain=domain)

        assert "Cough" in result["denied_symptoms"]

    @pytest.mark.asyncio
    async def test_phase_stays_intake_on_turn_zero(self, client, domain):
        reasoning = _mock_reasoning()
        with patch("backend.agent.nodes.reason.generate_reasoning", new_callable=AsyncMock, return_value=reasoning):
            state = create_initial_state("general_medicine")
            state["turn_count"] = 0
            state["intake_facts"] = []

            result = await reason_node(state, client=client, domain=domain)

        assert result["phase"] == Phase.INTAKE

    @pytest.mark.asyncio
    async def test_should_summarize_triggers_summary_phase(self, client, domain):
        reasoning = _mock_reasoning(should_summarize=True, confidence="high")
        with patch("backend.agent.nodes.reason.generate_reasoning", new_callable=AsyncMock, return_value=reasoning):
            state = create_initial_state("general_medicine")
            state["turn_count"] = 5
            state["intake_facts"] = []

            result = await reason_node(state, client=client, domain=domain)

        assert result["phase"] == Phase.SUMMARY
        assert result["remaining_gaps"] == []

    @pytest.mark.asyncio
    async def test_high_confidence_sets_narrowing(self, client, domain):
        reasoning = _mock_reasoning(confidence="high", should_summarize=False)
        with patch("backend.agent.nodes.reason.generate_reasoning", new_callable=AsyncMock, return_value=reasoning):
            state = create_initial_state("general_medicine")
            state["turn_count"] = 3
            state["intake_facts"] = []

            result = await reason_node(state, client=client, domain=domain)

        assert result["phase"] == Phase.NARROWING
        assert result["confidence"] == Confidence.HIGH

    @pytest.mark.asyncio
    async def test_max_turns_forces_summary(self, client, domain):
        reasoning = _mock_reasoning(should_summarize=False)
        with patch("backend.agent.nodes.reason.generate_reasoning", new_callable=AsyncMock, return_value=reasoning):
            state = create_initial_state("general_medicine")
            state["turn_count"] = 30
            state["intake_facts"] = []

            result = await reason_node(state, client=client, domain=domain)

        assert result["phase"] == Phase.SUMMARY
