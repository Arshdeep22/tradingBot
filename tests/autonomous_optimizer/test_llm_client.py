import json
from unittest.mock import MagicMock, patch

import pytest

from autonomous_optimizer.config import AgentConfig
from autonomous_optimizer.llm.client import AgentLLMClient, LLMError


def _make_client() -> AgentLLMClient:
    """Build a client with AICoreLLM pre-mocked so no env vars are needed."""
    with patch("autonomous_optimizer.llm.client.AgentLLMClient._build_llm") as mock_build:
        mock_build.return_value = MagicMock()
        client = AgentLLMClient(AgentConfig())
    return client


def test_call_parses_valid_json():
    client = _make_client()
    client._llm.chat.return_value = '{"key": "value"}'
    result = client.call("sys", "user")
    assert result == {"key": "value"}


def test_call_strips_markdown_fences():
    client = _make_client()
    client._llm.chat.return_value = '```json\n{"k": "v"}\n```'
    result = client.call("sys", "user")
    assert result == {"k": "v"}


def test_call_strips_plain_fences():
    client = _make_client()
    client._llm.chat.return_value = '```\n{"x": 1}\n```'
    result = client.call("sys", "user")
    assert result == {"x": 1}


def test_call_retries_on_invalid_json():
    client = _make_client()
    client._llm.chat.side_effect = ["not-json", '{"ok": true}']
    result = client.call("sys", "user", max_retries=3)
    assert result == {"ok": True}
    assert client._llm.chat.call_count == 2


def test_call_raises_after_max_retries():
    client = _make_client()
    client._llm.chat.return_value = "invalid json !!!"
    with pytest.raises(LLMError):
        client.call("sys", "user", max_retries=3)
    assert client._llm.chat.call_count == 3


def test_call_not_json_mode_returns_string():
    client = _make_client()
    client._llm.chat.return_value = "plain text response"
    result = client.call("sys", "user", expect_json=False)
    assert result == "plain text response"


def test_missing_env_vars_raises():
    with patch.dict("os.environ", {}, clear=True):
        # Remove all AICORE_ vars from environment
        import os
        env_backup = {k: os.environ.pop(k) for k in list(os.environ) if k.startswith("AICORE_")}
        try:
            with pytest.raises(EnvironmentError, match="Missing required environment variables"):
                AgentLLMClient(AgentConfig())
        finally:
            os.environ.update(env_backup)
