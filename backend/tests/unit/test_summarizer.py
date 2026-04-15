from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from backend.domain.models import DomainProfile, SymptomBlock, SymptomField
from backend.llm.summarizer import generate_summary, _DISCLAIMER, _FALLBACK
from backend.models.hypothesis import Hypothesis, HypothesisEntry


def _mock_client(return_value=None, side_effect=None):
    client = AsyncMock()
    client.complete = AsyncMock(return_value=return_value, side_effect=side_effect)
    return client


def _domain() -> DomainProfile:
    block = SymptomBlock(
        id="test",
        name="Test Block",
        fields=[SymptomField(name="fever", hint="Do you have a fever?")],
    )
    return DomainProfile(
        id="test",
        name="Test",
        description="test domain",
        opening_message="hi",
        symptom_blocks=[block],
    )


def _state(**overrides) -> dict:
    base = {
        "information_gathered": {"headache": "frontal", "fever": "38.5C"},
        "denied_symptoms": {"nausea"},
        "hypothesis": Hypothesis(
            leading=HypothesisEntry(
                name="Tension Headache",
                score=0.75,
                supporting_evidence="headache",
                missing_evidence="",
            )
        ),
        "confirmed_red_flag_ids": set(),
    }
    base.update(overrides)
    return base


class TestGenerateSummary:
    @pytest.mark.asyncio
    async def test_generates_summary(self):
        client = _mock_client(
            return_value="## Symptoms Reported\n- Frontal headache\n- Fever 38.5C"
        )
        result = await generate_summary(client, _state(), _domain())
        assert "Symptoms Reported" in result
        assert _DISCLAIMER in result

    @pytest.mark.asyncio
    async def test_disclaimer_always_present(self):
        client = _mock_client(return_value="Some summary without disclaimer")
        result = await generate_summary(client, _state(), _domain())
        assert result.endswith(_DISCLAIMER)
        assert "IMPORTANT DISCLAIMER" in result

    @pytest.mark.asyncio
    async def test_fallback_on_error(self):
        client = _mock_client(side_effect=RuntimeError("LLM down"))
        result = await generate_summary(client, _state(), _domain())
        assert result == _FALLBACK
        assert "IMPORTANT DISCLAIMER" in result

    @pytest.mark.asyncio
    async def test_fallback_on_empty_response(self):
        client = _mock_client(return_value="")
        result = await generate_summary(client, _state(), _domain())
        assert result == _FALLBACK
        assert "IMPORTANT DISCLAIMER" in result
