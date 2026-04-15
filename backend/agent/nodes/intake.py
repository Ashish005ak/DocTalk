from __future__ import annotations

import asyncio
import logging

from backend.domain.models import DomainProfile
from backend.llm.client import AgentLLMClient
from backend.llm.fact_extractor import extract_facts
from backend.llm.intent_classifier import classify_intent
from backend.models.state import PatientIntent

logger = logging.getLogger(__name__)


async def intake_node(
    state: dict,
    *,
    client: AgentLLMClient,
    domain: DomainProfile,
) -> dict:
    """Classify intent and extract facts from the patient message in parallel."""
    message = state.get("patient_message", "")
    last_gap = state.get("last_question_asked")
    info_gathered = state.get("information_gathered", {})

    logger.info(
        "INTAKE_ENTRY  message_len=%d  last_gap=%s  existing_facts=%d",
        len(message),
        last_gap or "(none)",
        len(info_gathered),
    )

    # Two parallel LLM calls: intent classification + fact extraction
    intent_task = classify_intent(client, message, last_gap)
    extract_task = extract_facts(client, message, last_gap, info_gathered)

    intent, facts = await asyncio.gather(intent_task, extract_task)

    logger.info(
        "INTAKE_INTENT  result=%s",
        intent.value,
    )
    logger.info(
        "INTAKE_FACTS  count=%d  keys=%s",
        len(facts),
        [f.key for f in facts],
    )

    # Identify volunteered keys (facts beyond what was asked about)
    asked_key = last_gap.lower() if last_gap else ""
    new_volunteered_keys = [
        f.key for f in facts
        if f.key.lower() != asked_key
        and f.key not in info_gathered
        and not f.denied
    ]

    result: dict = {
        "patient_message": message,
        "intake_intent": intent.value,
        "intake_facts": facts,
        "new_volunteered_keys": new_volunteered_keys,
    }

    if intent == PatientIntent.ASKING_EXPLANATION:
        result["intake_facts"] = []
        result["pending_explanation"] = message
        logger.info("INTAKE_EXPLANATION  discarded_facts  pending_set")

    elif intent == PatientIntent.MIXED:
        result["pending_explanation"] = message
        logger.info("INTAKE_MIXED  kept_facts=%d  pending_set", len(facts))

    else:
        result["pending_explanation"] = None

    logger.info(
        "INTAKE_EXIT  intent=%s  fact_count=%d  volunteered=%d  pending_explanation=%s",
        intent.value,
        len(result["intake_facts"]),
        len(new_volunteered_keys),
        result.get("pending_explanation") is not None,
    )

    return result
