from __future__ import annotations

from backend.domain.models import DomainProfile, HypothesisConfig, SymptomBlock
from backend.models.hypothesis import Hypothesis


def _tier1_ids(domain: DomainProfile) -> set[str]:
    return {b.id for b in domain.symptom_blocks if b.tier == 1}


def _all_tier1_completed(domain: DomainProfile, completed_ids: set[str]) -> bool:
    return _tier1_ids(domain).issubset(completed_ids)


def _condition_met(
    condition: str,
    domain: DomainProfile,
    hypothesis: Hypothesis | None,
    completed_ids: set[str],
) -> bool:
    """Evaluate a single activation condition for a tier-2 block."""
    if condition == "always_after_tier1":
        return _all_tier1_completed(domain, completed_ids)

    if hypothesis is None:
        return False

    all_entries = []
    if hypothesis.leading:
        all_entries.append(hypothesis.leading)
    all_entries.extend(hypothesis.differential)

    cond_lower = condition.lower()
    for entry in all_entries:
        if cond_lower in entry.id.lower() or cond_lower in entry.name.lower():
            return True

    return False


def get_relevant_blocks(
    domain: DomainProfile,
    hypothesis: Hypothesis | None,
    completed_ids: set[str],
) -> list[SymptomBlock]:
    """Return symptom blocks that should be active, excluding already-completed ones."""
    relevant: list[SymptomBlock] = []
    for block in domain.symptom_blocks:
        if block.id in completed_ids:
            continue
        if block.tier == 1:
            relevant.append(block)
        elif block.tier == 2:
            if any(
                _condition_met(c, domain, hypothesis, completed_ids)
                for c in block.activation_conditions
            ):
                relevant.append(block)
    return relevant


def _should_skip_field(
    f: "SymptomField",
    info_gathered: dict[str, str],
) -> bool:
    """Check if a field should be skipped based on its skip_if condition."""
    if not f.skip_if:
        return False
    dep_field = f.skip_if.get("field", "")
    dep_value = f.skip_if.get("value", "")
    gathered_value = info_gathered.get(dep_field, "")
    return gathered_value.lower().strip() == dep_value.lower().strip()


def compute_remaining_gaps(
    block: SymptomBlock,
    info_gathered: dict[str, str],
    denied: set[str],
) -> list[str]:
    """Return field names in the block that are not yet gathered or denied.

    Fields with a satisfied ``skip_if`` condition are excluded.
    """
    from backend.domain.models import SymptomField  # noqa: F811

    return [
        f.name
        for f in block.fields
        if f.name not in info_gathered
        and f.name not in denied
        and not _should_skip_field(f, info_gathered)
    ]


def should_advance_block(
    block: SymptomBlock,
    remaining_gaps: list[str],
) -> bool:
    """True when the block can be considered done.

    A block is done when:
      - all required fields are resolved (gathered or denied), OR
      - every field (required + optional) is resolved.
    """
    if not remaining_gaps:
        return True

    required_fields = {f.name for f in block.fields if f.required}
    required_gaps = [g for g in remaining_gaps if g in required_fields]
    return len(required_gaps) == 0


def advance_block(
    current_block_id: str | None,
    completed_block_ids: set[str],
    domain: DomainProfile,
    hypothesis: Hypothesis | None,
) -> tuple[str | None, set[str]]:
    """Complete the current block and move to the next relevant one.

    Returns (next_block_id_or_None, updated_completed_ids).
    """
    updated_completed = set(completed_block_ids)
    if current_block_id is not None:
        updated_completed.add(current_block_id)

    relevant = get_relevant_blocks(domain, hypothesis, updated_completed)
    next_id = relevant[0].id if relevant else None
    return next_id, updated_completed


def _field_relevant_to_hypothesis(
    field_name: str,
    hyp_config: HypothesisConfig,
) -> bool:
    """Check if a field name appears in a hypothesis's supporting keys (case-insensitive)."""
    name_lower = field_name.lower()
    for key in hyp_config.supporting_keys:
        if name_lower in key.lower() or key.lower() in name_lower:
            return True
    return False


def compute_revisit_gaps(
    uncertain_fields: dict[str, int],
    unconfirmed_facts: dict[str, str],
    domain: DomainProfile,
    hypothesis: Hypothesis | None,
) -> tuple[list[str], dict[str, int], dict[str, str]]:
    """Revisit hook: surface clinically relevant uncertain/unconfirmed fields as open gaps.

    For each field in uncertain_fields and unconfirmed_facts:
      1. Check if is_supporting_key is True on the SymptomField in the domain config.
      2. Check if any hypothesis that lists this field as a supporting key has
         a score above 0.3.

    If BOTH conditions are met: surface the field as an open gap for revisiting.
    If EITHER condition is false: discard the field permanently by removing it
    from uncertain_fields or unconfirmed_facts.

    Returns (revisit_gaps, pruned_uncertain_fields, pruned_unconfirmed_facts).
    """
    revisit_gaps: list[str] = []
    pruned_uncertain = dict(uncertain_fields)
    pruned_unconfirmed = dict(unconfirmed_facts)

    all_field_keys = set(uncertain_fields.keys()) | set(unconfirmed_facts.keys())

    scored_entries = []
    if hypothesis is not None:
        if hypothesis.leading:
            scored_entries.append(hypothesis.leading)
        scored_entries.extend(hypothesis.differential)

    for field_key in all_field_keys:
        sym_field = domain.get_field(field_key)
        is_supporting = sym_field is not None and sym_field.is_supporting_key

        has_active_hypothesis = False
        if is_supporting:
            for entry in scored_entries:
                hyp_config = domain.get_hypothesis_by_id(entry.id)
                if hyp_config is None:
                    continue
                if _field_relevant_to_hypothesis(field_key, hyp_config) and entry.score > 0.3:
                    has_active_hypothesis = True
                    break

        if is_supporting and has_active_hypothesis:
            revisit_gaps.append(field_key)
        else:
            pruned_uncertain.pop(field_key, None)
            pruned_unconfirmed.pop(field_key, None)

    return revisit_gaps, pruned_uncertain, pruned_unconfirmed
