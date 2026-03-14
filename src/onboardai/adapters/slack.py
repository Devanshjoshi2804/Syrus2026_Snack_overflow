from __future__ import annotations

import os

from onboardai.models import IntegrationResult, OnboardingState


class SlackAdapter:
    def __init__(self) -> None:
        self.bot_token = os.getenv("SLACK_BOT_TOKEN")

    def is_available(self) -> bool:
        return bool(self.bot_token)

    def execute(self, task_title: str, state: OnboardingState) -> IntegrationResult:
        if self.is_available():
            return IntegrationResult(
                success=True,
                status="available",
                detail=f"Slack adapter is configured for task '{task_title}'.",
            )
        return self.dry_run(task_title, state)

    def dry_run(self, task_title: str, state: OnboardingState) -> IntegrationResult:
        return IntegrationResult(
            success=True,
            status="queued",
            detail=f"Slack action '{task_title}' is queued for manual completion or demo mode.",
        )
