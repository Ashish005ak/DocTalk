from __future__ import annotations

import logging

from backend.clinical.fact_merger import merge_facts
from backend.clinical.red_flag_guard import RedFlagGuard
from backend.domain.models import DomainProfile
from backend.llm.client import AgentLLMClient
from backend.llm.clinical_reasoner import generate_reasoning
from backend.models.hypothesis import Hypothesis, HypothesisEntry
from backend.models.state import Confidence, ConsultationEnding, Phase

logger = logging.getLogger(__name__)

_RULED_OUT_THRESHOLD = 0.05


async def reason_node(
    state: dict,
    *,
    client: AgentLLMClient,
    domain: DomainProfile,
) -> dict:
    """Clinical reasoning: merge facts, check red flags, call LLM for differential diagnosis."""
    consultation_ending = state.get("consultation_ending", ConsultationEnding.NONE)
    if consultation_ending != ConsultationEnding.NONE:
        logger.info("REASON_SKIP  consultation_ending=%s  returning state unchanged", consultation_ending.value if hasattr(consultation_ending, "value") else consultation_ending)
        return {}

    intake_facts = state.get("intake_facts", [])
    info_gathered = dict(state.get("information_gathered", {}))
    denied_symptoms = set(state.get("denied_symptoms", set()))
    fact_confidence = dict(state.get("fact_confidence", {}))
    turn_count = state.get("turn_count", 0)
    old_phase = state.get("phase", Phase.INTAKE)
    unconfirmed = dict(state.get("unconfirmed_facts", {}))
    attempts = dict(state.get("clarification_attempts", {}))
    skipped_gaps = set(state.get("skipped_gaps", set()))

    logger.info(
        "REASON_ENTRY  turn=%d  phase=%s  intake_facts=%d  info_count=%d",
        turn_count,
        old_phase.value if hasattr(old_phase, "value") else old_phase,
        len(intake_facts),
        len(info_gathered),
    )

    # --- 1. Merge facts (deterministic, unchanged) ---
    (
        info_gathered,
        new_denied,
        fact_confidence,
        unconfirmed,
        attempts,
        _uncertain,
    ) = merge_facts(
        existing=info_gathered,
        new_facts=intake_facts,
        fact_confidence=fact_confidence,
        turn_count=turn_count,
        unconfirmed_facts=unconfirmed,
        clarification_attempts=attempts,
    )
    denied_symptoms = denied_symptoms | new_denied

    logger.info(
        "REASON_MERGE  new_denied=%s  info_count=%d  unconfirmed=%d",
        sorted(new_denied) if new_denied else "[]",
        len(info_gathered),
        len(unconfirmed),
    )

    # --- 2a. Score red flags → build Watch hints for the LLM ---
    guard = RedFlagGuard(domain)
    prev_watch = dict(state.get("watch_flags", {}))
    confirmed_rf_ids = set(state.get("confirmed_red_flag_ids", set()))

    alert_flags, watch_statuses, _clear = guard.check_with_states(
        info_gathered=info_gathered,
        denied_symptoms=denied_symptoms,
        confirmed_red_flag_ids=confirmed_rf_ids,
        current_turn=turn_count,
        prev_watch_flags=prev_watch,
    )

    watch_hints = ""
    if watch_statuses:
        hint_lines = ["Watch flags (screen when clinically appropriate):"]
        for ws in watch_statuses:
            missing_str = ", ".join(ws.missing_keys) if ws.missing_keys else "none"
            hint_lines.append(
                f"- {ws.rule.name} [{ws.rule.id}] [score: {ws.score}/{ws.hard_threshold}] "
                f"— Screen for {missing_str} when appropriate."
            )
        watch_hints = "\n".join(hint_lines)
        logger.info(
            "REASON_WATCH_HINTS  flags=%s  hint_len=%d",
            [ws.rule.id for ws in watch_statuses],
            len(watch_hints),
        )

    new_watch_flags: dict[str, dict] = {}
    for ws in watch_statuses:
        new_watch_flags[ws.rule.id] = {
            "score": ws.score,
            "since_turn": ws.watch_since_turn if ws.watch_since_turn is not None else turn_count,
            "missing_keys": ws.missing_keys,
        }

    # --- 2b. LLM clinical reasoning ---
    prev_hyp_data = None
    existing_hyp = state.get("hypothesis")
    if existing_hyp and existing_hyp.leading:
        prev_hyp_data = [
            {"name": existing_hyp.leading.name, "probability": existing_hyp.leading.score}
        ] + [
            {"name": d.name, "probability": d.score}
            for d in (existing_hyp.differential or [])
        ]

    prev_confidence = state.get("confidence", Confidence.LOW)
    prev_confidence_str = (
        prev_confidence.value if hasattr(prev_confidence, "value")
        else str(prev_confidence)
    )

    reasoning_state = {
        "information_gathered": info_gathered,
        "denied_symptoms": denied_symptoms,
        "turn_count": turn_count,
        "conversation_history": state.get("conversation_history", []),
        "watch_hints": watch_hints,
        "previous_hypothesis": prev_hyp_data,
        "previous_confidence": prev_confidence_str,
    }
    reasoning = await generate_reasoning(client, reasoning_state)

    # --- 3. Map LLM output to Hypothesis model ---
    entries = [
        HypothesisEntry(
            name=h.name,
            score=h.probability,
            supporting_evidence=h.supporting_evidence,
            missing_evidence=h.missing_evidence,
        )
        for h in reasoning.hypotheses
    ]

    leading = entries[0] if entries else None
    differential = [e for e in entries[1:] if e.score >= _RULED_OUT_THRESHOLD]
    ruled_out = [e for e in entries[1:] if e.score < _RULED_OUT_THRESHOLD]

    hypothesis = Hypothesis(
        leading=leading,
        differential=differential,
        ruled_out=ruled_out,
    )

    leading_name = leading.name if leading else "(none)"
    leading_score = leading.score if leading else 0.0

    logger.info(
        "REASON_HYPOTHESIS  leading=%s  score=%.3f  differential=%d  ruled_out=%d",
        leading_name,
        leading_score,
        len(differential),
        len(ruled_out),
    )

    # --- 4. Map LLM confidence to enum ---
    confidence_map = {
        "high": Confidence.HIGH,
        "moderate": Confidence.MODERATE,
        "low": Confidence.LOW,
    }
    confidence = confidence_map.get(reasoning.confidence, Confidence.LOW)

    # --- 5. Simplified phase logic ---
    max_turns = domain.thresholds.max_turns

    if turn_count >= max_turns:
        new_phase = Phase.SUMMARY
    elif reasoning.should_summarize and turn_count > 3:
        new_phase = Phase.SUMMARY
    elif turn_count == 0:
        new_phase = Phase.INTAKE
    elif confidence == Confidence.HIGH:
        new_phase = Phase.NARROWING
    elif confidence == Confidence.MODERATE:
        new_phase = Phase.NARROWING
    else:
        new_phase = Phase.EXPLORING

    if new_phase != old_phase:
        logger.info(
            "REASON_PHASE  transition  %s -> %s",
            old_phase.value if hasattr(old_phase, "value") else old_phase,
            new_phase.value,
        )

    # --- 6. Set remaining_gaps from LLM's next question ---
    if new_phase == Phase.SUMMARY or not reasoning.next_question:
        remaining_gaps = []
    else:
        remaining_gaps = [reasoning.next_question]

    if skipped_gaps:
        remaining_gaps = [g for g in remaining_gaps if g not in skipped_gaps]

    logger.info(
        "REASON_EXIT  phase=%s  info=%d  gaps=%s  hypothesis=%s(%.3f)  confidence=%s",
        new_phase.value,
        len(info_gathered),
        remaining_gaps,
        leading_name,
        leading_score,
        confidence.value,
    )

    # --- Track consecutive zero-fact turns for fatigue detection ---
    old_info_count = len(state.get("information_gathered", {}))
    new_facts_added = len(info_gathered) - old_info_count
    prev_zero = state.get("_consecutive_zero_fact_turns", 0)
    consecutive_zero = 0 if new_facts_added > 0 else prev_zero + 1

    result = {
        "information_gathered": info_gathered,
        "denied_symptoms": denied_symptoms,
        "fact_confidence": fact_confidence,
        "unconfirmed_facts": unconfirmed,
        "clarification_attempts": attempts,
        "hypothesis": hypothesis,
        "confidence": confidence,
        "remaining_gaps": remaining_gaps,
        "phase": new_phase,
        "question_rationale": reasoning.question_rationale,
        "_consecutive_zero_fact_turns": consecutive_zero,
        "watch_flags": new_watch_flags,
    }

    # --- Natural completion trigger ---
    if confidence == Confidence.HIGH and not remaining_gaps and turn_count > 3:
        from backend.clinical.readiness import is_ready_to_land
        if is_ready_to_land(state | result, "natural"):
            logger.info("REASON_NATURAL_COMPLETION  confidence=HIGH  gaps=0  triggering LANDING")
            result["consultation_ending"] = ConsultationEnding.LANDING
            result["closing_turn_count"] = 0
            result["remaining_gaps"] = []

    return result
