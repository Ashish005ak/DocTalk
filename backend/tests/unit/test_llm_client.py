from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.context.llm_client import LLMResponseParseError
from backend.llm.client import AgentLLMClient


class _FakeLLMClient:
    """Minimal stand-in for the underlying LLMClient."""
    provider = "fake"

    def __init__(self):
        self.analyze = AsyncMock(return_value="hello world")
        self.analyze_json = AsyncMock(return_value={"key": "value"})


@pytest.fixture
def fake_client():
    underlying = _FakeLLMClient()
    with patch("backend.llm.client.LLMClientFactory") as factory:
        factory.get_client.return_value = underlying
        agent = AgentLLMClient(provider="fake")
    agent._client = underlying
    return agent, underlying


class TestComplete:
    @pytest.mark.asyncio
    async def test_complete_delegates_to_analyze(self, fake_client):
        agent, underlying = fake_client
        underlying.analyze.return_value = "response text"
        result = await agent.complete("sys", "usr", caller="test")
        assert result == "response text"
        underlying.analyze.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_json_delegates(self, fake_client):
        agent, underlying = fake_client
        underlying.analyze_json.return_value = {"answer": 42}
        result = await agent.complete_json("sys", "usr", caller="test")
        assert result == {"answer": 42}
        underlying.analyze_json.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_complete_json_parse_error_propagates(self, fake_client):
        agent, underlying = fake_client
        underlying.analyze_json.side_effect = LLMResponseParseError("bad json")
        with pytest.raises(LLMResponseParseError):
            await agent.complete_json("sys", "usr", caller="test")

    def test_default_provider_from_settings(self):
        with patch("backend.llm.client.LLMClientFactory") as factory, \
             patch("backend.llm.client.settings") as mock_settings:
            mock_settings.llm_provider = "openai"
            mock_settings.openai_model = "gpt-4o"
            factory.get_client.return_value = _FakeLLMClient()
            agent = AgentLLMClient()
            assert agent.provider == "openai"
            factory.get_client.assert_called_once_with("openai")
