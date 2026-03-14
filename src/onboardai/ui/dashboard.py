from __future__ import annotations

from onboardai.models import OnboardingState


def build_dashboard_props(state: OnboardingState) -> dict:
    return {
        "streamUrl": state.dashboard_state.stream_url,
        "currentTask": state.dashboard_state.current_task,
        "latestStatus": state.dashboard_state.latest_status,
        "latestScreenshotArtifact": state.dashboard_state.latest_screenshot_artifact,
        "health": state.dashboard_state.health,
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
