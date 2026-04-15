from __future__ import annotations

import logging

from backend.config import settings
from backend.llm.client import AgentLLMClient
from backend.models.state import PatientIntent

logger = logging.getLogger(__name__)

_CALLER = "intent_classifier"

_VALID_INTENTS = {v.value for v in PatientIntent}

_SYSTEM_PROMPT = (
    "You are a clinical intent classifier. Given the patient's message and "
    "the last question the doctor asked, classify the patient's intent as "
    "exactly ONE of these words:\n"
    "  answering, asking_clarification, asking_explanation, "
    "expressing_concern, mixed, greeting, crisis, terminate\n\n"
    "Rules:\n"
    "- Respond with a SINGLE word only — no punctuation, no explanation.\n"
    "- If the patient is answering a clinical question, reply 'answering'.\n"
    "- If the patient asks what a term means or why something was asked, "
    "reply 'asking_explanation'.\n"
    "- If the patient wants a previous answer clarified, reply 'asking_clarification'.\n"
    "- If the patient expresses worry, fear, or frustration, reply 'expressing_concern'.\n"
    "- If the message contains both an answer and a question/concern, reply 'mixed'.\n"
    "- If the patient says hello or similar, reply 'greeting'.\n"
    "- If the patient mentions self-harm, suicide, or an immediate emergency, reply 'crisis'.\n"
    "- If the patient signals they are done — e.g. 'thank you', 'that helps', "
    "'okay I understand', 'I'll go now', 'bye', 'thanks doc' — reply 'terminate'."
)

_FALLBACK = PatientIntent.ANSWERING


async def classify_intent(
    client: AgentLLMClient,
    message: str,
    last_gap: str | None = None,
) -> PatientIntent:
    """Classify the patient's conversational intent.

    Returns PatientIntent.ANSWERING as a safe fallback on any failure.
    """
    context = f"Last question asked: {last_gap}" if last_gap else "No previous question."
    user_prompt = f"{context}\n\nPatient message: {message}"

    logger.info(
        "INTENT_REQ  message_len=%d  last_gap=%s",
        len(message),
        last_gap or "(none)",
    )

    try:
        raw = await client.complete(
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=settings.intent_classifier_max_tokens,
            temperature=0.0,
            caller=_CALLER,
        )

        parsed = raw.strip().lower().replace('"', "").replace("'", "")
        logger.info(
            "INTENT_RAW  raw_response=%r  parsed=%r",
            raw,
            parsed,
        )

        if parsed in _VALID_INTENTS:
            result = PatientIntent(parsed)
            logger.info("INTENT_OK  result=%s", result.value)
            return result

        logger.warning(
            "INTENT_UNRECOGNIZED  raw=%r  parsed=%r  fallback=%s",
            raw,
            parsed,
            _FALLBACK.value,
        )
        return _FALLBACK

    except Exception:
        logger.exception("INTENT_FAIL  fallback=%s", _FALLBACK.value)
        return _FALLBACK
