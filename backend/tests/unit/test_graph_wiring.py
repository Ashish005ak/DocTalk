from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agent.graph import build_graph
from backend.agent.state import create_initial_state
from backend.domain.loader import load_domain
from backend.llm.clinical_reasoner import ClinicalReasoning, LLMHypothesisEntry
from backend.models.facts import FactConfidence, RawFact
from backend.models.state import MoveType, PatientIntent


@pytest.fixture
def domain():
    return load_domain("general_medicine")


@pytest.fixture
def mock_client():
    return MagicMock()


def _default_reasoning():
    return ClinicalReasoning(
        hypotheses=[
            LLMHypothesisEntry(name="URTI", probability=0.5, supporting_evidence="headache", missing_evidence="fever"),
        ],
        next_question="fever",
        question_rationale="Fever presence helps differentiate URTI from tension headache",
        confidence="low",
        should_summarize=False,
    )


def _patch_llm_callers(intent=PatientIntent.ANSWERING, facts=None, question="Where is the pain?"):
    """Patch all LLM callers used by the graph nodes."""
    if facts is None:
        facts = [RawFact(key="Chief_Complaint", value="headache", confidence=FactConfidence.HIGH)]

    return (
        patch("backend.agent.nodes.intake.classify_intent", new_callable=AsyncMock, return_value=intent),
        patch("backend.agent.nodes.intake.extract_facts", new_callable=AsyncMock, return_value=facts),
        patch("backend.agent.nodes.reason.generate_reasoning", new_callable=AsyncMock, return_value=_default_reasoning()),
        patch("backend.agent.nodes.response_gen.generate_question", new_callable=AsyncMock, return_value=question),
        patch("backend.agent.nodes.response_gen.generate_summary", new_callable=AsyncMock, return_value="Summary text."),
        patch("backend.agent.nodes.response_gen.generate_explanation", new_callable=AsyncMock, return_value="Explanation text."),
    )


class TestGraphWiring:
    def test_graph_compiles(self, mock_client, domain):
        compiled = build_graph(mock_client, domain)
        assert compiled is not None

    @pytest.mark.asyncio
    async def test_single_turn_normal_path(self, mock_client, domain):
        patches = _patch_llm_callers()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            compiled = build_graph(mock_client, domain)
            state = create_initial_state("general_medicine")
            state["patient_message"] = "I have a headache"

            config = {"configurable": {"thread_id": "test-normal-1"}}
            result = await compiled.ainvoke(state, config=config)

        assert result["doctor_response"]
        assert len(result["doctor_response"]) > 0
        assert result["turn_count"] == 1
        assert len(result["conversation_history"]) >= 2
        assert result["intake_facts"] == []
        assert result["intake_intent"] == "answering"

    @pytest.mark.asyncio
    async def test_crisis_path(self, mock_client, domain):
        patches = _patch_llm_callers(intent=PatientIntent.CRISIS, facts=[])
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            compiled = build_graph(mock_client, domain)
            state = create_initial_state("general_medicine")
            state["patient_message"] = "I want to hurt myself"

            config = {"configurable": {"thread_id": "test-crisis-1"}}
            result = await compiled.ainvoke(state, config=config)

        assert "emergency" in result["doctor_response"].lower()
        assert "911" in result["doctor_response"]
        assert result["turn_count"] == 1
        assert result["conversation_move"].type == MoveType.CRISIS_RESPONSE

    @pytest.mark.asyncio
    async def test_two_consecutive_turns(self, mock_client, domain):
        facts_t1 = [RawFact(key="Chief_Complaint", value="headache", confidence=FactConfidence.HIGH)]
        facts_t2 = [RawFact(key="Onset", value="yesterday", confidence=FactConfidence.HIGH)]

        patches_t1 = _patch_llm_callers(facts=facts_t1, question="When did it start?")
        with patches_t1[0], patches_t1[1], patches_t1[2], patches_t1[3], patches_t1[4], patches_t1[5]:
            compiled = build_graph(mock_client, domain)
            state = create_initial_state("general_medicine")
            state["patient_message"] = "I have a headache"

            config = {"configurable": {"thread_id": "test-multi-1"}}
            result_t1 = await compiled.ainvoke(state, config=config)

        assert result_t1["turn_count"] == 1
        assert "Chief_Complaint" in result_t1["information_gathered"]

        patches_t2 = _patch_llm_callers(facts=facts_t2, question="Can you describe the pain?")
        with patches_t2[0], patches_t2[1], patches_t2[2], patches_t2[3], patches_t2[4], patches_t2[5]:
            turn2_input = {"patient_message": "It started yesterday"}
            result_t2 = await compiled.ainvoke(turn2_input, config=config)

        assert result_t2["turn_count"] == 2
        assert "Onset" in result_t2["information_gathered"]
        assert "Chief_Complaint" in result_t2["information_gathered"]
