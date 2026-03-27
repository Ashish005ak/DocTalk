from __future__ import annotations

import abc
import asyncio
import json
import logging
import re
import time
from typing import Any

from backend.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_json_fences(text: str) -> str:
    """Remove markdown ```json ... ``` wrappers that LLMs often add."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return cleaned.strip()


class LLMError(Exception):
    """Base exception for LLM client errors."""


class LLMRateLimitError(LLMError):
    """Raised when the provider returns a rate-limit / quota error."""


class LLMResponseParseError(LLMError):
    """Raised when the LLM response cannot be parsed as expected."""


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class LLMClient(abc.ABC):
    """Unified interface for calling any supported LLM provider."""

    provider: str = "base"

    @abc.abstractmethod
    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> str:
        """Send a prompt and return the raw text response."""

    async def analyze_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """Send a prompt and return the response parsed as JSON.

        Retries up to ``settings.llm_max_retries`` times on parse failures,
        appending a corrective instruction on each retry.
        """
        last_error: Exception | None = None
        for attempt in range(1, settings.llm_max_retries + 1):
            raw = await self.analyze(
                system_prompt,
                user_prompt,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            cleaned = _strip_json_fences(raw)
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError as exc:
                last_error = exc
                preview_head = cleaned[:300]
                preview_tail = cleaned[-200:] if len(cleaned) > 500 else ""
                logger.warning(
                    "JSON parse failed (attempt %d/%d): %s\n"
                    "  response_length=%d chars\n"
                    "  HEAD: %.300s\n"
                    "  TAIL: %.200s",
                    attempt,
                    settings.llm_max_retries,
                    exc,
                    len(cleaned),
                    preview_head,
                    preview_tail,
                )
                user_prompt = (
                    f"{user_prompt}\n\n"
                    "IMPORTANT: Your previous response was not valid JSON — "
                    "it appeared truncated. Keep the response concise and ensure "
                    "every opened brace/bracket is closed. "
                    "Respond ONLY with a valid JSON object, no markdown fences or extra text."
                )
        raise LLMResponseParseError(
            f"Failed to parse JSON after {settings.llm_max_retries} attempts"
        ) from last_error


# ---------------------------------------------------------------------------
# Retry wrapper
# ---------------------------------------------------------------------------

async def _retry_with_backoff(coro_factory, *, max_retries: int, provider: str) -> Any:
    """Execute an async callable with exponential backoff on transient errors."""
    delays = [1, 2, 4, 8, 16]
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            return await coro_factory()
        except LLMRateLimitError:
            raise
        except Exception as exc:
            last_exc = exc
            delay = delays[min(attempt, len(delays) - 1)]
            logger.warning(
                "%s API error (attempt %d/%d), retrying in %ds: %s",
                provider,
                attempt + 1,
                max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
    raise LLMError(f"{provider} failed after {max_retries} attempts") from last_exc


# ---------------------------------------------------------------------------
# Claude (Anthropic)
# ---------------------------------------------------------------------------

class ClaudeClient(LLMClient):
    provider = "claude"

    def __init__(self) -> None:
        try:
            import anthropic  # noqa: F811
        except ImportError as exc:
            raise ImportError("pip install anthropic") from exc
        if not settings.anthropic_api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set in .env")
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model
        logger.info("ClaudeClient initialized: model='%s' temperature=%.1f",
                     self._model, settings.llm_temperature)

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> str:
        import anthropic

        temp = temperature if temperature is not None else settings.llm_temperature

        async def _call():
            t0 = time.perf_counter()
            try:
                resp = await self._client.messages.create(
                    model=self._model,
                    max_tokens=max_tokens,
                    temperature=temp,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
            except anthropic.RateLimitError as exc:
                raise LLMRateLimitError(str(exc)) from exc
            latency_ms = (time.perf_counter() - t0) * 1000
            usage = resp.usage
            logger.info(
                "LLM call  provider=%s  model=%s  latency=%.0fms  "
                "in=%d  out=%d  stop_reason=%s  max_tokens=%d",
                self.provider,
                self._model,
                latency_ms,
                usage.input_tokens if usage else 0,
                usage.output_tokens if usage else 0,
                resp.stop_reason,
                max_tokens,
            )
            if resp.stop_reason == "max_tokens":
                logger.warning(
                    "Claude response TRUNCATED (hit max_tokens=%d). "
                    "Response will likely fail JSON parsing.",
                    max_tokens,
                )
            return resp.content[0].text

        return await _retry_with_backoff(
            _call, max_retries=settings.llm_max_retries, provider=self.provider
        )


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

class OpenAIClient(LLMClient):
    provider = "openai"

    def __init__(self) -> None:
        try:
            import openai  # noqa: F811
        except ImportError as exc:
            raise ImportError("pip install openai") from exc
        if not settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY is not set in .env")
        self._client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = settings.openai_model
        logger.info("OpenAIClient initialized: model='%s' temperature=%.1f",
                     self._model, settings.llm_temperature)

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> str:
        import openai

        temp = temperature if temperature is not None else settings.llm_temperature

        async def _call():
            t0 = time.perf_counter()
            try:
                resp = await self._client.chat.completions.create(
                    model=self._model,
                    temperature=temp,
                    max_tokens=max_tokens,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                )
            except openai.RateLimitError as exc:
                raise LLMRateLimitError(str(exc)) from exc
            latency_ms = (time.perf_counter() - t0) * 1000
            usage = resp.usage
            finish_reason = resp.choices[0].finish_reason if resp.choices else None
            logger.info(
                "LLM call  provider=%s  model=%s  latency=%.0fms  "
                "in=%d  out=%d  finish_reason=%s  max_tokens=%d",
                self.provider,
                self._model,
                latency_ms,
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
                finish_reason,
                max_tokens,
            )
            if finish_reason == "length":
                logger.warning(
                    "OpenAI response TRUNCATED (hit max_tokens=%d). "
                    "Response will likely fail JSON parsing.",
                    max_tokens,
                )
            return resp.choices[0].message.content or ""

        return await _retry_with_backoff(
            _call, max_retries=settings.llm_max_retries, provider=self.provider
        )


# ---------------------------------------------------------------------------
# Gemini (Google GenAI)
# ---------------------------------------------------------------------------

class GeminiClient(LLMClient):
    provider = "gemini"

    def __init__(self) -> None:
        try:
            import google.generativeai as genai  # noqa: F811
        except ImportError as exc:
            raise ImportError("pip install google-generativeai") from exc
        if not settings.google_api_key:
            raise LLMError("GOOGLE_API_KEY is not set in .env")
        genai.configure(api_key=settings.google_api_key)
        self._model_name = settings.gemini_model
        self._genai = genai
        logger.info("GeminiClient initialized: model='%s' temperature=%.1f",
                     self._model_name, settings.llm_temperature)

    async def analyze(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float | None = None,
        max_tokens: int = 4096,
    ) -> str:
        temp = temperature if temperature is not None else settings.llm_temperature

        async def _call():
            t0 = time.perf_counter()
            model = self._genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=system_prompt,
                generation_config=self._genai.GenerationConfig(
                    temperature=temp,
                    max_output_tokens=max_tokens,
                ),
            )
            resp = await model.generate_content_async(user_prompt)
            latency_ms = (time.perf_counter() - t0) * 1000

            finish_reason = None
            token_count = None
            if resp.candidates:
                candidate = resp.candidates[0]
                finish_reason = candidate.finish_reason.name if candidate.finish_reason else None
                if hasattr(resp, "usage_metadata") and resp.usage_metadata:
                    meta = resp.usage_metadata
                    token_count = getattr(meta, "candidates_token_count", None)

            logger.info(
                "LLM call  provider=%s  model=%s  latency=%.0fms  "
                "finish_reason=%s  output_tokens=%s  max_tokens=%d",
                self.provider,
                self._model_name,
                latency_ms,
                finish_reason,
                token_count,
                max_tokens,
            )

            if finish_reason == "MAX_TOKENS":
                logger.warning(
                    "Gemini response TRUNCATED (hit max_output_tokens=%d). "
                    "Response will likely fail JSON parsing.",
                    max_tokens,
                )

            return resp.text

        return await _retry_with_backoff(
            _call, max_retries=settings.llm_max_retries, provider=self.provider
        )


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_PROVIDERS: dict[str, type[LLMClient]] = {
    "claude": ClaudeClient,
    "openai": OpenAIClient,
    "gemini": GeminiClient,
}

_cached_clients: dict[str, LLMClient] = {}


class LLMClientFactory:
    """Config-driven factory for obtaining an LLMClient instance."""

    @staticmethod
    def get_client(provider: str | None = None) -> LLMClient:
        """Return a (cached) client for the given or configured provider."""
        provider = (provider or settings.llm_provider).lower().strip()
        if provider in _cached_clients:
            return _cached_clients[provider]

        cls = _PROVIDERS.get(provider)
        if cls is None:
            raise LLMError(
                f"Unknown LLM provider '{provider}'. "
                f"Supported: {', '.join(_PROVIDERS)}"
            )
        client = cls()
        _cached_clients[provider] = client
        logger.info("LLM client created: provider='%s'", provider)
        return client

    @staticmethod
    def available_providers() -> list[str]:
        return list(_PROVIDERS.keys())

    @staticmethod
    def configured_provider() -> str:
        return settings.llm_provider

    @staticmethod
    def has_api_key(provider: str | None = None) -> bool:
        """Check whether the API key is set for a provider (without revealing it)."""
        provider = (provider or settings.llm_provider).lower().strip()
        key_map = {
            "claude": settings.anthropic_api_key,
            "openai": settings.openai_api_key,
            "gemini": settings.google_api_key,
        }
        return bool(key_map.get(provider, ""))
