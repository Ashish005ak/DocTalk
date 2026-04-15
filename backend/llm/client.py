from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from backend.config import settings
from backend.context.llm_client import (
    LLMClient,
    LLMClientFactory,
    LLMError,
    LLMResponseParseError,
)
from backend.cost.context import current_caller

logger = logging.getLogger(__name__)

# Re-export for caller convenience
__all__ = ["AgentLLMClient", "LLMError", "LLMResponseParseError"]

# ── Approximate pricing per 1 M tokens (USD, as of 2025-Q2) ──────────────
_COST_PER_M: dict[str, tuple[float, float]] = {
    # (input_cost, output_cost) per 1 M tokens
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
    "gemini-2.5-flash": (0.15, 0.60),
    "gemini-1.5-pro": (1.25, 5.00),
    "llama-3.3-70b-versatile": (0.59, 0.79),
}


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return max(1, len(text) // 4)


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rates = _COST_PER_M.get(model)
    if not rates:
        return 0.0
    in_cost, out_cost = rates
    return (input_tokens * in_cost + output_tokens * out_cost) / 1_000_000


def _resolve_model(provider: str) -> str:
    mapping = {
        "claude": settings.anthropic_model,
        "openai": settings.openai_model,
        "gemini": settings.gemini_model,
        "groq": settings.groq_model,
    }
    return mapping.get(provider, "unknown")


@dataclass
class LLMCallMetrics:
    """Captured metadata from a single LLM call for monitoring."""
    caller: str
    provider: str
    model: str
    input_tokens_est: int = 0
    output_tokens_est: int = 0
    cost_est_usd: float = 0.0
    latency_ms: float = 0.0
    max_tokens: int = 0
    temperature: float | None = None
    raw_response: str = ""
    success: bool = True
    error: str | None = None


class AgentLLMClient:
    """Thin async wrapper over the multi-provider LLMClientFactory.

    Every call logs input/output token estimates, cost estimate, latency,
    and the full raw response for monitoring.
    """

    def __init__(self, provider: str | None = None) -> None:
        self._provider = (provider or settings.llm_provider).lower().strip()
        self._client: LLMClient = LLMClientFactory.get_client(self._provider)
        self._model = _resolve_model(self._provider)
        logger.info(
            "AgentLLMClient ready  provider=%s  model=%s",
            self._provider,
            self._model,
        )

    @property
    def provider(self) -> str:
        return self._provider

    @property
    def model(self) -> str:
        return self._model

    async def complete(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 512,
        temperature: float | None = None,
        caller: str = "unknown",
    ) -> str:
        current_caller.set(caller)
        input_tokens = _estimate_tokens(system + user)
        t0 = time.perf_counter()
        error_msg: str | None = None
        raw = ""
        try:
            raw = await self._client.analyze(
                system,
                user,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return raw
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            latency = (time.perf_counter() - t0) * 1000
            output_tokens = _estimate_tokens(raw) if raw else 0
            cost = _estimate_cost(self._model, input_tokens, output_tokens)
            metrics = LLMCallMetrics(
                caller=caller,
                provider=self._provider,
                model=self._model,
                input_tokens_est=input_tokens,
                output_tokens_est=output_tokens,
                cost_est_usd=cost,
                latency_ms=latency,
                max_tokens=max_tokens,
                temperature=temperature,
                raw_response=raw,
                success=error_msg is None,
                error=error_msg,
            )
            _log_call(metrics)

    async def complete_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 512,
        temperature: float | None = None,
        caller: str = "unknown",
    ) -> dict[str, Any]:
        current_caller.set(caller)
        input_tokens = _estimate_tokens(system + user)
        t0 = time.perf_counter()
        error_msg: str | None = None
        raw = ""
        result: dict[str, Any] = {}
        try:
            result = await self._client.analyze_json(
                system,
                user,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            raw = str(result)
            return result
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            latency = (time.perf_counter() - t0) * 1000
            output_tokens = _estimate_tokens(raw) if raw else 0
            cost = _estimate_cost(self._model, input_tokens, output_tokens)
            metrics = LLMCallMetrics(
                caller=caller,
                provider=self._provider,
                model=self._model,
                input_tokens_est=input_tokens,
                output_tokens_est=output_tokens,
                cost_est_usd=cost,
                latency_ms=latency,
                max_tokens=max_tokens,
                temperature=temperature,
                raw_response=raw,
                success=error_msg is None,
                error=error_msg,
            )
            _log_call(metrics)


def _log_call(m: LLMCallMetrics) -> None:
    status = "OK" if m.success else "FAIL"
    logger.info(
        "LLM_CALL  caller=%-25s  provider=%-8s  model=%-30s  "
        "status=%s  latency=%7.0fms  "
        "in_tokens=%-6d  out_tokens=%-6d  cost=$%.6f  max_tokens=%d",
        m.caller,
        m.provider,
        m.model,
        status,
        m.latency_ms,
        m.input_tokens_est,
        m.output_tokens_est,
        m.cost_est_usd,
        m.max_tokens,
    )
    if m.raw_response:
        truncated = m.raw_response[:2000]
        if len(m.raw_response) > 2000:
            truncated += f"... [TRUNCATED, total {len(m.raw_response)} chars]"
        logger.debug(
            "LLM_RAW   caller=%-25s  response=%s",
            m.caller,
            truncated,
        )
    if m.error:
        logger.error(
            "LLM_ERR   caller=%-25s  error=%s",
            m.caller,
            m.error,
        )
