from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from backend.llm.fact_extractor import extract_facts
from backend.models.facts import FactConfidence


def _mock_client(return_value=None, side_effect=None):
    client = AsyncMock()
    client.complete = AsyncMock(return_value=return_value, side_effect=side_effect)
    return client


class TestExtractFacts:
    @pytest.mark.asyncio
    async def test_basic_extraction(self):
        raw_json = '[{"key": "Headache", "value": "frontal", "denied": false, "confidence": "high"}]'
        client = _mock_client(return_value=raw_json)
        facts = await extract_facts(
            client,
            message="It hurts in the front of my head",
            last_question_topic="headache location",
            information_gathered={},
        )
        assert len(facts) == 1
        assert facts[0].key == "Headache"
        assert facts[0].value == "frontal"
        assert facts[0].confidence == FactConfidence.HIGH

    @pytest.mark.asyncio
    async def test_empty_on_error(self):
        client = _mock_client(side_effect=RuntimeError("boom"))
        facts = await extract_facts(
            client,
            message="something",
            last_question_topic=None,
            information_gathered={},
        )
        assert facts == []

    @pytest.mark.asyncio
    async def test_denied_fact(self):
        raw_json = '[{"key": "Fever", "value": "", "denied": true, "confidence": "high"}]'
        client = _mock_client(return_value=raw_json)
        facts = await extract_facts(
            client,
            message="No I don't have a fever",
            last_question_topic="fever",
            information_gathered={},
        )
        assert len(facts) == 1
        assert facts[0].denied is True

    @pytest.mark.asyncio
    async def test_multiple_facts(self):
        raw_json = (
            '[{"key": "Headache", "value": "severe", "denied": false, "confidence": "high"},'
            ' {"key": "Nausea", "value": "yes", "denied": false, "confidence": "medium"}]'
        )
        client = _mock_client(return_value=raw_json)
        facts = await extract_facts(
            client,
            message="I have a severe headache and feel nauseous",
            last_question_topic=None,
            information_gathered={},
        )
        assert len(facts) == 2
        assert facts[0].key == "Headache"
        assert facts[1].key == "Nausea"
        assert facts[1].confidence == FactConfidence.MEDIUM

    @pytest.mark.asyncio
    async def test_placeholder_values_filtered(self):
        raw_json = '[{"key": "Cough", "value": "not specified", "denied": false, "confidence": "high"}]'
        client = _mock_client(return_value=raw_json)
        facts = await extract_facts(
            client,
            message="I'm not sure about a cough",
            last_question_topic="cough",
            information_gathered={},
        )
        assert len(facts) == 0

    @pytest.mark.asyncio
    async def test_empty_message_returns_empty(self):
        client = _mock_client()
        facts = await extract_facts(
            client,
            message="",
            last_question_topic=None,
            information_gathered={},
        )
        assert facts == []

    @pytest.mark.asyncio
    async def test_markdown_fences_stripped(self):
        raw_json = '```json\n[{"key": "Fever", "value": "39C", "denied": false, "confidence": "high"}]\n```'
        client = _mock_client(return_value=raw_json)
        facts = await extract_facts(
            client,
            message="My temperature is 39C",
            last_question_topic="fever",
            information_gathered={},
        )
        assert len(facts) == 1
        assert facts[0].key == "Fever"
