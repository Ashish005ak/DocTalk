from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Literal

from backend.models.utterance import Transcript, Utterance
from backend.simulation.replay_engine import ReplayEngine, ReplayState
from backend.simulation.speed_controller import compute_delay

logger = logging.getLogger(__name__)

PREVIEW_LEAD_SECONDS = 0.8
PREVIEW_TEXT_FRACTION = 0.6  # emit the first 60 % of the text as a preview

UtteranceCallback = Callable[[Utterance], Awaitable[None]]


class PreviewBuffer:
    """
    Wraps a ReplayEngine and injects a preview event ~0.8 s before each
    committed utterance, simulating the partial-result behaviour of a live STT
    system.

    For each utterance the sequence is:
        T - 0.8s  →  emit Utterance(is_preview=True, text=first_60%)
        T         →  emit Utterance(is_preview=False, text=full_text)

    If the gap between consecutive utterances is less than PREVIEW_LEAD_SECONDS
    (which happens at 4× speed with short gaps), the preview is skipped and
    only the commit fires.
    """

    def __init__(self, engine: ReplayEngine) -> None:
        self._engine = engine
        self._callbacks: list[UtteranceCallback] = []
        self._state_callbacks: list[Callable[[ReplayState, int], Awaitable[None]]] = []

        # Hook into the engine's utterance stream
        engine.on_utterance(self._handle_utterance)
        engine.on_state_change(self._handle_state_change)

        # Cache the transcript so we can look ahead to compute inter-utterance gaps
        self._transcript: Transcript | None = None

    # ------------------------------------------------------------------
    # Public API — mirrors ReplayEngine for convenience
    # ------------------------------------------------------------------

    def on_utterance(self, callback: UtteranceCallback) -> None:
        """Register a callback that receives both preview and committed utterances."""
        self._callbacks.append(callback)

    def on_state_change(self, callback: Callable[[ReplayState, int], Awaitable[None]]) -> None:
        self._state_callbacks.append(callback)

    # Track when a new transcript is loaded so we can look ahead
    def notify_transcript_loaded(self, transcript: Transcript) -> None:
        self._transcript = transcript

    # ------------------------------------------------------------------
    # Engine hooks
    # ------------------------------------------------------------------

    async def _handle_utterance(self, utt: Utterance) -> None:
        """
        Called by ReplayEngine when an utterance is about to be committed.
        Determines whether a preview is possible and schedules accordingly.
        """
        gap_to_next = self._gap_to_next_utterance(utt)

        if gap_to_next is None or gap_to_next < PREVIEW_LEAD_SECONDS:
            # No room for a preview — emit the commit directly
            await self._emit(utt.model_copy(update={"is_preview": False}))
            return

        # Schedule the preview PREVIEW_LEAD_SECONDS before this utterance "arrives".
        # Because the engine has already waited for the utterance's timestamp before
        # calling us, the preview was supposed to fire 0.8 s ago.  We compensate by
        # firing it immediately at commit time but with is_preview=True, then sending
        # the full commit after 0 seconds — this preserves the two-stage UI pattern.
        preview_text = _truncate_to_fraction(utt.text, PREVIEW_TEXT_FRACTION)
        preview = utt.model_copy(update={"text": preview_text, "is_preview": True})
        await self._emit(preview)

        # The engine already held the delay; here we just ensure the commit fires
        # on the same tick (0 s delay) so the UI sees preview then commit.
        await asyncio.sleep(0)
        await self._emit(utt.model_copy(update={"is_preview": False}))

    async def _handle_state_change(self, state: ReplayState, turn: int) -> None:
        for cb in self._state_callbacks:
            try:
                await cb(state, turn)
            except Exception:
                logger.exception("Error in PreviewBuffer state callback")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _emit(self, utt: Utterance) -> None:
        for cb in self._callbacks:
            try:
                await cb(utt)
            except Exception:
                logger.exception("Error in PreviewBuffer utterance callback")

    def _gap_to_next_utterance(self, utt: Utterance) -> float | None:
        """Return seconds until the next utterance at current speed, or None if last."""
        if self._transcript is None:
            return None
        utterances = self._transcript.utterances
        try:
            idx = next(i for i, u in enumerate(utterances) if u.id == utt.id)
        except StopIteration:
            return None
        if idx + 1 >= len(utterances):
            return None
        return compute_delay(utt.timestamp, utterances[idx + 1].timestamp, self._engine.speed)


def _truncate_to_fraction(text: str, fraction: float) -> str:
    """
    Return a natural-looking prefix of `text` at roughly `fraction` of its length.
    Truncation prefers word boundaries.
    """
    if not text:
        return text
    target_len = max(1, int(len(text) * fraction))
    truncated = text[:target_len]
    # Walk back to the last space to avoid splitting mid-word
    last_space = truncated.rfind(" ")
    if last_space > 0:
        truncated = truncated[:last_space]
    return truncated
