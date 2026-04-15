from backend.clinical.block_manager import (
    advance_block,
    compute_remaining_gaps,
    get_relevant_blocks,
    should_advance_block,
)
from backend.domain.models import DomainProfile, SymptomBlock, SymptomField
from backend.models.hypothesis import Hypothesis, HypothesisEntry


def _field(name: str, required: bool = False) -> SymptomField:
    return SymptomField(name=name, required=required)


def _block(id: str, fields: list[SymptomField], tier: int = 1, conditions: list[str] | None = None) -> SymptomBlock:
    return SymptomBlock(id=id, name=id, fields=fields, tier=tier, activation_conditions=conditions or [])


def _domain(*blocks: SymptomBlock) -> DomainProfile:
    return DomainProfile(
        id="test", name="Test", description="", opening_message="",
        symptom_blocks=list(blocks),
    )


class TestGetRelevantBlocks:
    def test_tier1_always_returned(self):
        b1 = _block("chief", [_field("X")], tier=1)
        b2 = _block("socrates", [_field("Y")], tier=1)
        domain = _domain(b1, b2)
        result = get_relevant_blocks(domain, None, set())
        assert [b.id for b in result] == ["chief", "socrates"]

    def test_completed_excluded(self):
        b1 = _block("chief", [_field("X")], tier=1)
        b2 = _block("socrates", [_field("Y")], tier=1)
        domain = _domain(b1, b2)
        result = get_relevant_blocks(domain, None, {"chief"})
        assert [b.id for b in result] == ["socrates"]

    def test_tier2_excluded_without_condition(self):
        b1 = _block("chief", [_field("X")], tier=1)
        b2 = _block("family", [_field("Y")], tier=2, conditions=["always_after_tier1"])
        domain = _domain(b1, b2)
        result = get_relevant_blocks(domain, None, set())
        assert [b.id for b in result] == ["chief"]

    def test_tier2_included_after_tier1_done(self):
        b1 = _block("chief", [_field("X")], tier=1)
        b2 = _block("past", [_field("Y")], tier=2, conditions=["always_after_tier1"])
        domain = _domain(b1, b2)
        result = get_relevant_blocks(domain, None, {"chief"})
        assert [b.id for b in result] == ["past"]

    def test_tier2_condition_keyword_match(self):
        b1 = _block("chief", [_field("X")], tier=1)
        b2 = _block("infectious", [_field("Y")], tier=2, conditions=["pneumonia"])
        domain = _domain(b1, b2)
        hyp = Hypothesis(leading=HypothesisEntry(id="pneumonia", name="Pneumonia", score=0.6))
        result = get_relevant_blocks(domain, hyp, set())
        ids = [b.id for b in result]
        assert "infectious" in ids

    def test_tier2_condition_not_met(self):
        b1 = _block("chief", [_field("X")], tier=1)
        b2 = _block("infectious", [_field("Y")], tier=2, conditions=["pneumonia"])
        domain = _domain(b1, b2)
        hyp = Hypothesis(leading=HypothesisEntry(id="migraine", name="Migraine", score=0.5))
        result = get_relevant_blocks(domain, hyp, set())
        ids = [b.id for b in result]
        assert "infectious" not in ids

    def test_all_completed_returns_empty(self):
        b1 = _block("chief", [_field("X")], tier=1)
        domain = _domain(b1)
        result = get_relevant_blocks(domain, None, {"chief"})
        assert result == []


class TestComputeRemainingGaps:
    def test_all_gaps(self):
        block = _block("b", [_field("A"), _field("B"), _field("C")])
        gaps = compute_remaining_gaps(block, {}, set())
        assert gaps == ["A", "B", "C"]

    def test_some_gathered(self):
        block = _block("b", [_field("A"), _field("B"), _field("C")])
        gaps = compute_remaining_gaps(block, {"A": "yes", "C": "no"}, set())
        assert gaps == ["B"]

    def test_denied_resolves_gap(self):
        block = _block("b", [_field("A"), _field("B")])
        gaps = compute_remaining_gaps(block, {}, {"B"})
        assert gaps == ["A"]

    def test_no_gaps(self):
        block = _block("b", [_field("A")])
        gaps = compute_remaining_gaps(block, {"A": "yes"}, set())
        assert gaps == []

    def test_empty_block(self):
        block = _block("b", [])
        gaps = compute_remaining_gaps(block, {}, set())
        assert gaps == []


class TestShouldAdvanceBlock:
    def test_no_gaps_advances(self):
        block = _block("b", [_field("A", required=True)])
        assert should_advance_block(block, []) is True

    def test_required_gap_blocks(self):
        block = _block("b", [_field("A", required=True), _field("B")])
        assert should_advance_block(block, ["A"]) is False

    def test_only_optional_gaps_advances(self):
        block = _block("b", [_field("A", required=True), _field("B", required=False)])
        assert should_advance_block(block, ["B"]) is True

    def test_mixed_required_optional_gaps(self):
        block = _block("b", [
            _field("A", required=True),
            _field("B", required=True),
            _field("C", required=False),
        ])
        assert should_advance_block(block, ["A", "C"]) is False
        assert should_advance_block(block, ["C"]) is True


class TestAdvanceBlock:
    def test_advances_to_next(self):
        b1 = _block("chief", [_field("X")], tier=1)
        b2 = _block("socrates", [_field("Y")], tier=1)
        domain = _domain(b1, b2)
        next_id, completed = advance_block("chief", set(), domain, None)
        assert next_id == "socrates"
        assert "chief" in completed

    def test_returns_none_when_all_done(self):
        b1 = _block("chief", [_field("X")], tier=1)
        domain = _domain(b1)
        next_id, completed = advance_block("chief", set(), domain, None)
        assert next_id is None
        assert "chief" in completed

    def test_none_current_block(self):
        b1 = _block("chief", [_field("X")], tier=1)
        domain = _domain(b1)
        next_id, completed = advance_block(None, set(), domain, None)
        assert next_id == "chief"
        assert completed == set()

    def test_does_not_mutate_completed(self):
        b1 = _block("chief", [_field("X")], tier=1)
        b2 = _block("socrates", [_field("Y")], tier=1)
        domain = _domain(b1, b2)
        original = set()
        advance_block("chief", original, domain, None)
        assert original == set()
