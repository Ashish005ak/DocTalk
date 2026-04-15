from __future__ import annotations

import logging

from backend.domain.models import DomainProfile
from backend.llm.client import AgentLLMClient
from backend.models.move import ConversationMove
from backend.models.state import MoveType
from backend.models.utterance import Utterance

logger = logging.getLogger(__name__)

_EMERGENCY_RESPONSE = (
    "Please call emergency services immediately. If you're having chest pain, "
    "difficulty breathing, or feel you're in danger, call 911 (or your local "
    "emergency number) right now. Your safety is the top priority."
)


async def crisis_node(
    state: dict,
    *,
    client: AgentLLMClient,
    domain: DomainProfile,
) -> dict:
    """Return a hardcoded emergency response -- no LLM call."""
    message = state.get("patient_message", "")
    turn = state.get("turn_count", 0)

    logger.warning(
        "CRISIS_TRIGGERED  turn=%d  message_len=%d",
        turn,
        len(message),
    )

    move = ConversationMove(type=MoveType.CRISIS_RESPONSE)

    patient_utt = Utterance(speaker="patient", text=message, turn=turn)
    doctor_utt = Utterance(speaker="doctor", text=_EMERGENCY_RESPONSE, turn=turn)

    logger.info(
        "CRISIS_EXIT  response_len=%d  turn=%d",
        len(_EMERGENCY_RESPONSE),
        turn + 1,
    )

    return {
        "doctor_response": _EMERGENCY_RESPONSE,
        "conversation_move": move,
        "conversation_history": [patient_utt, doctor_utt],
        "turn_count": turn + 1,
    }
