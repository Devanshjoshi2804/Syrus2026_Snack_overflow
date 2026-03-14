from __future__ import annotations

from onboardai.models import OnboardingState, TaskStatus


def build_dashboard_props(state: OnboardingState) -> dict:
    total = len(state.task_plan)
    completed = sum(
        1 for task in state.task_plan
        if task.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}
    )
    return {
        "streamUrl": state.dashboard_state.stream_url,
        "currentTask": state.dashboard_state.current_task,
        "latestStatus": state.dashboard_state.latest_status,
        "latestScreenshotArtifact": state.dashboard_state.latest_screenshot_artifact,
        "health": state.dashboard_state.health,
        "totalTasks": total,
        "completedTasks": completed,
        "items": [
            {
                "taskId": item.task_id,
                "title": item.title,
                "status": item.status.value,
                "detail": item.detail,
                "timestamp": item.timestamp,
            }
            for item in state.dashboard_state.items
        ],
    }

