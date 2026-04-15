from __future__ import annotations

from backend.models.facts import FactConfidence, RawFact


def merge_facts(
    existing: dict[str, str],
    new_facts: list[RawFact],
    fact_confidence: dict[str, str],
    turn_count: int,
    unconfirmed_facts: dict[str, str] | None = None,
    clarification_attempts: dict[str, int] | None = None,
    uncertain_fields: dict[str, int] | None = None,
) -> tuple[dict[str, str], set[str], dict[str, str],
           dict[str, str], dict[str, int], dict[str, int]]:
    """Merge extracted facts into the appropriate state dict based on confidence.

    Three routing paths:
      - HIGH    -> merged into information_gathered (confirmed)
      - MEDIUM  -> merged into unconfirmed_facts (stored but not confirmed)
      - UNCLEAR -> not merged; increments clarification_attempts for the field.
                   If attempts >= 2, the field is moved to uncertain_fields
                   and no further clarification is attempted.

    Returns (updated_info_gathered, new_denied_set, updated_fact_confidence,
             updated_unconfirmed_facts, updated_clarification_attempts,
             updated_uncertain_fields).
    """
    updated = dict(existing)
    denied: set[str] = set()
    conf = dict(fact_confidence)
    unconfirmed = dict(unconfirmed_facts or {})
    attempts = dict(clarification_attempts or {})
    uncertain = dict(uncertain_fields or {})

    for fact in new_facts:
        if not fact.key:
            continue

        if fact.denied:
            denied.add(fact.key)
            updated.pop(fact.key, None)
            unconfirmed.pop(fact.key, None)
            conf.pop(fact.key, None)
            continue

        if not fact.value:
            continue

        confidence = (
            fact.confidence
            if isinstance(fact.confidence, FactConfidence)
            else FactConfidence(fact.confidence)
        )

        if confidence == FactConfidence.HIGH:
            updated[fact.key] = fact.value
            conf[fact.key] = confidence.value
            unconfirmed.pop(fact.key, None)

        elif confidence == FactConfidence.MEDIUM:
            unconfirmed[fact.key] = fact.value
            conf[fact.key] = confidence.value

        elif confidence == FactConfidence.UNCLEAR:
            conf[fact.key] = confidence.value
            attempts[fact.key] = attempts.get(fact.key, 0) + 1
            if attempts[fact.key] >= 2:
                uncertain[fact.key] = attempts[fact.key]

    return updated, denied, conf, unconfirmed, attempts, uncertain
