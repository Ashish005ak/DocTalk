from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SymptomField:
    name: str
    hint: str = ""


@dataclass
class SymptomBlock:
    id: str
    name: str
    fields: list[SymptomField] = field(default_factory=list)


@dataclass
class RedFlagConfig:
    id: str
    name: str
    required_keys: list[str] = field(default_factory=list)
    at_least_one_of: list[str] = field(default_factory=list)
    qualifiers: dict[str, list[str]] = field(default_factory=dict)
    message: str = ""
    severity: str = "critical"
    soft_threshold: int = 1
    hard_threshold: int = 4


@dataclass
class ConfidenceThresholds:
    max_turns: int = 30
    max_gap_asks: int = 2
    watch_turns_limit: int = 5


@dataclass
class DedupFallback:
    with_target: str = (
        "I appreciate your patience. To help me better understand your situation, "
        "could you share more details about your {target_gap}{hint_suffix}?"
    )
    without_target: str = (
        "Thank you for sharing all of that. "
        "Is there anything else about your health that you think I should know?"
    )


@dataclass
class DomainProfile:
    id: str
    name: str
    description: str
    opening_message: str
    symptom_blocks: list[SymptomBlock] = field(default_factory=list)
    red_flags: list[RedFlagConfig] = field(default_factory=list)
    jargon_map: dict[str, str] = field(default_factory=dict)
    thresholds: ConfidenceThresholds = field(default_factory=ConfidenceThresholds)
    dedup_fallback: DedupFallback = field(default_factory=DedupFallback)
    placeholder_values: list[str] = field(default_factory=lambda: [
        "not specified", "not provided", "not mentioned", "n/a", "na",
        "none", "unknown", "not applicable", "not stated", "not given",
        "not reported", "not available",
    ])

    def get_field(self, field_name: str) -> SymptomField | None:
        for block in self.symptom_blocks:
            for f in block.fields:
                if f.name == field_name:
                    return f
        return None

    def get_field_hint(self, field_name: str) -> str | None:
        for block in self.symptom_blocks:
            for f in block.fields:
                if f.name == field_name:
                    return f.hint
        return None

    def get_block_by_id(self, block_id: str) -> SymptomBlock | None:
        for block in self.symptom_blocks:
            if block.id == block_id:
                return block
        return None
