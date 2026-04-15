from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

from backend.llm.intent_classifier import classify_intent
from backend.models.state import PatientIntent


def _mock_client(return_value=None, side_effect=None):
    client = AsyncMock()
    client.complete = AsyncMock(return_value=return_value, side_effect=side_effect)
    return client


class TestClassifyIntent:
    @pytest.mark.asyncio
    async def test_answering_intent(self):
        client = _mock_client(return_value="answering")
        result = await classify_intent(client, "My head hurts a lot", last_gap="headache_location")
        assert result == PatientIntent.ANSWERING

    @pytest.mark.asyncio
    async def test_crisis_intent(self):
        client = _mock_client(return_value="crisis")
        result = await classify_intent(client, "I want to end it all")
        assert result == PatientIntent.CRISIS

    @pytest.mark.asyncio
    async def test_mixed_intent(self):
        client = _mock_client(return_value="mixed")
        result = await classify_intent(client, "Yes it hurts, but why do you ask?")
        assert result == PatientIntent.MIXED

    @pytest.mark.asyncio
    async def test_fallback_on_garbage(self):
        client = _mock_client(return_value="xyzzy_nonsense_123")
        result = await classify_intent(client, "something")
        assert result == PatientIntent.ANSWERING

    @pytest.mark.asyncio
    async def test_fallback_on_exception(self):
        client = _mock_client(side_effect=RuntimeError("LLM down"))
        result = await classify_intent(client, "something")
        assert result == PatientIntent.ANSWERING

    @pytest.mark.asyncio
    async def test_case_insensitive_parsing(self):
        client = _mock_client(return_value="  ANSWERING  ")
        result = await classify_intent(client, "something")
        assert result == PatientIntent.ANSWERING
