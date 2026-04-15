from __future__ import annotations

import contextvars

current_session_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_session_id", default=None
)

current_caller: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_caller", default="unknown"
)
