from __future__ import annotations

import logging

from backend.config import settings
from backend.domain.models import DomainProfile
from backend.llm.client import AgentLLMClient

logger = logging.getLogger(__name__)

_CALLER = "summarizer"

_DISCLAIMER = (
    "\n\n---\n"
    "IMPORTANT DISCLAIMER: This is an AI-assisted preliminary assessment only. "
    "It is NOT a medical diagnosis. Please consult a qualified healthcare "
    "professional for proper evaluation and treatment."
)

_FALLBACK = (
    "Summary could not be generated at this time." + _DISCLAIMER
)

_SYSTEM_PROMPT = (
    "You are a medical documentation assistant generating a structured "
    "consultation summary.\n\n"
    "Generate a summary with these EXACT sections:\n"
    "## Symptoms Reported\n"
    "## Key Findings\n"
    "## Possible Conditions\n"
    "## Recommended Next Steps\n\n"
    "Rules:\n"
    "- Use bullet points within each section.\n"
    "- Be factual — only include what was actually reported.\n"
    "- For 'Possible Conditions', list the leading hypothesis and differentials "
    "with their confidence levels.\n"
    "- 'Recommended Next Steps' should suggest appropriate medical follow-up.\n"
    "- Do NOT include any disclaimer — that will be added separately.\n"
    "- Use plain language the patient can understand."
)


async def generate_summary(
    client: AgentLLMClient,
    state: dict,
    domain: DomainProfile,
) -> str:
    """Generate a structured consultation summary with a hardcoded disclaimer.

    The disclaimer is always appended and cannot be skipped or overridden
    by the LLM.
    """
    info = state.get("information_gathered", {})
    denied = state.get("denied_symptoms", set())
    hypothesis = state.get("hypothesis")
    red_flags = state.get("confirmed_red_flag_ids", set())
    hyp_summary = _format_hypothesis(hypothesis)
    denied_list = ", ".join(sorted(denied)) if denied else "(none)"
    red_flag_list = ", ".join(sorted(red_flags)) if red_flags else "(none)"

    user_prompt = (
        f"Information gathered:\n{_format_info(info)}\n\n"
        f"Denied symptoms: {denied_list}\n\n"
        f"Hypothesis analysis:\n{hyp_summary}\n\n"
        f"Confirmed red flags: {red_flag_list}"
    )

    logger.info(
        "SUMMARY_REQ  info_count=%d  denied_count=%d  red_flags=%s  "
        "has_hypothesis=%s",
        len(info),
        len(denied),
        red_flag_list,
        hypothesis is not None,
    )

    try:
        raw = await client.complete(
            system=_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=settings.summarizer_max_tokens,
            temperature=0.2,
            caller=_CALLER,
        )

        logger.info("SUMMARY_RAW  response=%r", raw[:500] if raw else "(empty)")

        if not raw or not raw.strip():
            logger.warning("SUMMARY_EMPTY  using fallback")
            return _FALLBACK

        result = raw.strip() + _DISCLAIMER
        logger.info("SUMMARY_OK  response_len=%d  (with disclaimer)", len(result))
        return result

    except Exception:
        logger.exception("SUMMARY_FAIL  using fallback")
        return _FALLBACK


def _format_info(info: dict[str, str]) -> str:
    if not info:
        return "(no information gathered)"
    return "\n".join(f"- {k}: {v}" for k, v in info.items())


_EMERGENCY_SYSTEM_PROMPT = (
    "You are a medical documentation assistant generating an URGENT "
    "consultation summary.\n\n"
    "This patient has symptoms that require immediate medical attention.\n\n"
    "Generate a summary with these EXACT sections:\n"
    "## ⚠️ Urgent Action Required\n"
    "## Symptoms Reported\n"
    "## Why This Is Urgent\n"
    "## What To Do Right Now\n\n"
    "Rules:\n"
    "- Lead with the action — what the patient must do immediately.\n"
    "- Be direct and clear — this is not the time for hedging.\n"
    "- Use plain language the patient can understand.\n"
    "- Keep it concise — the patient needs to act, not read.\n"
    "- Do NOT include any disclaimer — that will be added separately."
)

_EMERGENCY_DISCLAIMER = (
    "\n\n---\n"
    "This is an AI-assisted preliminary assessment. Please seek "
    "immediate medical attention as recommended above."
)


async def generate_emergency_summary(
    client: AgentLLMClient,
    state: dict,
    domain: DomainProfile,
) -> str:
    """Generate a compressed, urgent summary for emergency endings."""
    info = state.get("information_gathered", {})
    denied = state.get("denied_symptoms", set())
    hypothesis = state.get("hypothesis")
    red_flags = state.get("confirmed_red_flag_ids", set())
    hyp_summary = _format_hypothesis(hypothesis)
    denied_list = ", ".join(sorted(denied)) if denied else "(none)"
    red_flag_list = ", ".join(sorted(red_flags)) if red_flags else "(none)"

    user_prompt = (
        f"Information gathered:\n{_format_info(info)}\n\n"
        f"Denied symptoms: {denied_list}\n\n"
        f"Hypothesis analysis:\n{hyp_summary}\n\n"
        f"Confirmed red flags: {red_flag_list}"
    )

    logger.info(
        "EMERGENCY_SUMMARY_REQ  info_count=%d  red_flags=%s",
        len(info),
        red_flag_list,
    )

    try:
        raw = await client.complete(
            system=_EMERGENCY_SYSTEM_PROMPT,
            user=user_prompt,
            max_tokens=settings.summarizer_max_tokens,
            temperature=0.2,
            caller="summarizer.emergency",
        )

        if not raw or not raw.strip():
            logger.warning("EMERGENCY_SUMMARY_EMPTY  using fallback")
            return _FALLBACK

        result = raw.strip() + _EMERGENCY_DISCLAIMER
        logger.info("EMERGENCY_SUMMARY_OK  response_len=%d", len(result))
        return result

    except Exception:
        logger.exception("EMERGENCY_SUMMARY_FAIL  using fallback")
        return _FALLBACK


def _format_hypothesis(hypothesis) -> str:
    if hypothesis is None:
        return "(no hypothesis computed)"
    parts: list[str] = []
    if hypothesis.leading:
        h = hypothesis.leading
        parts.append(
            f"Leading: {h.name} (score={h.score:.2f}, "
            f"supporting={h.supporting_evidence}, missing={h.missing_evidence})"
        )
    for d in getattr(hypothesis, "differential", []):
        parts.append(f"Differential: {d.name} (score={d.score:.2f})")
    if not parts:
        return "(no hypothesis computed)"
    return "\n".join(parts)
