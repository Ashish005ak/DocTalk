from __future__ import annotations

import logging

from backend.config import settings
from backend.domain.models import DomainProfile
from backend.llm.client import AgentLLMClient
from backend.llm.explainer import generate_explanation
from backend.models.move import ConversationMove
from backend.models.state import MoveType

logger = logging.getLogger(__name__)

_CALLER = "response_generator"

_FALLBACK = "Can you tell me more about that?"

_QUESTION_SYSTEM = (
    "You are a compassionate doctor conducting a medical consultation. "
    "Ask the patient about the specified symptom in a natural, conversational way.\n\n"
    "Rules:\n"
    "- Ask ONE clear question at a time.\n"
    "- Use simple, non-medical language.\n"
    "- Be warm and empathetic.\n"
    "- If a hint or rationale is provided, use it to frame the question appropriately.\n"
    "- Do NOT diagnose or speculate."
)

_CLARIFY_SYSTEM = (
    "You are a compassionate doctor who needs to clarify a previous answer. "
    "The patient's earlier response was ambiguous.\n\n"
    "Rules:\n"
    "- Politely ask for clarification on the specific topic.\n"
    "- Reference what they said before if helpful.\n"
    "- Ask ONE clear question.\n"
    "- Use simple language."
)

_RED_FLAG_SYSTEM = (
    "You are a doctor who has detected a potentially serious symptom. "
    "Ask an urgent follow-up question about it.\n\n"
    "Rules:\n"
    "- Be direct but not alarming.\n"
    "- Ask about the specific red-flag symptom.\n"
    "- Convey appropriate urgency without causing panic.\n"
    "- Ask ONE clear question."
)

_CONCERN_SYSTEM = (
    "You are a compassionate doctor acknowledging a patient's emotional concern.\n\n"
    "Rules:\n"
    "- Validate their feelings.\n"
    "- Be empathetic and reassuring.\n"
    "- Gently guide back to the consultation.\n"
    "- Keep it brief — 1-2 sentences of acknowledgment, then transition."
)


async def generate_question(
    client: AgentLLMClient,
    state: dict,
    domain: DomainProfile,
    move: ConversationMove,
) -> str:
    """Generate a doctor response based on the conversation move."""
    logger.info(
        "RESPONSE_REQ  move_type=%s  target_gap=%s  red_flag_id=%s",
        move.type.value,
        move.target_gap or "(none)",
        move.red_flag_id or "(none)",
    )

    try:
        if move.type == MoveType.EXPLAIN:
            result = await generate_explanation(client, state, domain)
            logger.info("RESPONSE_OK  delegated_to=explainer  len=%d", len(result))
            return result

        system, user_prompt = _build_prompt(state, domain, move)

        raw = await client.complete(
            system=system,
            user=user_prompt,
            max_tokens=settings.response_generator_max_tokens,
            temperature=0.3,
            caller=_CALLER,
        )

        logger.info("RESPONSE_RAW  response=%r", raw)

        if not raw or not raw.strip():
            logger.warning("RESPONSE_EMPTY  using fallback")
            return _FALLBACK

        logger.info("RESPONSE_OK  move_type=%s  len=%d", move.type.value, len(raw))
        return raw.strip()

    except Exception:
        logger.exception("RESPONSE_FAIL  using fallback")
        return _FALLBACK


def _build_prompt(
    state: dict,
    domain: DomainProfile,
    move: ConversationMove,
) -> tuple[str, str]:
    info = state.get("information_gathered", {})
    tone = state.get("emotional_tone", "neutral")
    if hasattr(tone, "value"):
        tone = tone.value

    question_rationale = state.get("question_rationale", "")

    if move.type in (MoveType.QUESTION, MoveType.CLARIFY, MoveType.TARGETED_CLARIFY):
        gap = move.target_gap or "general symptoms"
        hint = domain.get_field_hint(gap) or ""
        system = _CLARIFY_SYSTEM if move.type in (MoveType.CLARIFY, MoveType.TARGETED_CLARIFY) else _QUESTION_SYSTEM

        rationale_line = ""
        if question_rationale:
            rationale_line = f"\nClinical rationale for this question: {question_rationale}"

        user_prompt = (
            f"Topic to ask about: {gap}\n"
            f"Field hint: {hint}\n"
            f"Information gathered so far: {info}\n"
            f"Patient's emotional tone: {tone}"
            f"{rationale_line}"
        )
        return system, user_prompt

    if move.type == MoveType.RED_FLAG_FOLLOWUP:
        flag_id = move.red_flag_id or "unknown"
        user_prompt = (
            f"Red flag detected: {flag_id}\n"
            f"Information gathered so far: {info}\n"
            f"Patient's emotional tone: {tone}"
        )
        return _RED_FLAG_SYSTEM, user_prompt

    if move.type == MoveType.ACKNOWLEDGE_CONCERN:
        user_prompt = (
            f"Patient's emotional tone: {tone}\n"
            f"Information gathered so far: {info}\n"
            f"Reason for concern: {move.reason}"
        )
        return _CONCERN_SYSTEM, user_prompt

    user_prompt = (
        f"Continue the consultation.\n"
        f"Information gathered: {info}\n"
        f"Emotional tone: {tone}"
    )
    return _QUESTION_SYSTEM, user_prompt
