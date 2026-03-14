from __future__ import annotations

import re

from onboardai.adapters.browser import BrowserAdapter
from onboardai.adapters.e2b import SandboxManager
from onboardai.config import AppConfig
from onboardai.models import ComputerUseInstruction, ComputerUseResult, SandboxSession


class ComputerUseWorker:
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
