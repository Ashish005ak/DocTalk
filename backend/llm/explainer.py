from __future__ import annotations

import logging

from backend.config import settings
from backend.domain.models import DomainProfile
from backend.llm.client import AgentLLMClient

logger = logging.getLogger(__name__)

_CALLER = "explainer"

_FALLBACK = (
    "That's a good question. Let me continue with the consultation "
    "to help you better."
)

_SYSTEM_PROMPT = (
    "You are a compassionate medical assistant explaining clinical reasoning "
    "to a patient in plain language.\n\n"
    "Your task:\n"
    "1. Directly answer the patient's question. This may be about why "
    "something was asked, what a symptom might mean, how serious a "
    "condition could be, or what treatment options typically exist.\n"
    "2. If a 'Next topic' is provided, bridge naturally into that topic. "
    "If no next topic is provided, end with a warm, reassuring closing "
    "remark. Do NOT invent a new question.\n\n"
    "Rules:\n"
    "- Use simple, non-technical language.\n"
    "- Be reassuring but honest.\n"
    "- Keep the explanation under 4 sentences.\n"
    "- Do not state a definitive diagnosis, but you may discuss likely "
    "conditions, general prognosis, and common treatment approaches "
    "based on the information gathered.\n"
    "- If the patient asks about severity or treatment, answer based on "
    "the gathered information and the current hypothesis."
)


async def generate_explanation(
    client: AgentLLMClient,
    state: dict,
    domain: DomainProfile,
) -> str:
    """Generate an explanation for the patient's pending question,
    then bridge to the next clinical question.

    Returns a fallback string on any failure or empty response.
    """
    pending = state.get("pending_explanation", "")
    info = state.get("information_gathered", {})
    gaps = state.get("remaining_gaps", [])
    next_gap = gaps[0] if gaps else None
    next_hint = domain.get_field_hint(next_gap) if next_gap else None

    hypothesis = state.get("hypothesis")
    hyp_context = "(no hypothesis yet)"
    if hypothesis and hypothesis.leading:
        parts = [f"Leading: {hypothesis.leading.name} ({hypothesis.leading.score:.0%})"]
        for d in (hypothesis.differential or []):
            parts.append(f"  Differential: {d.name} ({d.score:.0%})")
        hyp_context = "\n".join(parts)

    user_prompt = (
        f"Patient's question: {pending}\n"
        f"Information gathered so far: {info}\n"
        f"Current assessment:\n{hyp_context}\n"
        f"Next topic to ask about: {next_gap or '(none -- consultation is wrapping up)'}\n"
        f"Hint for next topic: {next_hint or '(none)'}"
    )

    logger.info(
        "EXPLAIN_REQ  pending=%r  info_count=%d  next_gap=%s",
        pending,
        len(info),
        next_gap or "(none)",
    )

    try:
        raw = await client.complete(
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=settings.explainer_max_tokens,
            temperature=0.3,
            caller=_CALLER,
        )

        logger.info("EXPLAIN_RAW  response=%r", raw)

        if not raw or not raw.strip():
            logger.warning("EXPLAIN_EMPTY  using fallback")
            return _FALLBACK

        logger.info("EXPLAIN_OK  response_len=%d", len(raw))
        return raw.strip()

    except Exception:
        logger.exception("EXPLAIN_FAIL  using fallback")
        return _FALLBACK
