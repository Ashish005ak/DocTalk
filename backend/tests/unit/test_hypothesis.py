from backend.clinical.hypothesis import (
    compute_overall_confidence,
    score_all_hypotheses,
    score_hypothesis,
)
from backend.domain.models import (
    ConfidenceThresholds,
    DomainProfile,
    HypothesisConfig,
)
from backend.models.state import Confidence


def _make_domain(*hyps: HypothesisConfig, high: float = 0.75, moderate: float = 0.45) -> DomainProfile:
    return DomainProfile(
        id="test",
        name="Test",
        description="test",
        opening_message="hi",
        hypotheses=list(hyps),
        thresholds=ConfidenceThresholds(high=high, moderate=moderate),
    )


class TestScoreHypothesis:
    def test_full_supporting(self):
        config = HypothesisConfig(
            id="cold", name="Cold",
            supporting_keys=["Cough", "Fever", "Runny nose"],
            prior_weight=1.0,
        )
        facts = {"Cough": "dry", "Fever": "mild", "Runny nose": "yes"}
        score, sup, con = score_hypothesis(config, facts, set())
        assert score == 1.0
        assert len(sup) == 3
        assert con == []

    def test_partial_supporting(self):
        config = HypothesisConfig(
            id="cold", name="Cold",
            supporting_keys=["Cough", "Fever", "Runny nose", "Sneezing"],
            prior_weight=1.0,
        )
        facts = {"Cough": "dry", "Fever": "mild"}
        score, sup, con = score_hypothesis(config, facts, set())
        assert score == 0.5
        assert len(sup) == 2

    def test_contradicting_lowers_score(self):
        config = HypothesisConfig(
            id="cold", name="Cold",
            supporting_keys=["Cough", "Fever"],
            contradicting_keys=["Chest pain"],
            prior_weight=1.0,
        )
        facts = {"Cough": "dry", "Chest pain": "crushing"}
        score, sup, con = score_hypothesis(config, facts, set())
        assert score == 0.0  # (1 - 1) / 2 = 0
        assert len(con) == 1

    def test_no_matching_facts(self):
        config = HypothesisConfig(
            id="cold", name="Cold",
            supporting_keys=["Cough", "Fever"],
        )
        score, sup, con = score_hypothesis(config, {}, set())
        assert score == 0.0
        assert sup == []

    def test_prior_weight_scaling(self):
        config = HypothesisConfig(
            id="rare", name="Rare",
            supporting_keys=["Symptom A", "Symptom B"],
            prior_weight=0.5,
        )
        facts = {"Symptom A": "yes", "Symptom B": "yes"}
        score, sup, con = score_hypothesis(config, facts, set())
        assert score == 0.5  # (2 * 0.5) / 2

    def test_denied_counts_as_contradiction(self):
        config = HypothesisConfig(
            id="cold", name="Cold",
            supporting_keys=["Cough"],
            contradicting_keys=["No fever"],
        )
        facts = {"Cough": "dry"}
        denied = {"No fever"}
        score, sup, con = score_hypothesis(config, facts, denied)
        assert len(con) == 1

    def test_substring_matching_in_values(self):
        config = HypothesisConfig(
            id="mi", name="MI",
            supporting_keys=["Crushing pressure"],
        )
        facts = {"Chest_pain": "crushing pressure in center"}
        score, sup, con = score_hypothesis(config, facts, set())
        assert len(sup) == 1

    def test_empty_supporting_keys(self):
        config = HypothesisConfig(id="x", name="X", supporting_keys=[])
        score, sup, con = score_hypothesis(config, {"A": "1"}, set())
        assert score == 0.0


class TestScoreAllHypotheses:
    def test_leading_and_differential(self):
        h1 = HypothesisConfig(id="a", name="A", supporting_keys=["X", "Y"], prior_weight=1.0)
        h2 = HypothesisConfig(id="b", name="B", supporting_keys=["X"], prior_weight=1.0)
        domain = _make_domain(h1, h2)
        facts = {"X": "yes", "Y": "yes"}
        result = score_all_hypotheses(domain, facts, set())
        assert result.leading is not None
        assert result.leading.id == "a"
        assert result.leading.score == 1.0
        assert len(result.differential) == 1
        assert result.differential[0].id == "b"

    def test_ruled_out(self):
        h1 = HypothesisConfig(
            id="a", name="A",
            supporting_keys=["X"],
            contradicting_keys=["Y", "Z"],
        )
        domain = _make_domain(h1)
        facts = {"Y": "yes", "Z": "yes"}
        result = score_all_hypotheses(domain, facts, set())
        assert result.leading is None
        assert len(result.ruled_out) == 1
        assert result.ruled_out[0].id == "a"

    def test_empty_facts(self):
        h1 = HypothesisConfig(id="a", name="A", supporting_keys=["X"])
        domain = _make_domain(h1)
        result = score_all_hypotheses(domain, {}, set())
        assert result.leading is None
        assert result.differential == []

    def test_empty_hypotheses(self):
        domain = _make_domain()
        result = score_all_hypotheses(domain, {"X": "yes"}, set())
        assert result.leading is None
        assert result.differential == []
        assert result.ruled_out == []


class TestComputeOverallConfidence:
    def test_high(self):
        domain = _make_domain(high=0.75, moderate=0.45)
        assert compute_overall_confidence(0.80, domain) == Confidence.HIGH

    def test_moderate(self):
        domain = _make_domain(high=0.75, moderate=0.45)
        assert compute_overall_confidence(0.50, domain) == Confidence.MODERATE

    def test_low(self):
        domain = _make_domain(high=0.75, moderate=0.45)
        assert compute_overall_confidence(0.30, domain) == Confidence.LOW

    def test_exact_high_boundary(self):
        domain = _make_domain(high=0.75, moderate=0.45)
        assert compute_overall_confidence(0.75, domain) == Confidence.HIGH

    def test_exact_moderate_boundary(self):
        domain = _make_domain(high=0.75, moderate=0.45)
        assert compute_overall_confidence(0.45, domain) == Confidence.MODERATE

    def test_zero_score(self):
        domain = _make_domain(high=0.75, moderate=0.45)
        assert compute_overall_confidence(0.0, domain) == Confidence.LOW
