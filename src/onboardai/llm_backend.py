from __future__ import annotations

import json
from typing import Any

from onboardai.config import AppConfig


class LLMBackend:
    """Unified LLM backend using OpenAI-compatible APIs (Groq / Mistral)."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client
        try:
            from openai import OpenAI
        except ImportError:
            return None
        backend = self.config.llm_backend
        if backend == "groq" and self.config.groq_api_key:
            self._client = OpenAI(
                api_key=self.config.groq_api_key,
                base_url="https://api.groq.com/openai/v1",
            )
        elif backend == "mistral" and self.config.mistral_api_key:
            self._client = OpenAI(
                api_key=self.config.mistral_api_key,
                base_url="https://api.mistral.ai/v1",
            )
        else:
            return None
        return self._client

    def _model_name(self) -> str:
        if self.config.llm_backend == "groq":
            return self.config.groq_model
        return self.config.mistral_model

    def is_enabled(self) -> bool:
        return self._get_client() is not None

    def chat(self, user_message: str, system_context: str) -> str | None:
        """General conversational response with injected task/session context."""
        client = self._get_client()
        if not client:
            return None
        try:
            response = client.chat.completions.create(
                model=self._model_name(),
                messages=[
                    {"role": "system", "content": system_context},
                    {"role": "user", "content": user_message},
                ],
                max_tokens=600,
                temperature=0.4,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return None

    def answer(self, question: str, context: str) -> str | None:
        """RAG QA: generate a grounded answer from retrieved context."""
        client = self._get_client()
        if not client:
            return None
        try:
            response = client.chat.completions.create(
                model=self._model_name(),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are OnboardAI, a developer onboarding assistant for NovaByte Technologies. "
                            "Answer ONLY from the supplied onboarding context. "
                            "If the context is insufficient, say so explicitly and suggest who to contact. "
                            "Keep answers concise and actionable."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Question:\n{question}\n\nContext:\n{context}",
                    },
                ],
                max_tokens=500,
                temperature=0.3,
            )
            return response.choices[0].message.content.strip()
        except Exception:
            return None

    def tool_call_loop(
        self,
        system_prompt: str,
        user_prompt: str,
        tools: list[dict[str, Any]],
        tool_executor: callable,
        max_iterations: int = 10,
    ) -> dict[str, Any]:
        """
        Agentic tool-calling loop. Sends a prompt with tools, executes tool calls,
        feeds results back, and loops until the model stops calling tools.

        Args:
            system_prompt: System instructions for the agent.
            user_prompt: The task description.
            tools: OpenAI-format tool definitions.
            tool_executor: Callable(tool_name, arguments) -> str.
            max_iterations: Safety limit on tool call rounds.

        Returns:
            Dict with 'response' (final text), 'tool_calls' (list of calls made),
            and 'success' flag.
        """
        client = self._get_client()
        if not client:
            return {"response": "LLM backend not configured.", "tool_calls": [], "success": False}

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        all_tool_calls: list[dict[str, Any]] = []

        for _iteration in range(max_iterations):
            try:
                response = client.chat.completions.create(
                    model=self._model_name(),
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    max_tokens=2000,
                    temperature=0.1,
                )
            except Exception as exc:
                return {
                    "response": f"LLM API error: {exc}",
                    "tool_calls": all_tool_calls,
                    "success": False,
                }

            choice = response.choices[0]
            message = choice.message

            # If no tool calls, the model is done
            if not message.tool_calls:
                return {
                    "response": message.content or "",
                    "tool_calls": all_tool_calls,
                    "success": True,
                }

            # Append the assistant message (with tool_calls) to history
            messages.append(message.model_dump())

            # Execute each tool call and append results
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {"raw": tool_call.function.arguments}

                tool_result = tool_executor(func_name, arguments)
                all_tool_calls.append({
                    "tool": func_name,
                    "arguments": arguments,
                    "result": tool_result[:2000],
                })
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result[:4000],
                })

        # Hit max iterations
        return {
            "response": "Agent reached maximum iteration limit.",
            "tool_calls": all_tool_calls,
            "success": len(all_tool_calls) > 0,
        }


def build_llm_backend(config: AppConfig) -> LLMBackend:
    return LLMBackend(config)
