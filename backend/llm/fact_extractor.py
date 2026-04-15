from __future__ import annotations

import json
import logging
import re
from typing import Any

from backend.config import settings
from backend.llm.client import AgentLLMClient
from backend.models.facts import FactConfidence, RawFact

logger = logging.getLogger(__name__)

_CALLER = "fact_extractor"

_SYSTEM = (
    "You are a clinical fact extractor. Extract ALL health-relevant facts "
    "from the patient's message as key-value pairs.\n\n"
    "Rules:\n"
    "- Use clear, concise clinical keys (e.g., 'Headache', 'Fever', "
    "'Neck_Stiffness', 'Age', 'Cough').\n"
    "- Use underscores for multi-word keys (e.g., 'Neck_Stiffness', not "
    "'Neck stiffness').\n"
    "- Capture the patient's own description as the value.\n"
    "- Set denied=true ONLY if the patient EXPLICITLY denies or negates a "
    "symptom (e.g., 'I don't have fever', 'no nausea'). Not mentioning a "
    "symptom is NOT the same as denying it.\n"
    "- Set confidence to 'high' if the patient clearly states the fact, "
    "'medium' if somewhat ambiguous, 'unclear' if very vague.\n"
    "- Do NOT return placeholder values like 'not specified' or 'N/A'.\n"
    "- If the patient didn't share any medical facts, return an empty array: []\n"
    "- Respond with a JSON array ONLY. No markdown fences.\n\n"
    "Output format:\n"
    '[{"key": "field_name", "value": "extracted_value", "denied": false, '
    '"confidence": "high"}]'
)

_PLACEHOLDER_VALUES = {
    "not specified", "not provided", "not mentioned", "n/a", "na",
    "none", "unknown", "not applicable", "not stated", "not given",
    "not reported", "not available",
}


async def extract_facts(
    client: AgentLLMClient,
    message: str,
    last_question_topic: str | None,
    information_gathered: dict[str, str],
) -> list[RawFact]:
    """Single LLM call to extract all clinical facts from the patient message."""
    if not message or not message.strip():
        return []

    context_topic = last_question_topic or "general health"
    info_summary = ", ".join(f"{k}: {v}" for k, v in information_gathered.items()) if information_gathered else "(none yet)"

    user_prompt = (
        f"The doctor just asked about: {context_topic}\n"
        f"Facts already gathered: {info_summary}\n\n"
        f"Patient message: {message}"
    )

    logger.info(
        "EXTRACT_REQ  message_len=%d  last_topic=%s  existing_facts=%d",
        len(message),
        last_question_topic or "(none)",
        len(information_gathered),
    )

    try:
        raw = await client.complete(
            system=_SYSTEM,
            user=user_prompt,
            max_tokens=settings.fact_extractor_max_tokens,
            temperature=0.0,
            caller=_CALLER,
        )

        logger.info("EXTRACT_RAW  response=%r", raw)
        parsed = _safe_json_parse(raw)
        facts = _parse_facts_json(parsed)
        facts = _filter_placeholders(facts)

        logger.info(
            "EXTRACT_OK  facts_count=%d  facts=%s",
            len(facts),
            [(f.key, f.value, f.confidence.value) for f in facts],
        )
        return facts

    except Exception:
        logger.exception("EXTRACT_FAIL  returning empty list")
        return []


def _filter_placeholders(facts: list[RawFact]) -> list[RawFact]:
    """Drop facts with placeholder values."""
    result = []
    for fact in facts:
        if fact.value.lower().strip() in _PLACEHOLDER_VALUES:
            logger.info(
                "EXTRACT_DROP  key=%r  value=%r  reason=placeholder_value",
                fact.key,
                fact.value,
            )
            continue
        result.append(fact)
    return result


# ── Internals ────────────────────────────────────────────────────────────

_CONFIDENCE_MAP = {
    "high": FactConfidence.HIGH,
    "medium": FactConfidence.MEDIUM,
    "unclear": FactConfidence.UNCLEAR,
}


def _safe_json_parse(raw: str) -> Any:
    """Parse JSON from LLM response, stripping markdown fences if present."""
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return json.loads(cleaned.strip())


def _parse_facts_json(raw: Any) -> list[RawFact]:
    """Convert parsed JSON into a list of RawFact objects."""
    items: list[dict] = []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = [raw]
    else:
        logger.warning("PARSE_FACTS  unexpected type %s", type(raw).__name__)
        return []

    facts: list[RawFact] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip()
        value = str(item.get("value", "")).strip()
        if not key:
            continue
        denied = bool(item.get("denied", False))
        conf_str = str(item.get("confidence", "high")).lower().strip()
        confidence = _CONFIDENCE_MAP.get(conf_str, FactConfidence.HIGH)
        facts.append(RawFact(key=key, value=value, denied=denied, confidence=confidence))

    return facts
