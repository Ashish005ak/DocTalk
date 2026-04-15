from __future__ import annotations

from backend.domain.models import DomainProfile, HypothesisConfig
from backend.models.hypothesis import Hypothesis, HypothesisEntry
from backend.models.state import Confidence


def _key_matches_facts(key: str, facts: dict[str, str]) -> bool:
    """Check if a hypothesis key matches any gathered fact (key or value), case-insensitive."""
    key_lower = key.lower()
    for fact_key, fact_value in facts.items():
        if key_lower in fact_key.lower() or key_lower in fact_value.lower():
            return True
    return False


def _key_matches_denied(key: str, denied: set[str]) -> bool:
    """Check if a hypothesis key matches any denied symptom, case-insensitive."""
    key_lower = key.lower()
    for d in denied:
        if key_lower in d.lower() or d.lower() in key_lower:
            return True
    return False


def score_hypothesis(
    config: HypothesisConfig,
    facts: dict[str, str],
    denied: set[str],
) -> tuple[float, list[str], list[str]]:
    """Score a single hypothesis against gathered facts.

    IMPORTANT: ``facts`` must be ``information_gathered`` (confirmed facts only).
    Unconfirmed facts (from ``unconfirmed_facts``) must never be passed here
    to avoid inflating hypothesis scores with unverified data.

    Returns (normalised_score, matched_supporting_keys, matched_contradicting_keys).
    """
    supporting: list[str] = []
    contradicting: list[str] = []

    for key in config.supporting_keys:
        if _key_matches_facts(key, facts):
            supporting.append(key)

    for key in config.contradicting_keys:
        if _key_matches_facts(key, facts) or _key_matches_denied(key, denied):
            contradicting.append(key)

    raw = (len(supporting) * config.prior_weight) - len(contradicting)
    normalised = max(raw / max(len(config.supporting_keys), 1), 0.0)

    return normalised, supporting, contradicting


def score_all_hypotheses(
    domain: DomainProfile,
    facts: dict[str, str],
    denied: set[str],
) -> Hypothesis:
    """Score every hypothesis in the domain and partition into leading / differential / ruled_out.

    IMPORTANT: ``facts`` must be ``information_gathered`` (confirmed facts only).
    Unconfirmed facts must never be included to prevent score inflation.
    """
    entries: list[tuple[HypothesisEntry, int, int]] = []

    for config in domain.hypotheses:
        score, sup, con = score_hypothesis(config, facts, denied)
        entry = HypothesisEntry(
            id=config.id,
            name=config.name,
            score=score,
            supporting=sup,
            contradicting=con,
        )
        entries.append((entry, len(sup), len(con)))

    positive = [(e, s, c) for e, s, c in entries if e.score > 0]
    positive.sort(key=lambda t: t[0].score, reverse=True)

    ruled_out = [e for e, s, c in entries if c > s and e.score <= 0]

    leading = positive[0][0] if positive else None
    differential = [e for e, _, _ in positive[1:]]

    return Hypothesis(leading=leading, differential=differential, ruled_out=ruled_out)


def compute_overall_confidence(
    leading_score: float,
    domain: DomainProfile,
) -> Confidence:
    """Map the leading hypothesis score to a Confidence enum using domain thresholds."""
    if leading_score >= domain.thresholds.high:
        return Confidence.HIGH
    if leading_score >= domain.thresholds.moderate:
        return Confidence.MODERATE
    return Confidence.LOW
