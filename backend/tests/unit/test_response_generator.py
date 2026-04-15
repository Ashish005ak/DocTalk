from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from backend.domain.models import DomainProfile, SymptomBlock, SymptomField
from backend.llm.response_generator import generate_question, _FALLBACK
from backend.models.move import ConversationMove
from backend.models.state import MoveType


def _mock_client(return_value=None, side_effect=None):
    client = AsyncMock()
    client.complete = AsyncMock(return_value=return_value, side_effect=side_effect)
    return client


def _domain() -> DomainProfile:
    block = SymptomBlock(
        id="test",
        name="Test Block",
        fields=[
            SymptomField(name="fever", hint="Do you have a fever?"),
            SymptomField(name="headache", hint="Tell me about your headache"),
        ],
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
        "information_gathered": {"headache": "frontal"},
        "emotional_tone": "neutral",
        "remaining_gaps": ["fever"],
        "pending_explanation": None,
    }
    base.update(overrides)
    return base


class TestGenerateQuestion:
    @pytest.mark.asyncio
    async def test_question_move(self):
        client = _mock_client(return_value="Have you noticed any fever recently?")
        move = ConversationMove(type=MoveType.QUESTION, target_gap="fever")
        result = await generate_question(client, _state(), _domain(), move)
        assert "fever" in result.lower() or len(result) > 0

    @pytest.mark.asyncio
    async def test_red_flag_move(self):
        client = _mock_client(
            return_value="I need to ask urgently — are you experiencing chest pain right now?"
        )
        move = ConversationMove(
            type=MoveType.RED_FLAG_FOLLOWUP,
            red_flag_id="chest_pain_cardiac",
        )
        result = await generate_question(client, _state(), _domain(), move)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_acknowledge_concern_move(self):
        client = _mock_client(
            return_value="I understand this can be worrying. Let's work through this together."
        )
        move = ConversationMove(
            type=MoveType.ACKNOWLEDGE_CONCERN,
            reason="patient expressed anxiety",
        )
        state = _state(emotional_tone="anxious")
        result = await generate_question(client, state, _domain(), move)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_fallback_on_error(self):
        client = _mock_client(side_effect=RuntimeError("LLM down"))
        move = ConversationMove(type=MoveType.QUESTION, target_gap="fever")
        result = await generate_question(client, _state(), _domain(), move)
        assert result == _FALLBACK
