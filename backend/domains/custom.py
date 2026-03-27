from __future__ import annotations

import json
import logging
from pathlib import Path

from backend.domains.models import DomainProfile

logger = logging.getLogger(__name__)

_GENERIC_PROFILE = DomainProfile(
    id="custom",
    name="Custom",
    description="User-defined domain profile",
    framework="General",
    role_labels={"interviewer": "Interviewer", "responder": "Responder"},
    gap_categories=["Topic coverage", "Detail depth", "Follow-up needed"],
    signal_types=["important", "contradiction", "vague", "emotional"],
    priority_rules=[
        "Follow up on contradictions or inconsistencies first.",
        "Probe vague answers for specifics.",
        "Explore uncovered topics.",
    ],
    system_prompt_fragment="""\
You are a general conversation analyst. Track the conversation topics, \
information gathered, remaining gaps, and notable signals. \
Output the running context as a structured JSON object with keys: \
core_topic, information_gathered, gaps, signals, turn_count.""",
)


def load_custom_profile(path: str | Path) -> DomainProfile:
    """Load a custom domain profile from a JSON file.

    The JSON file must match the DomainProfile schema. Falls back to a
    generic profile if the file cannot be loaded.
    """
    file_path = Path(path)
    if not file_path.exists():
        logger.warning("Custom profile not found at %s — using generic profile", path)
        return _GENERIC_PROFILE

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        profile = DomainProfile(**data)
        logger.info("Custom profile loaded: id='%s' framework='%s' from %s",
                     profile.id, profile.framework, path)
        return profile
    except Exception as exc:
        logger.warning("Failed to load custom profile %s: %s — using generic profile", path, exc)
        return _GENERIC_PROFILE


def get_generic_profile() -> DomainProfile:
    """Return the built-in generic / fallback profile."""
    return _GENERIC_PROFILE.model_copy()
