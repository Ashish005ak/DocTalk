from __future__ import annotations

from enum import Enum


class Phase(str, Enum):
    INTAKE = "intake"
    EXPLORING = "exploring"
    NARROWING = "narrowing"
    SUMMARY = "summary"


class ConsultationEnding(str, Enum):
    NONE = "none"
    LANDING = "landing"
    EMERGENCY = "emergency"
    CLOSED = "closed"


class Confidence(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class PatientIntent(str, Enum):
    ANSWERING = "answering"
    ASKING_CLARIFICATION = "asking_clarification"
    ASKING_EXPLANATION = "asking_explanation"
    EXPRESSING_CONCERN = "expressing_concern"
    MIXED = "mixed"
    GREETING = "greeting"
    CRISIS = "crisis"
    TERMINATE = "terminate"


class MoveType(str, Enum):
    QUESTION = "question"
    CLARIFY = "clarify"
    TARGETED_CLARIFY = "targeted_clarify"
    ACKNOWLEDGE_CONCERN = "acknowledge_concern"
    RED_FLAG_FOLLOWUP = "red_flag_followup"
    EXPLAIN = "explain"
    SUMMARIZE = "summarize"
    CRISIS_RESPONSE = "crisis_response"
    OPENING = "opening"
    URGENT_CLOSE = "urgent_close"
    TERMINATE = "terminate"


class EmotionalTone(str, Enum):
    NEUTRAL = "neutral"
    ANXIOUS = "anxious"
    FRUSTRATED = "frustrated"
    DISTRESSED = "distressed"
