from __future__ import annotations

from onboardai.models import ChecklistTask, OnboardingState
from onboardai.state import mark_completed


def test_mark_completed_updates_latest_screenshot_artifact():
    state = OnboardingState(
        task_plan=[
            ChecklistTask(
                task_id="C-07",
                title="Accept GitHub organization invite",
                category="Access",
                source_section="Common Checklist",
            )
        ]
    )
    mark_completed(
        state,
        "C-07",
        "agent",
        "Opened GitHub page",
        artifacts=["/tmp/github-page.png"],
    )
    assert state.dashboard_state.latest_screenshot_artifact == "/tmp/github-page.png"
