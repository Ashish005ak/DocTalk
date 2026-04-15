from __future__ import annotations

from backend.agent.routing import route_after_intake
from backend.models.state import PatientIntent


class TestRouteAfterIntake:
    def test_crisis_intent_routes_to_crisis(self):
        state = {"intake_intent": PatientIntent.CRISIS.value}
        assert route_after_intake(state) == "crisis"

    def test_answering_intent_routes_to_reason(self):
        state = {"intake_intent": PatientIntent.ANSWERING.value}
        assert route_after_intake(state) == "reason"

    def test_mixed_intent_routes_to_reason(self):
        state = {"intake_intent": PatientIntent.MIXED.value}
        assert route_after_intake(state) == "reason"

    def test_asking_explanation_routes_to_reason(self):
        state = {"intake_intent": PatientIntent.ASKING_EXPLANATION.value}
        assert route_after_intake(state) == "reason"

    def test_expressing_concern_routes_to_reason(self):
        state = {"intake_intent": PatientIntent.EXPRESSING_CONCERN.value}
        assert route_after_intake(state) == "reason"

    def test_missing_intent_defaults_to_reason(self):
        state = {}
        assert route_after_intake(state) == "reason"
