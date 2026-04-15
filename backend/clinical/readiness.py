from __future__ import annotations

import logging

from backend.models.state import Confidence

logger = logging.getLogger(__name__)

_CHIEF_COMPLAINT_KEYS = {"chief_complaint", "main_symptom", "primary_symptom", "symptoms"}

_MIN_TURNS_FOR_NATURAL = 3


def _has_chief_complaint(info: dict[str, str]) -> bool:
    info_lower = {k.lower() for k in info}
    return bool(info_lower & _CHIEF_COMPLAINT_KEYS) or len(info) >= 2


def _has_hypothesis(state: dict) -> bool:
    hyp = state.get("hypothesis")
    if hyp is None:
        return False
    return hyp.leading is not None


def is_ready_to_land(state: dict, trigger: str) -> bool:
    """Determine whether the consultation has gathered enough to produce a meaningful summary.

    trigger must be one of: "emergency", "natural", "fatigue".
    Returns True if the readiness bar for the given trigger type is met.
    """
    info = state.get("information_gathered", {})

    if trigger == "emergency":
        return _has_chief_complaint(info) and _has_hypothesis(state)

    if trigger == "natural":
        turn_count = state.get("turn_count", 0)
        if turn_count <= _MIN_TURNS_FOR_NATURAL:
            return False
        confidence = state.get("confidence", Confidence.LOW)
        if hasattr(confidence, "value"):
            confidence = confidence.value
        if confidence != Confidence.HIGH.value:
            return False
        remaining_gaps = state.get("remaining_gaps", [])
        if remaining_gaps:
            return False
        return _has_chief_complaint(info) and _has_hypothesis(state)

    if trigger == "fatigue":
        return _has_chief_complaint(info) and _has_hypothesis(state)

    logger.warning("READINESS_UNKNOWN_TRIGGER  trigger=%s", trigger)
    return False
