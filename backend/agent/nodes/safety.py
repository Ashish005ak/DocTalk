from __future__ import annotations

import logging

from backend.config import settings
from backend.domain.models import DomainProfile
from backend.llm.client import AgentLLMClient
from backend.models.state import ConsultationEnding
from backend.models.utterance import Utterance
from backend.safety.dedup_checker import extract_question_sentences, is_duplicate_question
from backend.safety.jargon_replacer import replace_jargon
from backend.safety.validator import (
    empty_response_guard,
    has_acknowledgment_opener,
    strip_banned_openings,
    strip_first_sentence,
)

logger = logging.getLogger(__name__)

_ESCALATION_SYSTEM = (
    "You are a patient-safety reviewer. Given a list of raw clinical "
    "observations and any candidate red-flag IDs, decide whether anything "
    "warrants immediate medical escalation.\n\n"
    "Reply ONLY with YES or NO on the first line, followed by a one-line "
    "reason on the second line. Nothing else."
)
_ESCALATION_CALLER = "safety.escalation_check"

_CONSECUTIVE_ACK_LIMIT = 2


async def safety_node(
    state: dict,
    *,
    client: AgentLLMClient,
    domain: DomainProfile,
) -> dict:
    """Deterministic post-processing: strip banned openers, jargon, dedup, guard empty."""
    consultation_ending = state.get("consultation_ending", ConsultationEnding.NONE)

    if consultation_ending == ConsultationEnding.CLOSED:
        text = state.get("doctor_response", "")
        message = state.get("patient_message", "")
        turn = state.get("turn_count", 0)
        logger.info("SAFETY_SKIP_CLOSED  passing through terminate response")
        patient_utt = Utterance(speaker="patient", text=message, turn=turn)
        doctor_utt = Utterance(speaker="doctor", text=text, turn=turn)
        return {
            "doctor_response": text,
            "conversation_history": [patient_utt, doctor_utt],
            "turn_count": turn + 1,
            "intake_facts": [],
            "intake_intent": "answering",
            "pending_explanation": None,
        }

    text = state.get("doctor_response", "")
    message = state.get("patient_message", "")
    turn = state.get("turn_count", 0)
    questions_asked = list(state.get("questions_asked", []))
    move = state.get("conversation_move")
    consecutive_ack = state.get("_consecutive_ack_count", 0)

    logger.info(
        "SAFETY_ENTRY  response_len=%d  turn=%d  questions_asked=%d",
        len(text),
        turn,
        len(questions_asked),
    )

    # 1. Strip banned openings
    cleaned = strip_banned_openings(text)
    if cleaned != text:
        logger.info("SAFETY_BANNED  stripped_opener  original_len=%d  new_len=%d", len(text), len(cleaned))

    # 2. Jargon replacement
    cleaned, replaced_terms = replace_jargon(cleaned, domain.jargon_map)
    if replaced_terms:
        logger.info("SAFETY_JARGON  replaced=%s", replaced_terms)

    # 3. Opener throttle — if too many consecutive acknowledgments, strip first sentence
    if has_acknowledgment_opener(cleaned):
        consecutive_ack += 1
        if consecutive_ack >= _CONSECUTIVE_ACK_LIMIT:
            before = cleaned
            cleaned = strip_first_sentence(cleaned)
            if cleaned != before:
                logger.info("SAFETY_THROTTLE  stripped_ack  consecutive=%d", consecutive_ack)
            consecutive_ack = 0
    else:
        consecutive_ack = 0

    # 4. Dedup check — rephrase using domain-configured fallback templates
    is_dup = is_duplicate_question(cleaned, questions_asked)
    if is_dup:
        logger.warning("SAFETY_DEDUP  duplicate_detected  response_len=%d", len(cleaned))
        target_gap = None
        if move and hasattr(move, "target_gap"):
            target_gap = move.target_gap
        if target_gap:
            hint = domain.get_field_hint(target_gap) or ""
            hint_suffix = f" — {hint.lower()}" if hint else ""
            cleaned = domain.dedup_fallback.with_target.format(
                target_gap=target_gap.lower().replace("_", " "),
                hint_suffix=hint_suffix,
            )
        else:
            cleaned = domain.dedup_fallback.without_target

    # 5. LLM escalation check against all gathered clinical information
    #    Skip during LANDING/EMERGENCY — the summary already handles urgency.
    all_info = state.get("information_gathered", {})
    is_landing = consultation_ending in (ConsultationEnding.LANDING, ConsultationEnding.EMERGENCY)
    if all_info and not is_landing:
        logger.info(
            "SAFETY_ESCALATION_CHECK  info_count=%d  keys=%s",
            len(all_info),
            list(all_info.keys()),
        )
        candidate_rf = ""
        if move and hasattr(move, "red_flag_id") and move.red_flag_id:
            candidate_rf = f"Candidate red flag: {move.red_flag_id}"

        info_lines = "\n".join(f"- {k}: {v}" for k, v in all_info.items())
        escalation_prompt = (
            f"Patient observations:\n{info_lines}\n\n"
            f"{candidate_rf}"
        )

        try:
            escalation_raw = await client.complete(
                system=_ESCALATION_SYSTEM,
                user=escalation_prompt,
                max_tokens=60,
                temperature=0.0,
                caller=_ESCALATION_CALLER,
            )
            escalation_lines = escalation_raw.strip().splitlines()
            decision = escalation_lines[0].strip().upper() if escalation_lines else "NO"
            reason = escalation_lines[1].strip() if len(escalation_lines) > 1 else ""

            logger.info(
                "SAFETY_ESCALATION_RESULT  decision=%s  reason=%r",
                decision,
                reason,
            )

            if decision == "YES":
                warning = (
                    f"\n\n⚠️ IMPORTANT: Based on what you've described, "
                    f"I recommend seeking immediate medical attention. {reason}"
                )
                cleaned = cleaned + warning
                logger.warning(
                    "SAFETY_ESCALATION_TRIGGERED  appended_warning  reason=%r",
                    reason,
                )
        except Exception:
            logger.exception("SAFETY_ESCALATION_FAIL  skipping escalation check")

    # 6. Empty response guard
    cleaned = empty_response_guard(cleaned)

    # 7. Build conversation history entries
    patient_utt = Utterance(speaker="patient", text=message, turn=turn)
    doctor_utt = Utterance(speaker="doctor", text=cleaned, turn=turn)

    # 8. Extract question sentences — only return *new* ones to avoid
    #    exponential growth from the _append_list reducer in the state graph.
    new_questions = extract_question_sentences(cleaned)
    already_asked = set(q.lower().strip() for q in questions_asked)
    deduplicated_new = [
        q for q in new_questions
        if q.lower().strip() not in already_asked
    ]

    # 9. Determine last_question_asked
    last_question = None
    if move and hasattr(move, "target_gap"):
        last_question = move.target_gap

    logger.info(
        "SAFETY_EXIT  final_len=%d  turn=%d  new_questions=%d  last_question=%s",
        len(cleaned),
        turn + 1,
        len(deduplicated_new),
        last_question or "(none)",
    )

    return {
        "doctor_response": cleaned,
        "conversation_history": [patient_utt, doctor_utt],
        "questions_asked": deduplicated_new,
        "last_question_asked": last_question,
        "turn_count": turn + 1,
        "intake_facts": [],
        "intake_intent": "answering",
        "pending_explanation": None,
        "_consecutive_ack_count": consecutive_ack,
    }
