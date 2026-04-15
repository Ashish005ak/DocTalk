from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.llm.clinical_reasoner import ClinicalReasoning, LLMHypothesisEntry
from backend.models.facts import FactConfidence, RawFact
from backend.models.state import PatientIntent
from backend.session.manager import SessionManager


def _default_reasoning():
    return ClinicalReasoning(
        hypotheses=[
            LLMHypothesisEntry(name="URTI", probability=0.5, supporting_evidence="headache", missing_evidence="fever"),
        ],
        next_question="fever",
        question_rationale="Check for fever",
        confidence="low",
        should_summarize=False,
    )


def _patch_llm_callers(
    intent=PatientIntent.ANSWERING,
    facts=None,
    question="Where is the pain?",
):
    if facts is None:
        facts = [RawFact(key="Chief_Complaint", value="headache", confidence=FactConfidence.HIGH)]

    return (
        patch("backend.agent.nodes.intake.classify_intent", new_callable=AsyncMock, return_value=intent),
        patch("backend.agent.nodes.intake.extract_facts", new_callable=AsyncMock, return_value=facts),
        patch("backend.agent.nodes.reason.generate_reasoning", new_callable=AsyncMock, return_value=_default_reasoning()),
        patch("backend.agent.nodes.response_gen.generate_question", new_callable=AsyncMock, return_value=question),
        patch("backend.agent.nodes.response_gen.generate_summary", new_callable=AsyncMock, return_value="Summary."),
        patch("backend.agent.nodes.response_gen.generate_explanation", new_callable=AsyncMock, return_value="Explanation."),
    )


@pytest.fixture
def manager():
    with patch("backend.session.manager.AgentLLMClient", return_value=MagicMock(provider="mock", model="mock-model")):
        mgr = SessionManager()
        yield mgr


class TestSessionManagerCreate:
    def test_create_returns_session_id_and_opening(self, manager: SessionManager):
        sid, opening = manager.create_session("general_medicine")
        assert isinstance(sid, str)
        assert len(sid) == 32  # uuid4 hex
        assert isinstance(opening, str)
        assert len(opening) > 0

    def test_create_increments_active_count(self, manager: SessionManager):
        assert manager.active_count == 0
        manager.create_session("general_medicine")
        assert manager.active_count == 1
        manager.create_session("general_medicine")
        assert manager.active_count == 2

    def test_has_session(self, manager: SessionManager):
        sid, _ = manager.create_session("general_medicine")
        assert manager.has_session(sid) is True
        assert manager.has_session("nonexistent") is False


class TestSessionManagerSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_returns_response(self, manager: SessionManager):
        patches = _patch_llm_callers()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            sid, _ = manager.create_session("general_medicine")
            result = await manager.send_message(sid, "I have a headache")

        assert "text" in result
        assert len(result["text"]) > 0
        assert "phase" in result
        assert "state" in result

    @pytest.mark.asyncio
    async def test_send_message_unknown_session_raises(self, manager: SessionManager):
        with pytest.raises(KeyError, match="Unknown session"):
            await manager.send_message("nonexistent", "hello")

    @pytest.mark.asyncio
    async def test_two_turn_conversation(self, manager: SessionManager):
        facts_t1 = [RawFact(key="Chief_Complaint", value="headache", confidence=FactConfidence.HIGH)]
        facts_t2 = [RawFact(key="Onset", value="yesterday", confidence=FactConfidence.HIGH)]

        patches1 = _patch_llm_callers(facts=facts_t1, question="When did it start?")
        with patches1[0], patches1[1], patches1[2], patches1[3], patches1[4], patches1[5]:
            sid, _ = manager.create_session("general_medicine")
            r1 = await manager.send_message(sid, "I have a headache")

        assert "Chief_Complaint" in r1["state"]["information_gathered"]

        patches2 = _patch_llm_callers(facts=facts_t2, question="Describe the pain?")
        with patches2[0], patches2[1], patches2[2], patches2[3], patches2[4], patches2[5]:
            r2 = await manager.send_message(sid, "It started yesterday")

        assert "Onset" in r2["state"]["information_gathered"]
        assert "Chief_Complaint" in r2["state"]["information_gathered"]
        assert r2["state"]["turn_count"] == 2


class TestSessionManagerState:
    def test_get_session_state_before_messages(self, manager: SessionManager):
        sid, _ = manager.create_session("general_medicine")
        state = manager.get_session_state(sid)
        assert "phase" in state
        assert state["phase"] == "intake"
        assert state["turn_count"] == 0
        assert "information_gathered" in state

    @pytest.mark.asyncio
    async def test_get_session_state_after_message(self, manager: SessionManager):
        patches = _patch_llm_callers()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            sid, _ = manager.create_session("general_medicine")
            await manager.send_message(sid, "I have a headache")

        state = manager.get_session_state(sid)
        assert state["turn_count"] == 1
        assert "Chief_Complaint" in state["information_gathered"]

    def test_get_phase_initial(self, manager: SessionManager):
        sid, _ = manager.create_session("general_medicine")
        assert manager.get_phase(sid) == "intake"

    def test_get_state_unknown_session_raises(self, manager: SessionManager):
        with pytest.raises(KeyError, match="Unknown session"):
            manager.get_session_state("nonexistent")


class TestSessionManagerDelete:
    def test_delete_removes_session(self, manager: SessionManager):
        sid, _ = manager.create_session("general_medicine")
        assert manager.has_session(sid)
        manager.delete_session(sid)
        assert not manager.has_session(sid)
        assert manager.active_count == 0

    def test_delete_unknown_does_not_raise(self, manager: SessionManager):
        manager.delete_session("nonexistent")
