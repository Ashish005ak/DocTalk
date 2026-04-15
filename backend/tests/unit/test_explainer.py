from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from backend.domain.models import DomainProfile, SymptomBlock, SymptomField
from backend.llm.explainer import generate_explanation, _FALLBACK


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
        "pending_explanation": "Why did you ask about my headache?",
        "information_gathered": {"headache": "frontal"},
        "remaining_gaps": ["fever"],
    }
    base.update(overrides)
    return base


class TestGenerateExplanation:
    @pytest.mark.asyncio
    async def test_generates_explanation(self):
        client = _mock_client(
            return_value="Headaches can have many causes. Let me ask about fever next."
        )
        result = await generate_explanation(client, _state(), _domain())
        assert len(result) > 0
        assert result != _FALLBACK

    @pytest.mark.asyncio
    async def test_fallback_on_error(self):
        client = _mock_client(side_effect=RuntimeError("LLM is down"))
        result = await generate_explanation(client, _state(), _domain())
        assert result == _FALLBACK

    @pytest.mark.asyncio
    async def test_fallback_on_empty(self):
        client = _mock_client(return_value="")
        result = await generate_explanation(client, _state(), _domain())
        assert result == _FALLBACK
