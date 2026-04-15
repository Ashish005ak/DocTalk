from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from backend.agent.nodes.flow_control import flow_control_node
from backend.agent.state import create_initial_state
from backend.domain.models import DomainProfile, RedFlagConfig, ConfidenceThresholds
from backend.domain.loader import load_domain
from backend.models.state import MoveType, PatientIntent, Phase


@pytest.fixture
def domain():
    return load_domain("general_medicine")


@pytest.fixture
def client():
    return MagicMock()


class TestFlowControlNode:
    @pytest.mark.asyncio
    async def test_question_move_when_gaps_exist(self, client, domain):
        state = create_initial_state("general_medicine")
        state["remaining_gaps"] = ["Onset", "Duration"]
        state["phase"] = Phase.EXPLORING
        state["intake_intent"] = PatientIntent.ANSWERING.value

        result = await flow_control_node(state, client=client, domain=domain)

        assert result["conversation_move"].type == MoveType.QUESTION
        assert result["conversation_move"].target_gap == "Onset"

    @pytest.mark.asyncio
    async def test_summary_when_phase_is_summary(self, client, domain):
        state = create_initial_state("general_medicine")
        state["phase"] = Phase.SUMMARY
        state["intake_intent"] = PatientIntent.ANSWERING.value

        result = await flow_control_node(state, client=client, domain=domain)

        assert result["conversation_move"].type == MoveType.SUMMARIZE

    @pytest.mark.asyncio
    async def test_acknowledge_concern(self, client, domain):
        state = create_initial_state("general_medicine")
        state["phase"] = Phase.EXPLORING
        state["intake_intent"] = PatientIntent.EXPRESSING_CONCERN.value
        state["remaining_gaps"] = ["Location"]

        result = await flow_control_node(state, client=client, domain=domain)

        assert result["conversation_move"].type == MoveType.ACKNOWLEDGE_CONCERN
        assert result["conversation_move"].target_gap == "Location"

    @pytest.mark.asyncio
    async def test_explain_when_asking_explanation(self, client, domain):
        state = create_initial_state("general_medicine")
        state["phase"] = Phase.EXPLORING
        state["intake_intent"] = PatientIntent.ASKING_EXPLANATION.value
        state["pending_explanation"] = "What does that mean?"
        state["remaining_gaps"] = ["Duration"]

        result = await flow_control_node(state, client=client, domain=domain)

        assert result["conversation_move"].type == MoveType.EXPLAIN
        assert result["conversation_move"].target_gap == "Duration"

    @pytest.mark.asyncio
    async def test_clarify_unconfirmed_facts(self, client, domain):
        state = create_initial_state("general_medicine")
        state["phase"] = Phase.EXPLORING
        state["intake_intent"] = PatientIntent.ANSWERING.value
        state["unconfirmed_facts"] = {"Fever": "maybe"}
        state["remaining_gaps"] = []

        result = await flow_control_node(state, client=client, domain=domain)

        assert result["conversation_move"].type == MoveType.CLARIFY
        assert result["conversation_move"].target_gap == "Fever"

    @pytest.mark.asyncio
    async def test_fallback_summary_when_no_gaps(self, client, domain):
        state = create_initial_state("general_medicine")
        state["phase"] = Phase.EXPLORING
        state["intake_intent"] = PatientIntent.ANSWERING.value
        state["remaining_gaps"] = []

        result = await flow_control_node(state, client=client, domain=domain)

        assert result["conversation_move"].type == MoveType.SUMMARIZE

    @pytest.mark.asyncio
    async def test_snapshot_updated(self, client, domain):
        state = create_initial_state("general_medicine")
        state["information_gathered"] = {"Chief_Complaint": "headache"}
        state["remaining_gaps"] = ["Onset"]
        state["intake_intent"] = PatientIntent.ANSWERING.value

        result = await flow_control_node(state, client=client, domain=domain)

        assert result["last_rf_check_fact_snapshot"]["Chief_Complaint"] == "headache"


def _make_domain_with_flag(flag: RedFlagConfig, watch_turns_limit: int = 5) -> DomainProfile:
    return DomainProfile(
        id="test", name="Test", description="", opening_message="Hi",
        red_flags=[flag],
        thresholds=ConfidenceThresholds(watch_turns_limit=watch_turns_limit),
    )


class TestWatchAlertFlowControl:
    """Tests for the Clear/Watch/Alert red flag system in flow control."""

    @pytest.mark.asyncio
    async def test_watch_flag_does_not_override_llm(self, client):
        """When only a Watch-state flag is active, the LLM's question passes through."""
        flag = RedFlagConfig(
            id="meningitis_triad", name="Meningitis Triad",
            required_keys=["Fever"],
            at_least_one_of=["Neck_Stiffness", "Photophobia"],
            qualifiers={},
            message="Emergency.", severity="critical",
            soft_threshold=1, hard_threshold=4,
        )
        domain = _make_domain_with_flag(flag)
        state = create_initial_state("test")
        state["information_gathered"] = {"Fever": "yes"}
        state["remaining_gaps"] = ["Cough"]
        state["phase"] = Phase.EXPLORING
        state["intake_intent"] = PatientIntent.ANSWERING.value
        state["turn_count"] = 2

        result = await flow_control_node(state, client=client, domain=domain)

        assert result["conversation_move"].type == MoveType.QUESTION
        assert result["conversation_move"].target_gap == "Cough"
        assert "watch_flags" in result
        assert "meningitis_triad" in result["watch_flags"]

    @pytest.mark.asyncio
    async def test_alert_flag_overrides_llm(self, client):
        """When an Alert-state flag is active (but not fully confirmed), it overrides with TARGETED_CLARIFY."""
        flag = RedFlagConfig(
            id="meningitis_triad", name="Meningitis Triad",
            required_keys=["Fever"],
            at_least_one_of=["Neck_Stiffness", "Photophobia"],
            qualifiers={"Fever": ["high"]},
            message="Emergency.", severity="critical",
            soft_threshold=1, hard_threshold=2,
        )
        domain = _make_domain_with_flag(flag)
        state = create_initial_state("test")
        # score = 1 (required) + 1 (qualifier) = 2 >= hard=2 → Alert
        # But NO at_least_one_of present → not "confirmed" by legacy check
        state["information_gathered"] = {"Fever": "high fever"}
        state["remaining_gaps"] = ["Cough"]
        state["phase"] = Phase.EXPLORING
        state["intake_intent"] = PatientIntent.ANSWERING.value
        state["turn_count"] = 3

        result = await flow_control_node(state, client=client, domain=domain)

        assert result["conversation_move"].type == MoveType.TARGETED_CLARIFY
        assert result["conversation_move"].red_flag_id == "meningitis_triad"

    @pytest.mark.asyncio
    async def test_watch_timeout_promotes_to_alert(self, client):
        """After watch_turns_limit turns, a Watch flag promotes to Alert."""
        flag = RedFlagConfig(
            id="meningitis_triad", name="Meningitis Triad",
            required_keys=["Fever"],
            at_least_one_of=["Neck_Stiffness", "Photophobia"],
            qualifiers={},
            message="Emergency.", severity="critical",
            soft_threshold=1, hard_threshold=10,  # very high so it stays Watch normally
        )
        domain = _make_domain_with_flag(flag, watch_turns_limit=3)
        state = create_initial_state("test")
        state["information_gathered"] = {"Fever": "yes"}
        state["remaining_gaps"] = ["Cough"]
        state["phase"] = Phase.EXPLORING
        state["intake_intent"] = PatientIntent.ANSWERING.value
        state["turn_count"] = 5
        state["watch_flags"] = {
            "meningitis_triad": {"since_turn": 2, "score": 1, "missing_keys": ["Neck_Stiffness"]},
        }

        result = await flow_control_node(state, client=client, domain=domain)

        assert result["conversation_move"].type == MoveType.TARGETED_CLARIFY
        assert result["conversation_move"].red_flag_id == "meningitis_triad"
