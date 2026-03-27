from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Awaitable, Callable

from backend.config import settings
from backend.context.context_models import ContextObject
from backend.context.llm_client import LLMClient, LLMError
from backend.domains.models import DomainProfile
from backend.suggestions.suggestion_models import Suggestion, SuggestionOutput

logger = logging.getLogger(__name__)

SuggestionCallback = Callable[[SuggestionOutput], Awaitable[None]]

_SUGGESTION_SYSTEM_PROMPT = """\
You are an expert interviewing coach specializing in the {domain} domain.
Your task is to suggest the next best questions for the interviewer to ask,
based on the current conversation context.

{system_prompt_fragment}

## Priority Rules (domain-specific)
{priority_rules}

## Signal Types to Watch
{signal_types}
"""

_SUGGESTION_USER_PROMPT = """\
Below is the current conversation context analysis.

## Context
{context_json}

## Questions Already Asked
{questions_asked}

## Instructions
Based on the context above, suggest {max_count} questions the interviewer should ask next.
Rank them by priority according to the domain-specific priority rules.

Rules:
- NEVER suggest a question that has already been asked (see "Questions Already Asked" above).
- Each suggestion must have a clear, specific rationale tied to a gap or signal.
- Phrase questions naturally, as a human interviewer would ask them.
- Priority must be one of: "high", "medium", "low"

Return a JSON object:
{{
  "context_summary": "<one-sentence summary of where the conversation stands>",
  "suggestions": [
    {{
      "priority": "high|medium|low",
      "question": "<the question to ask>",
      "rationale": "<one sentence explaining why this question matters now>"
    }}
  ]
}}

Respond ONLY with valid JSON, no markdown fences or extra text.
"""


class SuggestionEngine:
    """Generates ranked next-question suggestions from a context object.

    Used as a standalone fallback when the combined context+suggestions
    LLM call in ContextEngine does not produce suggestions.
    """

    def __init__(
        self,
        domain_profile: DomainProfile,
        llm_client: LLMClient,
    ) -> None:
        self._profile = domain_profile
        self._llm = llm_client
        self._subscribers: list[SuggestionCallback] = []
        self._latest: SuggestionOutput | None = None
        self._suggestion_counter = 0

    @property
    def latest(self) -> SuggestionOutput | None:
        return self._latest

    def subscribe(self, callback: SuggestionCallback) -> None:
        self._subscribers.append(callback)

    async def generate(self, context: ContextObject) -> SuggestionOutput:
        """Generate suggestions from a context object via a standalone LLM call."""
        system_prompt = _SUGGESTION_SYSTEM_PROMPT.format(
            domain=self._profile.name,
            system_prompt_fragment=self._profile.system_prompt_fragment,
            priority_rules="\n".join(f"- {r}" for r in self._profile.priority_rules),
            signal_types=json.dumps(self._profile.signal_types),
        )

        user_prompt = _SUGGESTION_USER_PROMPT.format(
            context_json=json.dumps(context.model_dump(), indent=2),
            questions_asked=json.dumps(context.questions_asked),
            max_count=settings.suggestion_max_count,
        )

        raw: dict[str, Any] = await self._llm.analyze_json(
            system_prompt, user_prompt,
            max_tokens=settings.llm_max_output_tokens,
        )

        output = self._parse_response(raw, context)
        self._latest = output

        await self._emit(output)
        return output

    def parse_from_combined(
        self, raw_suggestions: list[dict[str, Any]], context: ContextObject,
        context_summary: str = "",
    ) -> SuggestionOutput:
        """Parse suggestions extracted from a combined context+suggestions LLM response."""
        trigger = context.session_id
        if len(context.questions_asked) > 0:
            trigger = f"turn_{context.turn_count}"

        suggestions = self._build_suggestions(raw_suggestions, context)

        output = SuggestionOutput(
            trigger_utt=trigger,
            context_summary=context_summary or context.core_topic,
            suggestions=suggestions,
        )
        self._latest = output
        return output

    def _parse_response(
        self, raw: dict[str, Any], context: ContextObject,
    ) -> SuggestionOutput:
        trigger = f"turn_{context.turn_count}"
        context_summary = raw.get("context_summary", context.core_topic)
        raw_suggestions = raw.get("suggestions", [])

        suggestions = self._build_suggestions(raw_suggestions, context)

        return SuggestionOutput(
            trigger_utt=trigger,
            context_summary=str(context_summary),
            suggestions=suggestions,
        )

    def _build_suggestions(
        self, raw_suggestions: list[Any], context: ContextObject,
    ) -> list[Suggestion]:
        asked_lower = {q.lower().strip() for q in context.questions_asked}
        suggestions: list[Suggestion] = []

        for item in raw_suggestions:
            if not isinstance(item, dict):
                continue
            question = str(item.get("question", "")).strip()
            if not question:
                continue
            if question.lower().strip() in asked_lower:
                logger.debug("Filtered duplicate suggestion: %s", question[:60])
                continue

            self._suggestion_counter += 1
            priority = str(item.get("priority", "medium")).lower()
            if priority not in ("high", "medium", "low"):
                priority = "medium"

            suggestions.append(Suggestion(
                id=f"sug_{self._suggestion_counter:03d}",
                priority=priority,
                question=question,
                rationale=str(item.get("rationale", "")),
            ))

            if len(suggestions) >= settings.suggestion_max_count:
                break

        priority_order = {"high": 0, "medium": 1, "low": 2}
        suggestions.sort(key=lambda s: priority_order.get(s.priority, 1))
        return suggestions

    async def _emit(self, output: SuggestionOutput) -> None:
        for cb in self._subscribers:
            try:
                await cb(output)
            except Exception:
                logger.exception("Error in suggestion subscriber callback")

    def reset(self) -> None:
        self._latest = None
        self._suggestion_counter = 0
