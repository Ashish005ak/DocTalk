from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RedFlagRule:
    id: str
    name: str
    required_keys: list[str] = field(default_factory=list)
    at_least_one_of: list[str] = field(default_factory=list)
    qualifiers: dict[str, list[str]] = field(default_factory=dict)
    message: str = ""
    severity: str = "critical"
    soft_threshold: int = 1
    hard_threshold: int = 4
