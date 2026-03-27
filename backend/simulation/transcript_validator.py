from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from backend.models.utterance import Transcript

logger = logging.getLogger(__name__)


class TranscriptValidationError(Exception):
    def __init__(self, message: str, details: list[dict] | None = None) -> None:
        super().__init__(message)
        self.details = details or []


def validate_transcript_dict(data: dict[str, Any]) -> Transcript:
    """
    Validate a raw dict against the Transcript schema.
    Raises TranscriptValidationError with structured details on failure.
    """
    try:
        transcript = Transcript.model_validate(data)
    except ValidationError as exc:
        details = [
            {"field": " -> ".join(str(loc) for loc in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        raise TranscriptValidationError(
            f"Transcript validation failed with {len(details)} error(s).",
            details=details,
        ) from exc

    _validate_timestamp_order(transcript)
    _validate_speaker_pattern(transcript)
    logger.info(
        "Transcript validated: id='%s' domain='%s' utterances=%d",
        transcript.id, transcript.domain, len(transcript.utterances),
    )
    return transcript


def validate_transcript_file(path: Path) -> Transcript:
    """Load and validate a transcript JSON file from disk."""
    if not path.exists():
        raise TranscriptValidationError(f"File not found: {path}")
    logger.debug("Loading transcript file: %s", path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("Invalid JSON in transcript file %s: %s", path.name, exc)
        raise TranscriptValidationError(f"Invalid JSON: {exc}") from exc
    return validate_transcript_dict(data)


def _validate_timestamp_order(transcript: Transcript) -> None:
    """Ensure utterance timestamps are strictly increasing."""
    prev_ts = -1.0
    for utt in transcript.utterances:
        ts = _parse_timestamp(utt.timestamp)
        if ts <= prev_ts:
            raise TranscriptValidationError(
                f"Utterance {utt.id} has a non-increasing timestamp '{utt.timestamp}'. "
                "Timestamps must be strictly increasing."
            )
        prev_ts = ts


def _validate_speaker_pattern(transcript: Transcript) -> None:
    """Warn if two consecutive utterances have the same speaker (allowed but unusual)."""
    for i in range(1, len(transcript.utterances)):
        prev = transcript.utterances[i - 1]
        curr = transcript.utterances[i]
        if prev.speaker == curr.speaker:
            # Not a hard error — monologues can happen — but flag it
            pass  # could emit a warning here in future


def _parse_timestamp(ts: str) -> float:
    """Convert HH:MM:SS.mmm to total seconds as a float."""
    try:
        parts = ts.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    except (IndexError, ValueError) as exc:
        raise TranscriptValidationError(f"Cannot parse timestamp '{ts}': {exc}") from exc
