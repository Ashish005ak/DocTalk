from __future__ import annotations

import logging
import time
from difflib import SequenceMatcher

from backend.suggestions.suggestion_models import (
    FeedbackSummary,
    Suggestion,
    SuggestionFeedback,
    SuggestionOutput,
)

logger = logging.getLogger(__name__)

ADAPTED_SIMILARITY_THRESHOLD = 0.45


class FeedbackLogger:
    """Tracks suggestion outcomes (used / adapted / ignored) for a session."""

    def __init__(self) -> None:
        self._entries: list[SuggestionFeedback] = []
        self._active_suggestions: dict[str, Suggestion] = {}
        self._all_suggestions: dict[str, Suggestion] = {}

    def register_suggestions(self, output: SuggestionOutput) -> None:
        """Register a new batch of suggestions as the current active set.

        Previous active suggestions that were neither used nor adapted
        are marked as ignored.
        """
        for sid, sug in self._active_suggestions.items():
            if not any(e.suggestion_id == sid for e in self._entries):
                self._entries.append(SuggestionFeedback(
                    suggestion_id=sid,
                    outcome="ignored",
                    timestamp=time.time(),
                ))
                logger.debug("Suggestion marked ignored (replaced): %s", sid)

        self._active_suggestions.clear()
        for sug in output.suggestions:
            self._active_suggestions[sug.id] = sug
            self._all_suggestions[sug.id] = sug

    def mark_used(self, suggestion_id: str) -> bool:
        """Mark a suggestion as explicitly used by the interviewer."""
        if suggestion_id not in self._all_suggestions:
            logger.warning("Unknown suggestion id: %s", suggestion_id)
            return False

        existing = [e for e in self._entries if e.suggestion_id == suggestion_id]
        if existing:
            logger.debug("Suggestion %s already logged as '%s'", suggestion_id, existing[0].outcome)
            return False

        self._entries.append(SuggestionFeedback(
            suggestion_id=suggestion_id,
            outcome="used",
            timestamp=time.time(),
        ))
        self._active_suggestions.pop(suggestion_id, None)
        logger.info("Suggestion marked USED: %s", suggestion_id)
        return True

    def check_adapted(self, interviewer_text: str) -> None:
        """Check if the interviewer's utterance is semantically similar to an active suggestion.

        Uses simple string similarity (SequenceMatcher) as a lightweight v1 approach.
        """
        text_lower = interviewer_text.lower().strip()
        for sid, sug in list(self._active_suggestions.items()):
            if any(e.suggestion_id == sid for e in self._entries):
                continue

            ratio = SequenceMatcher(None, text_lower, sug.question.lower().strip()).ratio()
            if ratio >= ADAPTED_SIMILARITY_THRESHOLD:
                self._entries.append(SuggestionFeedback(
                    suggestion_id=sid,
                    outcome="adapted",
                    timestamp=time.time(),
                ))
                self._active_suggestions.pop(sid, None)
                logger.info(
                    "Suggestion marked ADAPTED: %s (similarity=%.2f)",
                    sid, ratio,
                )

    @property
    def summary(self) -> FeedbackSummary:
        used = sum(1 for e in self._entries if e.outcome == "used")
        adapted = sum(1 for e in self._entries if e.outcome == "adapted")
        ignored = sum(1 for e in self._entries if e.outcome == "ignored")
        total = used + adapted + ignored
        relevance_rate = (used + adapted) / total if total > 0 else 0.0

        return FeedbackSummary(
            total=total,
            used=used,
            adapted=adapted,
            ignored=ignored,
            relevance_rate=round(relevance_rate, 3),
            entries=list(self._entries),
        )

    def reset(self) -> None:
        self._entries.clear()
        self._active_suggestions.clear()
        self._all_suggestions.clear()
