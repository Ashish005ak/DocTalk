from __future__ import annotations

from backend.domain.models import DomainProfile
from backend.models.hypothesis import Hypothesis
from backend.models.state import Phase


def compute_phase(
    hypothesis: Hypothesis | None,
    remaining_gaps: list[str],
    turn_count: int,
    domain: DomainProfile,
) -> Phase:
    """Determine the current consultation phase based on clinical state.

    Transition rules (evaluated in priority order):
      1. First turn is always INTAKE.
      2. Max turns reached forces SUMMARY.
      3. High confidence + no gaps -> SUMMARY.
      4. Moderate confidence -> NARROWING.
      5. Default -> EXPLORING.
    """
    if turn_count == 0:
        return Phase.INTAKE

    if turn_count >= domain.thresholds.max_turns:
        return Phase.SUMMARY

    if hypothesis is None or hypothesis.leading is None:
        return Phase.EXPLORING

    leading_score = hypothesis.leading.score

    if leading_score >= domain.thresholds.high and len(remaining_gaps) == 0:
        return Phase.SUMMARY

    if leading_score >= domain.thresholds.moderate:
        return Phase.NARROWING

    return Phase.EXPLORING
