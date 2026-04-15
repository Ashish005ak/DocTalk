from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class HypothesisEntry:
    name: str
    score: float
    supporting_evidence: str = ""
    missing_evidence: str = ""


@dataclass
class Hypothesis:
    leading: HypothesisEntry | None = None
    differential: list[HypothesisEntry] = field(default_factory=list)
    ruled_out: list[HypothesisEntry] = field(default_factory=list)
