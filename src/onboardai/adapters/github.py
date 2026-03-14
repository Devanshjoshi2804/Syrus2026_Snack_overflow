from __future__ import annotations

import os

from onboardai.models import IntegrationResult, OnboardingState


class GitHubAdapter:
    def __init__(self) -> None:
        self.token = os.getenv("GITHUB_TOKEN")

    def is_available(self) -> bool:
        return bool(self.token)

    def execute(self, task_title: str, state: OnboardingState) -> IntegrationResult:
        if self.is_available():
            return IntegrationResult(
                success=True,
                status="available",
                detail=f"GitHub adapter is configured for task '{task_title}'.",
            )
        return self.dry_run(task_title, state)

    def dry_run(self, task_title: str, state: OnboardingState) -> IntegrationResult:
        return IntegrationResult(
            success=True,
            status="queued",
            detail=f"GitHub action '{task_title}' is queued for manual completion or demo mode.",
        )
