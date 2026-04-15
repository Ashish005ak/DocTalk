from backend.clinical.fact_merger import merge_facts
from backend.models.facts import FactConfidence, RawFact


class TestMergeFactsBasic:
    def test_merge_into_empty(self):
        facts = [RawFact(key="Fever", value="high, 39C")]
        updated, denied, conf, *_ = merge_facts({}, facts, {}, 1)
        assert updated == {"Fever": "high, 39C"}
        assert denied == set()
        assert conf == {"Fever": "high"}

    def test_overwrite_existing(self):
        existing = {"Fever": "mild"}
        facts = [RawFact(key="Fever", value="high, 39C")]
        updated, denied, conf, *_ = merge_facts(existing, facts, {"Fever": "high"}, 2)
        assert updated["Fever"] == "high, 39C"

    def test_multiple_new_facts(self):
        facts = [
            RawFact(key="Fever", value="high"),
            RawFact(key="Cough", value="dry"),
        ]
        updated, denied, conf, *_ = merge_facts({}, facts, {}, 1)
        assert updated == {"Fever": "high", "Cough": "dry"}
        assert len(conf) == 2


class TestMergeFactsDenied:
    def test_denied_removes_existing(self):
        existing = {"Fever": "mild"}
        facts = [RawFact(key="Fever", value="", denied=True)]
        updated, denied, conf, *_ = merge_facts(existing, facts, {"Fever": "high"}, 2)
        assert "Fever" not in updated
        assert "Fever" in denied
        assert "Fever" not in conf

    def test_denied_new_key(self):
        facts = [RawFact(key="Cough", value="", denied=True)]
        updated, denied, conf, *_ = merge_facts({}, facts, {}, 1)
        assert "Cough" not in updated
        assert "Cough" in denied

    def test_denied_with_value_still_denies(self):
        facts = [RawFact(key="Fever", value="no fever", denied=True)]
        updated, denied, conf, *_ = merge_facts({}, facts, {}, 1)
        assert "Fever" not in updated
        assert "Fever" in denied


class TestMergeFactsConfidence:
    def test_unclear_discarded(self):
        facts = [RawFact(key="Fever", value="maybe", confidence=FactConfidence.UNCLEAR)]
        updated, denied, conf, unconfirmed, attempts, uncertain = merge_facts({}, facts, {}, 1)
        assert "Fever" not in updated
        assert "Fever" not in unconfirmed
        assert denied == set()
        assert conf == {"Fever": "unclear"}
        assert attempts == {"Fever": 1}

    def test_medium_routed_to_unconfirmed(self):
        facts = [RawFact(key="Fever", value="possibly high", confidence=FactConfidence.MEDIUM)]
        updated, denied, conf, unconfirmed, attempts, uncertain = merge_facts({}, facts, {}, 1)
        assert "Fever" not in updated
        assert unconfirmed == {"Fever": "possibly high"}
        assert conf == {"Fever": "medium"}

    def test_high_merged_normally(self):
        facts = [RawFact(key="Fever", value="39C", confidence=FactConfidence.HIGH)]
        updated, denied, conf, *_ = merge_facts({}, facts, {}, 1)
        assert updated == {"Fever": "39C"}
        assert conf == {"Fever": "high"}

    def test_unclear_does_not_overwrite_existing(self):
        existing = {"Fever": "39C"}
        facts = [RawFact(key="Fever", value="maybe", confidence=FactConfidence.UNCLEAR)]
        updated, denied, conf, unconfirmed, attempts, uncertain = merge_facts(
            existing, facts, {"Fever": "high"}, 2,
        )
        assert updated["Fever"] == "39C"
        assert conf["Fever"] == "unclear"
        assert attempts == {"Fever": 1}


class TestMergeFactsEdgeCases:
    def test_empty_key_skipped(self):
        facts = [RawFact(key="", value="something")]
        updated, denied, conf, *_ = merge_facts({}, facts, {}, 1)
        assert updated == {}
        assert conf == {}

    def test_empty_value_skipped(self):
        facts = [RawFact(key="Fever", value="")]
        updated, denied, conf, *_ = merge_facts({}, facts, {}, 1)
        assert "Fever" not in updated

    def test_empty_facts_list(self):
        existing = {"Fever": "high"}
        updated, denied, conf, *_ = merge_facts(existing, [], {"Fever": "high"}, 1)
        assert updated == {"Fever": "high"}
        assert denied == set()

    def test_last_fact_wins_same_key(self):
        facts = [
            RawFact(key="Fever", value="mild"),
            RawFact(key="Fever", value="high, 39C"),
        ]
        updated, denied, conf, *_ = merge_facts({}, facts, {}, 1)
        assert updated["Fever"] == "high, 39C"

    def test_does_not_mutate_inputs(self):
        existing = {"Fever": "mild"}
        fact_conf = {"Fever": "high"}
        facts = [RawFact(key="Cough", value="dry")]
        merge_facts(existing, facts, fact_conf, 1)
        assert "Cough" not in existing
        assert "Cough" not in fact_conf


class TestMergeFactsThreeWayRouting:
    """Tests for the confidence-based three-way routing paths."""

    def test_high_goes_to_info_gathered(self):
        facts = [RawFact(key="Fever", value="39C", confidence=FactConfidence.HIGH)]
        updated, _, conf, unconfirmed, attempts, uncertain = merge_facts({}, facts, {}, 1)
        assert updated == {"Fever": "39C"}
        assert "Fever" not in unconfirmed
        assert "Fever" not in attempts
        assert conf["Fever"] == "high"

    def test_medium_goes_to_unconfirmed(self):
        facts = [RawFact(key="Cough", value="maybe dry", confidence=FactConfidence.MEDIUM)]
        updated, _, conf, unconfirmed, attempts, uncertain = merge_facts({}, facts, {}, 1)
        assert "Cough" not in updated
        assert unconfirmed == {"Cough": "maybe dry"}
        assert conf["Cough"] == "medium"

    def test_unclear_increments_attempts(self):
        facts = [RawFact(key="Rash", value="not sure", confidence=FactConfidence.UNCLEAR)]
        updated, _, conf, unconfirmed, attempts, uncertain = merge_facts({}, facts, {}, 1)
        assert "Rash" not in updated
        assert "Rash" not in unconfirmed
        assert attempts["Rash"] == 1
        assert "Rash" not in uncertain

    def test_unclear_second_attempt_moves_to_uncertain(self):
        facts = [RawFact(key="Rash", value="still not sure", confidence=FactConfidence.UNCLEAR)]
        _, _, _, _, attempts, uncertain = merge_facts(
            {}, facts, {}, 2,
            clarification_attempts={"Rash": 1},
        )
        assert attempts["Rash"] == 2
        assert uncertain["Rash"] == 2

    def test_unclear_third_attempt_stays_in_uncertain(self):
        facts = [RawFact(key="Rash", value="dunno", confidence=FactConfidence.UNCLEAR)]
        _, _, _, _, attempts, uncertain = merge_facts(
            {}, facts, {}, 3,
            clarification_attempts={"Rash": 2},
            uncertain_fields={"Rash": 2},
        )
        assert attempts["Rash"] == 3
        assert uncertain["Rash"] == 3

    def test_high_promotes_from_unconfirmed(self):
        facts = [RawFact(key="Fever", value="39C confirmed", confidence=FactConfidence.HIGH)]
        updated, _, conf, unconfirmed, _, _ = merge_facts(
            {}, facts, {}, 2,
            unconfirmed_facts={"Fever": "maybe 39C"},
        )
        assert updated == {"Fever": "39C confirmed"}
        assert "Fever" not in unconfirmed

    def test_denied_clears_unconfirmed(self):
        facts = [RawFact(key="Fever", value="", denied=True)]
        updated, denied, conf, unconfirmed, _, _ = merge_facts(
            {}, facts, {}, 2,
            unconfirmed_facts={"Fever": "maybe"},
        )
        assert "Fever" not in updated
        assert "Fever" not in unconfirmed
        assert "Fever" in denied

    def test_mixed_confidence_batch(self):
        facts = [
            RawFact(key="Fever", value="39C", confidence=FactConfidence.HIGH),
            RawFact(key="Cough", value="maybe", confidence=FactConfidence.MEDIUM),
            RawFact(key="Rash", value="unclear", confidence=FactConfidence.UNCLEAR),
        ]
        updated, _, conf, unconfirmed, attempts, uncertain = merge_facts({}, facts, {}, 1)
        assert updated == {"Fever": "39C"}
        assert unconfirmed == {"Cough": "maybe"}
        assert attempts == {"Rash": 1}
        assert uncertain == {}

    def test_does_not_mutate_input_dicts(self):
        existing_unconfirmed = {"Fever": "maybe"}
        existing_attempts = {"Rash": 1}
        existing_uncertain = {}
        facts = [RawFact(key="Cough", value="dry", confidence=FactConfidence.MEDIUM)]
        merge_facts(
            {}, facts, {}, 1,
            unconfirmed_facts=existing_unconfirmed,
            clarification_attempts=existing_attempts,
            uncertain_fields=existing_uncertain,
        )
        assert "Cough" not in existing_unconfirmed
        assert "Cough" not in existing_attempts
