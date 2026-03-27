from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator, model_validator


class Utterance(BaseModel):
    id: str
    timestamp: str  # "HH:MM:SS.mmm"
    speaker: Literal["interviewer", "responder"]
    text: str
    is_preview: bool = False

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        parts = v.split(":")
        if len(parts) != 3:
            raise ValueError("timestamp must be HH:MM:SS.mmm")
        return v


class TranscriptMeta(BaseModel):
    id: str
    domain: str  # open — any domain string is accepted
    title: str
    description: str = ""
    turn_count: int = 0


class Transcript(BaseModel):
    id: str
    domain: str  # open — any domain string is accepted
    title: str
    description: str = ""
    utterances: list[Utterance]

    @property
    def meta(self) -> TranscriptMeta:
        return TranscriptMeta(
            id=self.id,
            domain=self.domain,
            title=self.title,
            description=self.description,
            turn_count=len(self.utterances),
        )


class SessionConfig(BaseModel):
    transcript_id: str | None = None
    domain: str
    mode: Literal["simulation", "chat"] = "simulation"
    interviewer_label: str = "Interviewer"
    responder_label: str = "Responder"
    speed: float = 1.0

    @model_validator(mode="after")
    def validate_mode_requirements(self) -> "SessionConfig":
        if self.mode == "simulation" and not self.transcript_id:
            raise ValueError("transcript_id is required in simulation mode")
        return self

    @field_validator("speed")
    @classmethod
    def validate_speed(cls, v: float) -> float:
        allowed = {0.5, 1.0, 2.0, 4.0}
        if v not in allowed:
            raise ValueError(f"speed must be one of {allowed}")
        return v


class SessionState(BaseModel):
    state: Literal["idle", "playing", "paused", "finished"]
    transcript_id: str | None = None
    domain: str | None = None
    turn_count: int = 0
    current_turn: int = 0
    speed: float = 1.0
