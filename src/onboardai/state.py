from __future__ import annotations

from datetime import datetime

from onboardai.models import (
    ChecklistTask,
    DashboardItem,
    OnboardingState,
    TaskStatus,
    VerificationEntry,
)


def get_current_task(state: OnboardingState) -> ChecklistTask | None:
    if not state.current_task_id:
        return None
    for task in state.task_plan:
        if task.task_id == state.current_task_id:
            return task
    return None


def choose_next_task(state: OnboardingState) -> ChecklistTask | None:
    for task in state.task_plan:
        if task.status in {TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS}:
            state.current_task_id = task.task_id
            state.dashboard_state.current_task = task.title
            return task
    state.current_task_id = None
    state.dashboard_state.current_task = None
    return None


def set_task_status(state: OnboardingState, task_id: str, status: TaskStatus) -> ChecklistTask | None:
    for task in state.task_plan:
        if task.task_id == task_id:
            task.status = status
            return task
    return None


def record_verification(
    state: OnboardingState,
    entry: VerificationEntry,
) -> None:
    state.verification_log.append(entry)
    item = DashboardItem(
        task_id=entry.task_id,
        title=entry.task_title,
        status=entry.status,
        detail=entry.details,
        timestamp=entry.timestamp.isoformat(timespec="seconds"),
    )
    state.dashboard_state.items = [
        dashboard_item
        for dashboard_item in state.dashboard_state.items
        if dashboard_item.task_id != entry.task_id
    ]
    state.dashboard_state.items.append(item)
    state.dashboard_state.latest_status = f"{entry.task_title}: {entry.status.value}"
    state.dashboard_state.current_task = entry.task_title
    state.artifact_paths.extend(entry.artifacts)
    for artifact in reversed(entry.artifacts):
        if artifact.lower().endswith((".png", ".jpg", ".jpeg")):
            state.dashboard_state.latest_screenshot_artifact = artifact
            break


def mark_completed(
    state: OnboardingState,
    task_id: str,
    method: str,
    details: str,
    verified_values: dict[str, str] | None = None,
    artifacts: list[str] | None = None,
) -> None:
    task = set_task_status(state, task_id, TaskStatus.COMPLETED)
    if not task:
        return
    record_verification(
        state,
        VerificationEntry(
            task_id=task.task_id,
            task_title=task.title,
            status=TaskStatus.COMPLETED,
            method=method,
            details=details,
            verified_values=verified_values or {},
            artifacts=artifacts or [],
            timestamp=datetime.utcnow(),
        ),
    )


def mark_skipped(state: OnboardingState, task_id: str, reason: str) -> None:
    task = set_task_status(state, task_id, TaskStatus.SKIPPED)
    if not task:
        return
    record_verification(
        state,
        VerificationEntry(
            task_id=task.task_id,
            task_title=task.title,
            status=TaskStatus.SKIPPED,
            method="skip",
            details=reason,
        ),
    )
