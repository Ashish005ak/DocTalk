from __future__ import annotations

import logging

from backend.models.state import PatientIntent

logger = logging.getLogger(__name__)


def route_after_intake(state: dict) -> str:
    """Conditional edge: CRISIS intent goes to crisis node, everything else continues linearly."""
    intent = state.get("intake_intent", "answering")

    if intent == PatientIntent.CRISIS.value:
        logger.warning("ROUTE_DECISION  intent=%s  destination=crisis", intent)
        return "crisis"

    logger.info("ROUTE_DECISION  intent=%s  destination=reason", intent)
    return "reason"
