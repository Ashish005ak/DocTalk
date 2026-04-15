from backend.clinical.red_flag_guard import RedFlagGuard, RedFlagStatus
from backend.domain.models import DomainProfile, RedFlagConfig


def _domain(*flags: RedFlagConfig) -> DomainProfile:
    return DomainProfile(
        id="test", name="Test", description="", opening_message="",
        red_flags=list(flags),
    )


def _meningitis_rule() -> RedFlagConfig:
    return RedFlagConfig(
        id="meningitis_triad",
        name="Meningitis Triad",
        required_keys=["Fever"],
        at_least_one_of=["Neck stiffness", "Photophobia", "Altered consciousness"],
        qualifiers={"Fever": ["high", "high fever", ">103", ">39"]},
        message="Seek emergency care.",
        severity="critical",
    )


def _mi_rule() -> RedFlagConfig:
    return RedFlagConfig(
        id="acute_mi",
        name="Acute MI",
        required_keys=["Chest pain"],
        at_least_one_of=["Arm pain", "Jaw pain", "Sweating", "Nausea"],
        qualifiers={"Chest_pain": ["crushing", "pressure", "heavy", "radiating"]},
        message="Call 911.",
        severity="critical",
    )


def _sah_rule() -> RedFlagConfig:
    return RedFlagConfig(
        id="sah",
        name="SAH",
        required_keys=["Severe headache"],
        at_least_one_of=["Sudden onset", "Worst-ever", "Thunderclap"],
        qualifiers={"Severe_headache": ["worst ever", "thunderclap", "sudden"]},
        message="Emergency.",
        severity="critical",
    )


def _stroke_rule() -> RedFlagConfig:
    return RedFlagConfig(
        id="stroke",
        name="Stroke",
        required_keys=[],
        at_least_one_of=["Unilateral weakness", "Speech difficulty", "Facial droop"],
        qualifiers={},
        message="Time critical.",
        severity="critical",
    )


class TestMeningitisTriad:
    def test_triggers_with_high_fever_and_neck_stiffness(self):
        guard = RedFlagGuard(_domain(_meningitis_rule()))
        facts = {"Fever": "high fever, 39.5C", "Neck stiffness": "yes"}
        result = guard.check(facts, set(), set(), {})
        assert len(result) == 1
        assert result[0].id == "meningitis_triad"

    def test_does_not_trigger_mild_fever(self):
        guard = RedFlagGuard(_domain(_meningitis_rule()))
        facts = {"Fever": "mild, 37.5C", "Neck stiffness": "yes"}
        result = guard.check(facts, set(), set(), {})
        assert len(result) == 0

    def test_does_not_trigger_without_at_least_one(self):
        guard = RedFlagGuard(_domain(_meningitis_rule()))
        facts = {"Fever": "high fever"}
        result = guard.check(facts, set(), set(), {})
        assert len(result) == 0

    def test_triggers_with_photophobia(self):
        guard = RedFlagGuard(_domain(_meningitis_rule()))
        facts = {"Fever": "high, >39", "Photophobia": "yes"}
        result = guard.check(facts, set(), set(), {})
        assert len(result) == 1


class TestAcuteMI:
    def test_triggers_crushing_chest_pain_with_arm_pain(self):
        guard = RedFlagGuard(_domain(_mi_rule()))
        facts = {"Chest pain": "yes", "Chest_pain": "crushing pressure", "Arm pain": "left arm"}
        result = guard.check(facts, set(), set(), {})
        assert len(result) == 1
        assert result[0].id == "acute_mi"

    def test_no_trigger_without_qualifier(self):
        guard = RedFlagGuard(_domain(_mi_rule()))
        facts = {"Chest pain": "yes", "Chest_pain": "mild ache", "Arm pain": "left"}
        result = guard.check(facts, set(), set(), {})
        assert len(result) == 0


class TestSAH:
    def test_triggers_worst_ever_headache(self):
        guard = RedFlagGuard(_domain(_sah_rule()))
        facts = {"Severe headache": "yes", "Severe_headache": "worst ever headache", "Sudden onset": "yes"}
        result = guard.check(facts, set(), set(), {})
        assert len(result) == 1
        assert result[0].id == "sah"


class TestStrokeNoRequiredKeys:
    def test_triggers_with_at_least_one(self):
        guard = RedFlagGuard(_domain(_stroke_rule()))
        facts = {"Facial droop": "right side"}
        result = guard.check(facts, set(), set(), {})
        assert len(result) == 1
        assert result[0].id == "stroke"

    def test_no_trigger_without_any(self):
        guard = RedFlagGuard(_domain(_stroke_rule()))
        facts = {"Headache": "mild"}
        result = guard.check(facts, set(), set(), {})
        assert len(result) == 0


class TestSkipBehavior:
    def test_skips_already_confirmed(self):
        guard = RedFlagGuard(_domain(_stroke_rule()))
        facts = {"Facial droop": "yes"}
        result = guard.check(facts, set(), {"stroke"}, {})
        assert len(result) == 0

    def test_skips_unchanged_facts(self):
        guard = RedFlagGuard(_domain(_stroke_rule()))
        facts = {"Facial droop": "yes"}
        result = guard.check(facts, set(), set(), facts)
        assert len(result) == 0

    def test_re_evaluates_on_changed_facts(self):
        guard = RedFlagGuard(_domain(_stroke_rule()))
        old_facts = {"Headache": "mild"}
        new_facts = {"Headache": "mild", "Facial droop": "yes"}
        result = guard.check(new_facts, set(), set(), old_facts)
        assert len(result) == 1


class TestDeniedSymptoms:
    def test_denied_required_key_prevents_trigger(self):
        guard = RedFlagGuard(_domain(_meningitis_rule()))
        facts = {"Neck stiffness": "yes"}
        denied = {"Fever"}
        result = guard.check(facts, denied, set(), {})
        assert len(result) == 0

    def test_denied_does_not_affect_at_least_one(self):
        guard = RedFlagGuard(_domain(_meningitis_rule()))
        facts = {"Fever": "high fever", "Photophobia": "yes"}
        denied = {"Neck stiffness"}
        result = guard.check(facts, denied, set(), {})
        assert len(result) == 1


class TestCandidateDenialLogic:
    """Tests for check_with_candidates respecting denied symptoms in at_least_one_of."""

    def test_all_at_least_one_denied_returns_clear(self):
        guard = RedFlagGuard(_domain(_meningitis_rule()))
        facts = {"Fever": "high fever"}
        denied = {"Neck stiffness", "Photophobia", "Altered consciousness"}
        _confirmed, candidates = guard.check_with_candidates(facts, denied, set(), {})
        assert len(candidates) == 0
        assert len(_confirmed) == 0

    def test_some_at_least_one_denied_still_candidate(self):
        guard = RedFlagGuard(_domain(_meningitis_rule()))
        facts = {"Fever": "high fever"}
        denied = {"Neck stiffness"}
        _confirmed, candidates = guard.check_with_candidates(facts, denied, set(), {})
        assert len(candidates) == 1
        assert candidates[0].id == "meningitis_triad"

    def test_denied_at_least_one_with_another_present_still_confirms(self):
        guard = RedFlagGuard(_domain(_meningitis_rule()))
        facts = {"Fever": "high fever", "Photophobia": "yes"}
        denied = {"Neck stiffness"}
        confirmed, _candidates = guard.check_with_candidates(facts, denied, set(), {})
        assert len(confirmed) == 1
        assert confirmed[0].id == "meningitis_triad"

    def test_stroke_all_at_least_one_denied_returns_clear(self):
        guard = RedFlagGuard(_domain(_stroke_rule()))
        denied = {"Unilateral weakness", "Speech difficulty", "Facial droop"}
        _confirmed, candidates = guard.check_with_candidates({}, denied, set(), {})
        assert len(candidates) == 0


class TestFindMissingKeyDenial:
    """Tests for _find_missing_key_for_candidate skipping denied keys."""

    def test_skips_denied_key_picks_next(self):
        from backend.agent.nodes.flow_control import _find_missing_key_for_candidate
        from backend.models.red_flag import RedFlagRule

        flag = RedFlagRule(
            id="meningitis_triad", name="Meningitis Triad",
            required_keys=["Fever"],
            at_least_one_of=["Neck stiffness", "Photophobia", "Altered consciousness"],
            qualifiers={}, message="", severity="critical",
        )
        facts = {"Fever": "high"}
        denied = {"Neck stiffness"}
        target = _find_missing_key_for_candidate(flag, facts, denied)
        assert target == "Photophobia"

    def test_returns_none_when_all_missing_are_denied(self):
        from backend.agent.nodes.flow_control import _find_missing_key_for_candidate
        from backend.models.red_flag import RedFlagRule

        flag = RedFlagRule(
            id="meningitis_triad", name="Meningitis Triad",
            required_keys=["Fever"],
            at_least_one_of=["Neck stiffness", "Photophobia", "Altered consciousness"],
            qualifiers={}, message="", severity="critical",
        )
        facts = {"Fever": "high"}
        denied = {"Neck stiffness", "Photophobia", "Altered consciousness"}
        target = _find_missing_key_for_candidate(flag, facts, denied)
        assert target is None


class TestMultipleRules:
    def test_multiple_triggers(self):
        guard = RedFlagGuard(_domain(_stroke_rule(), _sah_rule()))
        facts = {
            "Facial droop": "yes",
            "Severe headache": "yes",
            "Severe_headache": "worst ever",
            "Sudden onset": "yes",
        }
        result = guard.check(facts, set(), set(), {})
        ids = {r.id for r in result}
        assert "stroke" in ids
        assert "sah" in ids

    def test_only_matching_rules_trigger(self):
        guard = RedFlagGuard(_domain(_stroke_rule(), _mi_rule()))
        facts = {"Facial droop": "yes"}
        result = guard.check(facts, set(), set(), {})
        assert len(result) == 1
        assert result[0].id == "stroke"


# =====================================================================
# Scoring engine tests (Clear / Watch / Alert)
# =====================================================================


def _meningitis_rule_with_thresholds(
    soft: int = 1, hard: int = 4,
) -> RedFlagConfig:
    return RedFlagConfig(
        id="meningitis_triad",
        name="Meningitis Triad",
        required_keys=["Fever"],
        at_least_one_of=["Neck_Stiffness", "Photophobia", "Altered_Consciousness"],
        qualifiers={"Fever": ["high", "high fever", ">103", ">39"]},
        message="Seek emergency care.",
        severity="critical",
        soft_threshold=soft,
        hard_threshold=hard,
    )


def _sah_rule_with_thresholds(
    soft: int = 1, hard: int = 2,
) -> RedFlagConfig:
    return RedFlagConfig(
        id="sah",
        name="SAH",
        required_keys=["Headache"],
        at_least_one_of=["Onset"],
        qualifiers={"Headache": ["worst ever", "thunderclap", "sudden"]},
        message="Emergency.",
        severity="critical",
        soft_threshold=soft,
        hard_threshold=hard,
    )


class TestScoreRule:
    """Tests for RedFlagGuard.score_rule()."""

    def test_fever_alone_scores_1(self):
        rule = _meningitis_rule_with_thresholds()
        score, missing = RedFlagGuard.score_rule(rule, {"Fever": "yes"}, set())
        assert score == 1
        assert "Neck_Stiffness" in missing or "Photophobia" in missing

    def test_fever_plus_qualifier_scores_2(self):
        rule = _meningitis_rule_with_thresholds()
        score, _ = RedFlagGuard.score_rule(rule, {"Fever": "high fever 39.5C"}, set())
        assert score == 2  # +1 required_key + 1 qualifier

    def test_fever_plus_qualifier_plus_neck_scores_5(self):
        rule = _meningitis_rule_with_thresholds()
        facts = {"Fever": "high fever", "Neck_Stiffness": "yes"}
        score, _ = RedFlagGuard.score_rule(rule, facts, set())
        assert score == 4  # +1 required + 1 qualifier + 2 at_least_one_of

    def test_denied_required_key_returns_negative(self):
        rule = _meningitis_rule_with_thresholds()
        score, _ = RedFlagGuard.score_rule(rule, {}, {"Fever"})
        assert score == -1

    def test_all_at_least_one_denied_returns_negative(self):
        rule = _meningitis_rule_with_thresholds()
        facts = {"Fever": "high fever"}
        denied = {"Neck_Stiffness", "Photophobia", "Altered_Consciousness"}
        score, _ = RedFlagGuard.score_rule(rule, facts, denied)
        assert score == -1

    def test_no_evidence_scores_zero(self):
        rule = _meningitis_rule_with_thresholds()
        score, missing = RedFlagGuard.score_rule(rule, {}, set())
        assert score == 0
        assert "Fever" in missing

    def test_multiple_at_least_one_of_present(self):
        rule = _meningitis_rule_with_thresholds()
        facts = {"Fever": "yes", "Neck_Stiffness": "yes", "Photophobia": "yes"}
        score, _ = RedFlagGuard.score_rule(rule, facts, set())
        # +1 required + 2 at_least_one + 2 at_least_one = 5
        assert score == 5


class TestCheckWithStates:
    """Tests for the three-state Clear/Watch/Alert bucketing."""

    def test_fever_alone_returns_watch(self):
        rule = _meningitis_rule_with_thresholds(soft=1, hard=4)
        guard = RedFlagGuard(_domain(rule))
        alerts, watches, clears = guard.check_with_states(
            {"Fever": "yes"}, set(), set(),
        )
        assert len(watches) == 1
        assert watches[0].state == "watch"
        assert watches[0].score == 1
        assert len(alerts) == 0

    def test_fever_qualifier_neck_returns_alert(self):
        rule = _meningitis_rule_with_thresholds(soft=1, hard=4)
        guard = RedFlagGuard(_domain(rule))
        facts = {"Fever": "high fever", "Neck_Stiffness": "yes"}
        alerts, watches, _ = guard.check_with_states(facts, set(), set())
        assert len(alerts) == 1
        assert alerts[0].state == "alert"
        assert alerts[0].score >= 4

    def test_denied_required_key_returns_clear(self):
        rule = _meningitis_rule_with_thresholds()
        guard = RedFlagGuard(_domain(rule))
        alerts, watches, clears = guard.check_with_states(
            {}, {"Fever"}, set(),
        )
        assert len(clears) == 1
        assert clears[0].state == "clear"
        assert len(alerts) == 0
        assert len(watches) == 0

    def test_no_evidence_returns_clear(self):
        rule = _meningitis_rule_with_thresholds()
        guard = RedFlagGuard(_domain(rule))
        alerts, watches, clears = guard.check_with_states({}, set(), set())
        assert len(clears) == 1
        assert clears[0].state == "clear"

    def test_sah_low_hard_threshold_alerts_quickly(self):
        rule = _sah_rule_with_thresholds(soft=1, hard=2)
        guard = RedFlagGuard(_domain(rule))
        facts = {"Headache": "thunderclap headache"}
        alerts, watches, _ = guard.check_with_states(facts, set(), set())
        # score = 1 (required) + 1 (qualifier) = 2 >= hard=2 → alert
        assert len(alerts) == 1
        assert alerts[0].state == "alert"

    def test_custom_thresholds_respected(self):
        rule = _meningitis_rule_with_thresholds(soft=3, hard=5)
        guard = RedFlagGuard(_domain(rule))
        facts = {"Fever": "high fever"}
        # score = 2 (required + qualifier), but soft=3 → clear
        alerts, watches, clears = guard.check_with_states(facts, set(), set())
        assert len(clears) == 1
        assert clears[0].state == "clear"
        assert len(watches) == 0

    def test_watch_since_turn_persists(self):
        rule = _meningitis_rule_with_thresholds(soft=1, hard=4)
        guard = RedFlagGuard(_domain(rule))
        prev_watch = {"meningitis_triad": {"since_turn": 2, "score": 1, "missing_keys": []}}
        _, watches, _ = guard.check_with_states(
            {"Fever": "yes"}, set(), set(),
            current_turn=5,
            prev_watch_flags=prev_watch,
        )
        assert len(watches) == 1
        assert watches[0].watch_since_turn == 2  # preserved from prior turn

    def test_confirmed_flags_are_skipped(self):
        rule = _meningitis_rule_with_thresholds()
        guard = RedFlagGuard(_domain(rule))
        facts = {"Fever": "high fever", "Neck_Stiffness": "yes"}
        alerts, watches, clears = guard.check_with_states(
            facts, set(), {"meningitis_triad"},
        )
        assert len(alerts) == 0
        assert len(watches) == 0
        assert len(clears) == 0
