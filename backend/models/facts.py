from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from backend.models.state import EmotionalTone, PatientIntent


class FactConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    UNCLEAR = "unclear"


@dataclass
class RawFact:
    key: str
    value: str
    denied: bool = False
    confidence: FactConfidence = FactConfidence.HIGH


@dataclass
class IntakeResult:
    intent: PatientIntent
    facts: list[RawFact] = field(default_factory=list)
    emotional_tone: EmotionalTone = EmotionalTone.NEUTRAL
