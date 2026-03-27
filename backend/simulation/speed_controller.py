from __future__ import annotations


def parse_timestamp(ts: str) -> float:
    """Convert 'HH:MM:SS.mmm' to total seconds as a float."""
    parts = ts.split(":")
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def compute_delay(ts_from: str, ts_to: str, speed: float) -> float:
    """
    Return the sleep duration (in seconds) between two consecutive utterances,
    scaled by the playback speed multiplier.

    A speed of 2.0 halves the wall-clock time between utterances.
    Clamps to a minimum of 0.0 to guard against floating-point drift.
    """
    if speed <= 0:
        raise ValueError(f"speed must be positive, got {speed}")
    delta = parse_timestamp(ts_to) - parse_timestamp(ts_from)
    return max(0.0, delta / speed)
