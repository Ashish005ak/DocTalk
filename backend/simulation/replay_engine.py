from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, Literal

from backend.models.utterance import Transcript, Utterance
from backend.simulation.speed_controller import compute_delay

logger = logging.getLogger(__name__)

ReplayState = Literal["idle", "playing", "paused", "finished"]
UtteranceCallback = Callable[[Utterance], Awaitable[None]]


class ReplayEngine:
    """
    Asyncio-based transcript replay engine.

    Loads a Transcript and emits each Utterance through a registered callback
    at timing intervals derived from the original timestamps, scaled by speed.

    State machine:
        idle → playing → paused ↔ playing → finished → idle (after reset)
    """

    def __init__(self) -> None:
        self._transcript: Transcript | None = None
        self._state: ReplayState = "idle"
        self._speed: float = 1.0
        self._current_index: int = 0

        # asyncio primitives
        self._pause_event: asyncio.Event = asyncio.Event()
        self._pause_event.set()  # not paused initially
        self._task: asyncio.Task | None = None

        # registered listeners — called on every committed utterance
        self._callbacks: list[UtteranceCallback] = []

        # state-change listeners — called when state transitions
        self._state_callbacks: list[Callable[[ReplayState, int], Awaitable[None]]] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load(self, transcript: Transcript) -> None:
        """Load a transcript. Resets any in-progress replay."""
        if self._task and not self._task.done():
            self._task.cancel()
        self._transcript = transcript
        self._current_index = 0
        self._state = "idle"
        self._pause_event.set()
        logger.info("Loaded transcript '%s' (%d utterances)", transcript.id, len(transcript.utterances))

    def on_utterance(self, callback: UtteranceCallback) -> None:
        """Register a callback that fires when an utterance is committed."""
        self._callbacks.append(callback)

    def on_state_change(self, callback: Callable[[ReplayState, int], Awaitable[None]]) -> None:
        """Register a callback that fires when replay state changes."""
        self._state_callbacks.append(callback)

    def start(self) -> None:
        """Begin replay from the current position. No-op if already playing."""
        if self._state == "playing":
            return
        if self._transcript is None:
            raise RuntimeError("No transcript loaded. Call load() first.")
        if self._state == "finished":
            self._current_index = 0
        self._state = "playing"
        self._pause_event.set()
        self._task = asyncio.create_task(self._run())
        asyncio.create_task(self._emit_state())
        logger.info(
            "Replay started: transcript='%s' from_turn=%d speed=%.1fx",
            self._transcript.id, self._current_index, self._speed,
        )

    def pause(self) -> None:
        """Pause replay at the current position."""
        if self._state != "playing":
            return
        self._state = "paused"
        self._pause_event.clear()
        asyncio.create_task(self._emit_state())
        logger.info("Replay paused at turn %d/%d", self._current_index,
                     len(self._transcript.utterances) if self._transcript else 0)

    def resume(self) -> None:
        """Resume a paused replay."""
        if self._state != "paused":
            return
        self._state = "playing"
        self._pause_event.set()
        asyncio.create_task(self._emit_state())
        logger.info("Replay resumed at turn %d/%d", self._current_index,
                     len(self._transcript.utterances) if self._transcript else 0)

    def stop(self) -> None:
        """Stop and reset to the beginning."""
        transcript_id = self._transcript.id if self._transcript else "none"
        if self._task and not self._task.done():
            self._task.cancel()
        self._current_index = 0
        self._state = "idle"
        self._pause_event.set()
        asyncio.create_task(self._emit_state())
        logger.info("Replay stopped and reset: transcript='%s'", transcript_id)

    def reset(self) -> None:
        """Alias for stop() — resets position to zero."""
        self.stop()

    def set_speed(self, speed: float) -> None:
        """
        Update playback speed. Takes effect on the next inter-utterance delay.
        Valid values: 0.5, 1.0, 2.0, 4.0.
        """
        allowed = {0.5, 1.0, 2.0, 4.0}
        if speed not in allowed:
            raise ValueError(f"speed must be one of {allowed}, got {speed}")
        old_speed = self._speed
        self._speed = speed
        logger.info("Speed changed: %.1fx → %.1fx", old_speed, speed)

    @property
    def state(self) -> ReplayState:
        return self._state

    @property
    def speed(self) -> float:
        return self._speed

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def transcript(self) -> Transcript | None:
        return self._transcript

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        assert self._transcript is not None
        utterances = self._transcript.utterances

        while self._current_index < len(utterances):
            # Respect pause
            await self._pause_event.wait()

            utt = utterances[self._current_index]

            # Compute delay before emitting: time to the NEXT utterance
            # For the first utterance, wait the timestamp offset from t=0.
            # For subsequent utterances, wait the delta from the previous.
            if self._current_index == 0:
                delay = compute_delay("00:00:00.000", utt.timestamp, self._speed)
            else:
                prev_ts = utterances[self._current_index - 1].timestamp
                delay = compute_delay(prev_ts, utt.timestamp, self._speed)

            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                return

            # Re-check pause after sleep (speed or pause may have changed)
            await self._pause_event.wait()

            # Emit the utterance
            for cb in self._callbacks:
                try:
                    await cb(utt)
                except Exception:
                    logger.exception("Error in utterance callback")

            self._current_index += 1
            asyncio.create_task(self._emit_state())

        self._state = "finished"
        asyncio.create_task(self._emit_state())
        logger.info("Replay finished for '%s'", self._transcript.id)

    async def _emit_state(self) -> None:
        for cb in self._state_callbacks:
            try:
                await cb(self._state, self._current_index)
            except Exception:
                logger.exception("Error in state callback")
