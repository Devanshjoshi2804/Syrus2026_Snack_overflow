from __future__ import annotations

import json
import re

from onboardai.adapters.browser import BrowserAdapter
from onboardai.adapters.e2b import SandboxManager
from onboardai.config import AppConfig
from onboardai.computer_use.prompts import (
    AGENTIC_SYSTEM_PROMPT,
    BASH_TOOL,
    BROWSER_TOOL,
)
from onboardai.llm_backend import LLMBackend
from onboardai.models import ComputerUseInstruction, ComputerUseResult, RunMode, SandboxSession


class ComputerUseWorker:
    """Deterministic command-based execution worker (dev_mock default)."""

    def __init__(
        self,
        config: AppConfig,
        sandbox_manager: SandboxManager,
        browser_adapter: BrowserAdapter,
    ) -> None:
        self.config = config
        self.sandbox_manager = sandbox_manager
        self.browser_adapter = browser_adapter

    def execute(
        self,
        instruction: ComputerUseInstruction,
        session: SandboxSession,
    ) -> ComputerUseResult:
        if instruction.command_plan:
            return self._run_commands(instruction, session)
        if instruction.url:
            if self.browser_adapter.is_available():
                observation, artifacts = self.browser_adapter.open_url(instruction.url)
            else:
                observation = self.sandbox_manager.open_url(session, instruction.url)
                artifacts = []
            return ComputerUseResult(
                task_id=instruction.task_id,
                success=True,
                observations=[observation],
                verified_values={"url": instruction.url},
                artifacts=artifacts,
                raw_transcript=observation,
            )
        return ComputerUseResult(
            task_id=instruction.task_id,
            success=False,
            failure_reason="No deterministic execution path defined for this task.",
        )

    def _run_commands(
        self,
        instruction: ComputerUseInstruction,
        session: SandboxSession,
    ) -> ComputerUseResult:
        transcript_parts: list[str] = []
        verified_values: dict[str, str] = {}
        observations: list[str] = []
        for command in instruction.command_plan:
            output = self.sandbox_manager.run_command(session, command)
            transcript_parts.append(f"$ {command}\n{output}".strip())
            observations.append(f"Ran: {command}")
            for key, pattern in instruction.expected_patterns.items():
                if key in verified_values:
                    continue
                match = re.search(pattern, output, flags=re.MULTILINE)
                if match:
                    verified_values[key] = match.group(0)
        missing = [key for key in instruction.expected_patterns if key not in verified_values]
        success = not missing
        return ComputerUseResult(
            task_id=instruction.task_id,
            success=success,
            observations=observations,
            verified_values=verified_values,
            raw_transcript="\n\n".join(transcript_parts),
            failure_reason=None if success else f"Missing expected patterns: {', '.join(missing)}",
        )


class AgenticComputerUseWorker:
    """LLM-driven agentic execution worker using Groq/Mistral tool-calling loop."""

    def __init__(
        self,
        config: AppConfig,
        sandbox_manager: SandboxManager,
        browser_adapter: BrowserAdapter,
        llm_backend: LLMBackend,
    ) -> None:
        self.config = config
        self.sandbox_manager = sandbox_manager
        self.browser_adapter = browser_adapter
        self.llm_backend = llm_backend

    def execute(
        self,
        instruction: ComputerUseInstruction,
        session: SandboxSession,
    ) -> ComputerUseResult:
        # Build the user prompt from the instruction
        user_prompt = self._build_user_prompt(instruction)

        # Select tools based on allowed_tools
        tools = []
        if "bash" in instruction.allowed_tools or not instruction.allowed_tools:
            tools.append(BASH_TOOL)
        if "browser" in instruction.allowed_tools:
            tools.append(BROWSER_TOOL)
        if not tools:
            tools.append(BASH_TOOL)

        # Create tool executor bound to sandbox
        def tool_executor(tool_name: str, arguments: dict) -> str:
            if tool_name == "run_bash":
                command = arguments.get("command", "")
                return self.sandbox_manager.run_command(session, command)
            elif tool_name == "open_browser":
                url = arguments.get("url", "")
                if self.browser_adapter.is_available():
                    observation, _artifacts = self.browser_adapter.open_url(url)
                    return observation
                return self.sandbox_manager.open_url(session, url)
            return f"Unknown tool: {tool_name}"

        # Run the agentic loop
        result = self.llm_backend.tool_call_loop(
            system_prompt=AGENTIC_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            tools=tools,
            tool_executor=tool_executor,
            max_iterations=instruction.timeout_seconds // 30 if instruction.timeout_seconds else 10,
        )

        # Extract verified values from tool call results
        verified_values = self._extract_verified_values(result, instruction)
        observations = [
            f"{call['tool']}({json.dumps(call['arguments'])})" for call in result["tool_calls"]
        ]
        raw_transcript = "\n\n".join(
            f"Tool: {call['tool']}\nArgs: {json.dumps(call['arguments'])}\nResult: {call['result']}"
            for call in result["tool_calls"]
        )

        return ComputerUseResult(
            task_id=instruction.task_id,
            success=result["success"] and not self._has_missing_patterns(verified_values, instruction),
            observations=observations,
            verified_values=verified_values,
            raw_transcript=raw_transcript,
            failure_reason=None if result["success"] else result.get("response", "Agent failed."),
        )

    def _build_user_prompt(self, instruction: ComputerUseInstruction) -> str:
        parts = [
            f"TASK: {instruction.goal}",
            f"Task ID: {instruction.task_id}",
        ]
        if instruction.success_criteria:
            parts.append(f"Success Criteria: {', '.join(instruction.success_criteria)}")
        if instruction.command_plan:
            parts.append(f"Suggested commands:\n" + "\n".join(f"  $ {cmd}" for cmd in instruction.command_plan))
        if instruction.expected_patterns:
            parts.append(f"Expected output patterns: {json.dumps(instruction.expected_patterns)}")
        if instruction.url:
            parts.append(f"URL to open: {instruction.url}")
        return "\n".join(parts)

    def _extract_verified_values(
        self,
        result: dict,
        instruction: ComputerUseInstruction,
    ) -> dict[str, str]:
        verified: dict[str, str] = {}
        for call in result["tool_calls"]:
            output = call.get("result", "")
            for key, pattern in instruction.expected_patterns.items():
                if key in verified:
                    continue
                match = re.search(pattern, output, flags=re.MULTILINE)
                if match:
                    verified[key] = match.group(0)
        return verified

    def _has_missing_patterns(
        self,
        verified: dict[str, str],
        instruction: ComputerUseInstruction,
    ) -> bool:
        return any(key not in verified for key in instruction.expected_patterns)


def build_worker(
    config: AppConfig,
    sandbox_manager: SandboxManager,
    browser_adapter: BrowserAdapter,
    llm_backend: LLMBackend | None = None,
) -> ComputerUseWorker | AgenticComputerUseWorker:
    """Factory: Use agentic worker when LLM backend is available, else deterministic."""
    if (
        config.mode == RunMode.DEMO_REAL
        and llm_backend
        and llm_backend.is_enabled()
        and config.llm_backend in ("groq", "mistral")
    ):
        return AgenticComputerUseWorker(config, sandbox_manager, browser_adapter, llm_backend)
    return ComputerUseWorker(config, sandbox_manager, browser_adapter)
