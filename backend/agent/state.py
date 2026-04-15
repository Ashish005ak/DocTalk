from __future__ import annotations

from typing import Annotated, Any

from langgraph.graph import add_messages

from backend.models.hypothesis import Hypothesis
from backend.models.move import ConversationMove
from backend.models.state import Confidence, ConsultationEnding, EmotionalTone, Phase
from backend.models.utterance import Utterance


def _replace(existing: Any, new: Any) -> Any:
    return new


def _merge_dict(existing: dict, new: dict) -> dict:
    merged = dict(existing)
    merged.update(new)
    return merged


def _union_set(existing: set, new: set) -> set:
    return existing | new


def _append_list(existing: list, new: list) -> list:
    return existing + new


class ClinicalState:
    """LangGraph state definition for a clinical consultation."""

    # Input from the current turn
    patient_message: Annotated[str, _replace]

    # Domain configuration
    domain_id: Annotated[str, _replace]

    # Consultation phase and turn tracking
    phase: Annotated[Phase, _replace]
    turn_count: Annotated[int, _replace]

    # Clinical facts gathered so far (key -> value)
    information_gathered: Annotated[dict[str, str], _merge_dict]
    denied_symptoms: Annotated[set[str], _union_set]

    # Hypothesis state
    hypothesis: Annotated[Hypothesis | None, _replace]
    confidence: Annotated[Confidence, _replace]

    # LLM-chosen next question topic(s)
    remaining_gaps: Annotated[list[str], _replace]

    # Conversation history
    conversation_history: Annotated[list[Utterance], _append_list]
    questions_asked: Annotated[list[str], _append_list]

    # Red flag tracking
    confirmed_red_flag_ids: Annotated[set[str], _union_set]
    last_rf_check_fact_snapshot: Annotated[dict[str, str], _replace]

    # Current turn outputs
    doctor_response: Annotated[str, _replace]
    conversation_move: Annotated[ConversationMove | None, _replace]
    emotional_tone: Annotated[EmotionalTone, _replace]

    # Explanation tracking
    explanations_given: Annotated[list[str], _append_list]
    pending_explanation: Annotated[str | None, _replace]

    # Context for targeted slot filling
    last_question_asked: Annotated[str | None, _replace]

    # Per-field extraction confidence (key -> "high"/"medium"/"unclear")
    fact_confidence: Annotated[dict[str, str], _merge_dict]

    # Medium-confidence extractions awaiting confirmation
    unconfirmed_facts: Annotated[dict[str, str], _replace]

    # Per-field clarification attempt counter (max 2)
    clarification_attempts: Annotated[dict[str, int], _merge_dict]

    # Per-gap ask counter
    gap_ask_counts: Annotated[dict[str, int], _merge_dict]

    # Watch-state red flags: flag_id -> {"score": int, "since_turn": int, "missing_keys": list}
    watch_flags: Annotated[dict[str, dict], _replace]

    # Gaps that have been permanently skipped after too many retries
    skipped_gaps: Annotated[set[str], _union_set]

    # Newly volunteered fact keys this turn (for acknowledgment)
    new_volunteered_keys: Annotated[list[str], _replace]

    # Inter-node communication (set by intake, consumed by reason/flow_control)
    intake_facts: Annotated[list, _replace]
    intake_intent: Annotated[str, _replace]

    # LLM reasoning rationale for the chosen next question
    question_rationale: Annotated[str, _replace]

    # Consultation ending state (one-way door: NONE -> LANDING/EMERGENCY -> CLOSED)
    consultation_ending: Annotated[ConsultationEnding, _replace]
    closing_turn_count: Annotated[int, _replace]
    summary_generated: Annotated[bool, _replace]

    # Fatigue detection: consecutive turns with zero new confirmed facts
    _consecutive_zero_fact_turns: Annotated[int, _replace]


def create_initial_state(domain_id: str) -> dict:
    """Create the initial state dict for a new consultation session."""
    return {
        "patient_message": "",
        "domain_id": domain_id,
        "phase": Phase.INTAKE,
        "turn_count": 0,
        "information_gathered": {},
        "denied_symptoms": set(),
        "hypothesis": None,
        "confidence": Confidence.LOW,
        "remaining_gaps": [],
        "conversation_history": [],
        "questions_asked": [],
        "confirmed_red_flag_ids": set(),
        "last_rf_check_fact_snapshot": {},
        "doctor_response": "",
        "conversation_move": None,
        "emotional_tone": EmotionalTone.NEUTRAL,
        "explanations_given": [],
        "pending_explanation": None,
        "last_question_asked": None,
        "fact_confidence": {},
        "unconfirmed_facts": {},
        "clarification_attempts": {},
        "gap_ask_counts": {},
        "watch_flags": {},
        "skipped_gaps": set(),
        "new_volunteered_keys": [],
        "intake_facts": [],
        "intake_intent": "answering",
        "question_rationale": "",
        "consultation_ending": ConsultationEnding.NONE,
        "closing_turn_count": 0,
        "summary_generated": False,
        "_consecutive_zero_fact_turns": 0,
    }
