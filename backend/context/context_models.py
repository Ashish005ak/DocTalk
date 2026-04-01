from __future__ import annotations

from pydantic import BaseModel


class InformationItem(BaseModel):
    key: str
    value: str
    source_utt: str


class Signal(BaseModel):
    type: str  # "red_flag", "contradiction", "vague", "emotional"
    detail: str
    source_utt: str


class ContextObject(BaseModel):
    session_id: str
    core_topic: str = ""
    information_gathered: list[InformationItem] = []
    questions_asked: list[str] = []
    gaps: list[str] = []
    signals: list[Signal] = []
    turn_count: int = 0
    active_categories: list[str] = []
    conversation_phase: str = "gathering"
