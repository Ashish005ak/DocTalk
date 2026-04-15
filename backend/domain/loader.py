from __future__ import annotations

import logging
from pathlib import Path

import yaml

from backend.domain.models import (
    ConfidenceThresholds,
    DedupFallback,
    DomainProfile,
    RedFlagConfig,
    SymptomBlock,
    SymptomField,
)

logger = logging.getLogger(__name__)

_CONFIGS_DIR = Path(__file__).parent / "configs"

_REQUIRED_TOP_LEVEL = {"id", "name", "description", "opening_message", "symptom_blocks", "red_flags"}


def load_domain(domain_id: str, configs_dir: Path | None = None) -> DomainProfile:
    """Load a YAML domain config and return a validated DomainProfile."""
    base = configs_dir or _CONFIGS_DIR
    path = base / f"{domain_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(f"Domain config not found: {path}")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Domain config must be a YAML mapping, got {type(raw).__name__}")

    missing = _REQUIRED_TOP_LEVEL - raw.keys()
    if missing:
        raise ValueError(f"Domain config {domain_id} missing required fields: {missing}")

    symptom_blocks = _parse_symptom_blocks(raw.get("symptom_blocks", []))
    red_flags = _parse_red_flags(raw.get("red_flags", []))
    jargon_map = raw.get("jargon_map", {})
    thresholds = _parse_thresholds(raw.get("thresholds", {}))
    dedup_fallback = _parse_dedup_fallback(raw.get("dedup_fallback", {}))
    placeholder_values = raw.get("placeholder_values", [])

    profile = DomainProfile(
        id=raw["id"],
        name=raw["name"],
        description=raw["description"],
        opening_message=raw["opening_message"].strip(),
        symptom_blocks=symptom_blocks,
        red_flags=red_flags,
        jargon_map=jargon_map,
        thresholds=thresholds,
        dedup_fallback=dedup_fallback,
        **({"placeholder_values": placeholder_values} if placeholder_values else {}),
    )

    logger.info(
        "Loaded domain '%s': %d blocks, %d red flags, %d jargon entries",
        profile.id,
        len(profile.symptom_blocks),
        len(profile.red_flags),
        len(profile.jargon_map),
    )
    return profile


def _parse_symptom_blocks(raw_blocks: list[dict]) -> list[SymptomBlock]:
    blocks: list[SymptomBlock] = []
    for b in raw_blocks:
        if "id" not in b or "name" not in b:
            raise ValueError(f"Symptom block missing 'id' or 'name': {b}")
        fields = [
            SymptomField(
                name=f["name"],
                hint=f.get("hint", ""),
            )
            for f in b.get("fields", [])
        ]
        blocks.append(SymptomBlock(
            id=b["id"],
            name=b["name"],
            fields=fields,
        ))
    return blocks


def _parse_red_flags(raw_flags: list[dict]) -> list[RedFlagConfig]:
    return [
        RedFlagConfig(
            id=rf["id"],
            name=rf["name"],
            required_keys=rf.get("required_keys", []),
            at_least_one_of=rf.get("at_least_one_of", []),
            qualifiers=rf.get("qualifiers", {}),
            message=rf.get("message", ""),
            severity=rf.get("severity", "critical"),
            soft_threshold=rf.get("soft_threshold", 1),
            hard_threshold=rf.get("hard_threshold", 4),
        )
        for rf in raw_flags
    ]


def _parse_thresholds(raw: dict) -> ConfidenceThresholds:
    return ConfidenceThresholds(
        max_turns=raw.get("max_turns", 30),
        max_gap_asks=raw.get("max_gap_asks", 2),
        watch_turns_limit=raw.get("watch_turns_limit", 5),
    )


def _parse_dedup_fallback(raw: dict) -> DedupFallback:
    fb = DedupFallback()
    if "with_target" in raw:
        fb.with_target = raw["with_target"].strip()
    if "without_target" in raw:
        fb.without_target = raw["without_target"].strip()
    return fb
