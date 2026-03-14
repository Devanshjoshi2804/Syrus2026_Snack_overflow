from __future__ import annotations

from unittest.mock import MagicMock, patch

from onboardai.config import AppConfig
from onboardai.llm_backend import LLMBackend


def test_llm_backend_answer_returns_string_when_configured(project_root):
    """LLM backend should return a string answer when API is configured."""
    config = AppConfig(
        project_root=project_root,
        llm_backend="groq",
        groq_api_key="test-key",
    )
    backend = LLMBackend(config)

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "The coding standard is trunk-based development."

    with patch("openai.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        MockOpenAI.return_value = mock_client

        backend._client = None
        result = backend.answer("What is the coding standard?", "NovaByte follows trunk-based development.")

    assert result is not None
    assert "trunk-based" in result


def test_llm_backend_tool_call_loop(project_root):
    """Tool call loop should execute tools and return results."""
    config = AppConfig(
        project_root=project_root,
        llm_backend="groq",
        groq_api_key="test-key",
    )
    backend = LLMBackend(config)

    # First response: tool call
    tool_call_msg = MagicMock()
    tool_call_msg.content = None
    tool_call = MagicMock()
    tool_call.function.name = "run_bash"
    tool_call.function.arguments = '{"command": "node --version"}'
    tool_call.id = "call_123"
    tool_call_msg.tool_calls = [tool_call]
    tool_call_msg.model_dump.return_value = {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": "call_123", "function": {"name": "run_bash", "arguments": '{"command": "node --version"}'}, "type": "function"}],
    }

    # Second response: final answer
    final_msg = MagicMock()
    final_msg.content = "Node.js v20.11.0 is installed."
    final_msg.tool_calls = None

    mock_responses = [
        MagicMock(choices=[MagicMock(message=tool_call_msg)]),
        MagicMock(choices=[MagicMock(message=final_msg)]),
    ]

    def mock_executor(name, args):
        return "v20.11.0"

    with patch("openai.OpenAI") as MockOpenAI:
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = mock_responses
        MockOpenAI.return_value = mock_client

        backend._client = None
        result = backend.tool_call_loop(
            system_prompt="You are an agent.",
            user_prompt="Install Node.js 20",
            tools=[{"type": "function", "function": {"name": "run_bash", "parameters": {}}}],
            tool_executor=mock_executor,
        )

    assert result["success"] is True
    assert len(result["tool_calls"]) == 1
    assert result["tool_calls"][0]["tool"] == "run_bash"
    assert "v20.11.0" in result["tool_calls"][0]["result"]


def test_llm_backend_disabled_without_key(project_root):
    """LLM backend should be disabled without an API key."""
    config = AppConfig(project_root=project_root, llm_backend="groq", groq_api_key=None)
    backend = LLMBackend(config)
    assert backend.is_enabled() is False
    assert backend.answer("test", "context") is None
