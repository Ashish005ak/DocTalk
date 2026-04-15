from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.models.state import PatientIntent


@dataclass
class Utterance:
    speaker: Literal["patient", "doctor"]
    text: str
    turn: int
    intent: PatientIntent | None = None
