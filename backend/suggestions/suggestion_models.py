from __future__ import annotations

from pydantic import BaseModel


class Suggestion(BaseModel):
    id: str
    priority: str  # "high" | "medium" | "low"
    question: str
    rationale: str


class SuggestionOutput(BaseModel):
    trigger_utt: str
    context_summary: str
    suggestions: list[Suggestion] = []


class SuggestionFeedback(BaseModel):
    suggestion_id: str
    outcome: str  # "used" | "adapted" | "ignored"
    timestamp: float


class FeedbackSummary(BaseModel):
    total: int = 0
    used: int = 0
    adapted: int = 0
    ignored: int = 0
    relevance_rate: float = 0.0
    entries: list[SuggestionFeedback] = []
