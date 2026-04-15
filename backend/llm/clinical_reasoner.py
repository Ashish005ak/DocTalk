from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from backend.config import settings
from backend.llm.client import AgentLLMClient

logger = logging.getLogger(__name__)

_CALLER = "clinical_reasoner"

_SYSTEM = (
    "You are an experienced physician conducting a differential diagnosis.\n"
    "Based on the clinical information gathered so far, provide:\n"
    "1. Your top 5 differential diagnoses with calibrated probabilities.\n"
    "2. The single best next question to ask the patient to differentiate "
    "between competing diagnoses.\n\n"
    "Rules:\n"
    "- Be calibrated. Consider common conditions first but never ignore "
    "serious conditions that fit the presentation.\n"
    "- Probabilities must reflect genuine clinical likelihood given the evidence.\n"
    "- The next question should have the highest diagnostic value — it should "
    "help confirm or rule out the most likely competing diagnoses.\n"
    "- If you have enough information for a reasonable assessment and further "
    "questions would add little value, set should_summarize to true.\n"
    "- Confidence calibration:\n"
    '  - "low": fewer than 4 facts gathered, chief complaint unclear.\n'
    '  - "moderate": chief complaint clear, 4-7 relevant facts, '
    "multiple competing diagnoses remain.\n"
    '  - "high": 8+ relevant facts, leading diagnosis clearly ahead of '
    "alternatives, further questions unlikely to change the assessment "
    "significantly.\n"
    "- Your next_question must be a SHORT topic label (2-4 words), "
    "not a full sentence.\n"
    "- Respond with ONLY a JSON object. No markdown fences, no commentary.\n\n"
    "Output JSON schema:\n"
    "{\n"
    '  "hypotheses": [\n'
    '    {"name": "...", "probability": 0.0, '
    '"supporting_evidence": "...", "missing_evidence": "..."}\n'
    "  ],\n"
    '  "next_question": "topic to ask about",\n'
    '  "question_rationale": "why this question helps differentiate",\n'
    '  "confidence": "low|moderate|high",\n'
    '  "should_summarize": false\n'
    "}"
)


@dataclass
class LLMHypothesisEntry:
    name: str
    probability: float
    supporting_evidence: str = ""
    missing_evidence: str = ""


@dataclass
class ClinicalReasoning:
    hypotheses: list[LLMHypothesisEntry] = field(default_factory=list)
    next_question: str = ""
    question_rationale: str = ""
    confidence: str = "low"
    should_summarize: bool = False


def _build_user_prompt(state: dict) -> str:
    info = state.get("information_gathered", {})
    denied = state.get("denied_symptoms", set())
    turn = state.get("turn_count", 0)
    history = state.get("conversation_history", [])

    info_lines = "\n".join(f"- {k}: {v}" for k, v in info.items()) if info else "(none yet)"
    denied_lines = ", ".join(sorted(denied)) if denied else "(none)"

    recent = history[-6:] if len(history) > 6 else history
    history_lines = []
    for utt in recent:
        speaker = getattr(utt, "speaker", "unknown")
        text = getattr(utt, "text", str(utt))
        history_lines.append(f"  {speaker}: {text}")
    history_block = "\n".join(history_lines) if history_lines else "(first turn)"

    prompt = (
        f"Information gathered:\n{info_lines}\n\n"
        f"Denied symptoms: {denied_lines}\n\n"
        f"Turn count: {turn}\n\n"
        f"Recent conversation:\n{history_block}"
    )

    watch_hints = state.get("watch_hints", "")
    if watch_hints:
        prompt += f"\n\n{watch_hints}"

    prev_hyp = state.get("previous_hypothesis")
    prev_conf = state.get("previous_confidence", "")
    if prev_hyp:
        hyp_lines = "\n".join(f"- {h['name']}: {h['probability']:.0%}" for h in prev_hyp)
        prompt += (
            f"\n\nYour previous assessment (last turn):\n"
            f"{hyp_lines}\n"
            f"Previous confidence: {prev_conf}\n"
            f"Update your assessment based on any new information. "
            f"If evidence has strengthened your leading diagnosis, "
            f"increase its probability accordingly."
        )

    return prompt


def _parse_response(raw: str) -> ClinicalReasoning:
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)

    data = json.loads(cleaned.strip())

    hypotheses = []
    for h in data.get("hypotheses", []):
        if not isinstance(h, dict) or "name" not in h:
            continue
        hypotheses.append(LLMHypothesisEntry(
            name=str(h["name"]),
            probability=float(h.get("probability", 0.0)),
            supporting_evidence=str(h.get("supporting_evidence", "")),
            missing_evidence=str(h.get("missing_evidence", "")),
        ))

    hypotheses.sort(key=lambda e: e.probability, reverse=True)

    return ClinicalReasoning(
        hypotheses=hypotheses,
        next_question=str(data.get("next_question", "")),
        question_rationale=str(data.get("question_rationale", "")),
        confidence=str(data.get("confidence", "low")),
        should_summarize=bool(data.get("should_summarize", False)),
    )


_FALLBACK = ClinicalReasoning(
    hypotheses=[],
    next_question="general symptoms",
    question_rationale="Need more information to form differential",
    confidence="low",
    should_summarize=False,
)


async def generate_reasoning(
    client: AgentLLMClient,
    state: dict,
) -> ClinicalReasoning:
    """Call the LLM to produce differential diagnoses and pick the next question."""
    user_prompt = _build_user_prompt(state)

    logger.info(
        "REASONER_REQ  turn=%d  info_count=%d",
        state.get("turn_count", 0),
        len(state.get("information_gathered", {})),
    )

    try:
        raw = await client.complete(
            system=_SYSTEM,
            user=user_prompt,
            max_tokens=settings.fact_extractor_max_tokens,
            temperature=0.2,
            caller=_CALLER,
        )

        logger.info("REASONER_RAW  response_len=%d", len(raw))

        reasoning = _parse_response(raw)

        logger.info(
            "REASONER_OK  hypotheses=%d  top=%s(%.2f)  next_q=%s  confidence=%s  summarize=%s",
            len(reasoning.hypotheses),
            reasoning.hypotheses[0].name if reasoning.hypotheses else "(none)",
            reasoning.hypotheses[0].probability if reasoning.hypotheses else 0.0,
            reasoning.next_question,
            reasoning.confidence,
            reasoning.should_summarize,
        )

        return reasoning

    except Exception:
        logger.exception("REASONER_FAIL  returning fallback")
        return _FALLBACK
