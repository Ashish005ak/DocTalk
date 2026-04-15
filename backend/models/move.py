from __future__ import annotations

from dataclasses import dataclass

from backend.models.state import MoveType


@dataclass
class ConversationMove:
    type: MoveType
    target_gap: str | None = None
    red_flag_id: str | None = None
    reason: str = ""
