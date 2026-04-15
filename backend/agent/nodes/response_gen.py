from __future__ import annotations

import logging

from backend.domain.models import DomainProfile
from backend.llm.client import AgentLLMClient
from backend.llm.explainer import generate_explanation
from backend.llm.response_generator import generate_question
from backend.llm.summarizer import generate_emergency_summary, generate_summary
from backend.models.move import ConversationMove
from backend.models.state import ConsultationEnding, MoveType, PatientIntent

logger = logging.getLogger(__name__)

_TERMINATE_TEMPLATE = "Thank you{name_part} for sharing this with me. Take care of yourself, and don't hesitate to seek medical help if anything changes. Goodbye."


async def response_gen_node(
    state: dict,
    *,
    client: AgentLLMClient,
    domain: DomainProfile,
) -> dict:
    """Generate the doctor's response by routing to the appropriate LLM caller."""
    move: ConversationMove = state.get("conversation_move")
    pending = state.get("pending_explanation")
    intent_str = state.get("intake_intent", PatientIntent.ANSWERING.value)

    move_type = move.type if move else MoveType.QUESTION

    logger.info(
        "RESPONSE_GEN_ENTRY  move_type=%s  pending_explanation=%s  intent=%s",
        move_type.value,
        pending is not None,
        intent_str,
    )

    was_blended = False

    if move_type == MoveType.TERMINATE:
        patient_name = state.get("information_gathered", {}).get("patient_name", "")
        name_part = f", {patient_name}," if patient_name else ""
        response = _TERMINATE_TEMPLATE.format(name_part=name_part)
        logger.info("RESPONSE_GEN_TERMINATE  template-based  len=%d", len(response))
        return {
            "doctor_response": response,
            "consultation_ending": ConsultationEnding.CLOSED,
        }

    if move_type == MoveType.URGENT_CLOSE:
        response = await generate_emergency_summary(client, state, domain)
        logger.info("RESPONSE_GEN_URGENT_CLOSE  len=%d", len(response))
        return {
            "doctor_response": response,
            "summary_generated": True,
        }

    if move_type == MoveType.SUMMARIZE:
        response = await generate_summary(client, state, domain)
        return {
            "doctor_response": response,
            "summary_generated": True,
        }

    if move_type == MoveType.EXPLAIN:
        response = await generate_explanation(client, state, domain)
        if intent_str == PatientIntent.MIXED.value and move and move.target_gap:
            question = await generate_question(client, state, domain, move)
            response = f"{response}\n\n{question}"
            was_blended = True

    else:
        response = await generate_question(client, state, domain, move)

    logger.info(
        "RESPONSE_GEN_EXIT  response_len=%d  was_blended=%s",
        len(response),
        was_blended,
    )

    return {"doctor_response": response}
