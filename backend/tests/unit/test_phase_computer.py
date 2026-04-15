from backend.clinical.phase_computer import compute_phase
from backend.domain.models import ConfidenceThresholds, DomainProfile
from backend.models.hypothesis import Hypothesis, HypothesisEntry
from backend.models.state import Phase


def _domain(high: float = 0.75, moderate: float = 0.45, max_turns: int = 30) -> DomainProfile:
    return DomainProfile(
        id="test", name="Test", description="", opening_message="",
        thresholds=ConfidenceThresholds(high=high, moderate=moderate, max_turns=max_turns),
    )


def _hyp(score: float) -> Hypothesis:
    return Hypothesis(
        leading=HypothesisEntry(id="a", name="A", score=score),
    )


class TestPhaseComputer:
    def test_first_turn_is_intake(self):
        assert compute_phase(None, [], 0, _domain()) == Phase.INTAKE

    def test_first_turn_intake_even_with_hypothesis(self):
        assert compute_phase(_hyp(0.9), [], 0, _domain()) == Phase.INTAKE

    def test_no_hypothesis_is_exploring(self):
        assert compute_phase(None, ["Fever"], 3, _domain()) == Phase.EXPLORING

    def test_no_leading_is_exploring(self):
        h = Hypothesis(leading=None)
        assert compute_phase(h, ["Fever"], 3, _domain()) == Phase.EXPLORING

    def test_low_score_with_gaps_is_exploring(self):
        assert compute_phase(_hyp(0.2), ["Cough"], 5, _domain()) == Phase.EXPLORING

    def test_moderate_score_is_narrowing(self):
        assert compute_phase(_hyp(0.50), ["Cough"], 5, _domain()) == Phase.NARROWING

    def test_exact_moderate_boundary(self):
        assert compute_phase(_hyp(0.45), ["X"], 5, _domain()) == Phase.NARROWING

    def test_high_score_no_gaps_is_summary(self):
        assert compute_phase(_hyp(0.80), [], 10, _domain()) == Phase.SUMMARY

    def test_exact_high_boundary_no_gaps(self):
        assert compute_phase(_hyp(0.75), [], 10, _domain()) == Phase.SUMMARY

    def test_high_score_with_gaps_is_narrowing(self):
        assert compute_phase(_hyp(0.80), ["Onset"], 10, _domain()) == Phase.NARROWING

    def test_max_turns_forces_summary(self):
        assert compute_phase(_hyp(0.1), ["X", "Y"], 30, _domain(max_turns=30)) == Phase.SUMMARY

    def test_over_max_turns_forces_summary(self):
        assert compute_phase(None, ["X"], 35, _domain(max_turns=30)) == Phase.SUMMARY

    def test_max_turns_overrides_low_confidence(self):
        assert compute_phase(_hyp(0.0), ["A", "B", "C"], 30, _domain(max_turns=30)) == Phase.SUMMARY
