from __future__ import annotations

import csv
import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_COSTS_DIR = Path("costs")

_RUN_CSV = _COSTS_DIR / "run.csv"
_COST_CSV = _COSTS_DIR / "cost.csv"

_RUN_HEADERS = [
    "timestamp", "session_id", "caller", "model",
    "prompt_tokens", "completion_tokens", "total_tokens", "cost_usd",
]
_COST_HEADERS = [
    "session_id", "domain_id", "start_time", "end_time",
    "total_calls", "total_prompt_tokens", "total_completion_tokens",
    "total_tokens", "total_cost_usd",
]

# Pricing per 1M tokens: (input, output)
COST_PER_M: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-1.5-pro": (1.25, 5.00),
    "llama-3.3-70b-versatile": (0.59, 0.79),
}


def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    rates = COST_PER_M.get(model)
    if not rates:
        return 0.0
    in_cost, out_cost = rates
    return (prompt_tokens * in_cost + completion_tokens * out_cost) / 1_000_000


@dataclass
class _SessionCostRecord:
    session_id: str
    domain_id: str
    start_time: datetime
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_cost_usd: float = 0.0
    call_count: int = 0
    finalized: bool = False


class CostTracker:
    """Singleton that logs per-call rows to run.csv and per-session summaries to cost.csv."""

    def __init__(self) -> None:
        self._sessions: dict[str, _SessionCostRecord] = {}
        self._lock = threading.Lock()
        self._ensure_files()

    def _ensure_files(self) -> None:
        _COSTS_DIR.mkdir(parents=True, exist_ok=True)
        if not _RUN_CSV.exists() or _RUN_CSV.stat().st_size == 0:
            with open(_RUN_CSV, "w", newline="") as f:
                csv.writer(f).writerow(_RUN_HEADERS)
        if not _COST_CSV.exists() or _COST_CSV.stat().st_size == 0:
            with open(_COST_CSV, "w", newline="") as f:
                csv.writer(f).writerow(_COST_HEADERS)

    def register_session(self, session_id: str, domain_id: str) -> None:
        with self._lock:
            self._sessions[session_id] = _SessionCostRecord(
                session_id=session_id,
                domain_id=domain_id,
                start_time=datetime.now(timezone.utc),
            )
        logger.info("COST_TRACKER  register  session_id=%s  domain=%s", session_id, domain_id)

    def log_call(
        self,
        session_id: str | None,
        caller: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> None:
        cost = calculate_cost(model, prompt_tokens, completion_tokens)
        total_tokens = prompt_tokens + completion_tokens
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            with open(_RUN_CSV, "a", newline="") as f:
                csv.writer(f).writerow([
                    now,
                    session_id or "unknown",
                    caller,
                    model,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    f"{cost:.8f}",
                ])

            rec = self._sessions.get(session_id) if session_id else None
            if rec and not rec.finalized:
                rec.total_prompt_tokens += prompt_tokens
                rec.total_completion_tokens += completion_tokens
                rec.total_cost_usd += cost
                rec.call_count += 1

        logger.info(
            "COST_TRACKER  log_call  session=%s  caller=%s  model=%s  "
            "in=%d  out=%d  cost=$%.8f",
            session_id or "unknown", caller, model,
            prompt_tokens, completion_tokens, cost,
        )

    def finalize_session(self, session_id: str) -> None:
        with self._lock:
            rec = self._sessions.get(session_id)
            if rec is None or rec.finalized:
                return
            rec.finalized = True
            end_time = datetime.now(timezone.utc)

            with open(_COST_CSV, "a", newline="") as f:
                csv.writer(f).writerow([
                    rec.session_id,
                    rec.domain_id,
                    rec.start_time.isoformat(),
                    end_time.isoformat(),
                    rec.call_count,
                    rec.total_prompt_tokens,
                    rec.total_completion_tokens,
                    rec.total_prompt_tokens + rec.total_completion_tokens,
                    f"{rec.total_cost_usd:.8f}",
                ])

        logger.info(
            "COST_TRACKER  finalize  session_id=%s  calls=%d  "
            "tokens=%d  cost=$%.8f",
            session_id, rec.call_count,
            rec.total_prompt_tokens + rec.total_completion_tokens,
            rec.total_cost_usd,
        )

    def finalize_all(self) -> None:
        with self._lock:
            session_ids = [
                sid for sid, rec in self._sessions.items() if not rec.finalized
            ]
        for sid in session_ids:
            self.finalize_session(sid)
        if session_ids:
            logger.info("COST_TRACKER  finalize_all  sessions=%d", len(session_ids))


cost_tracker = CostTracker()
