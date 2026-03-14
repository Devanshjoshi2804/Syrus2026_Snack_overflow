from __future__ import annotations

from onboardai.models import AutomationMode, OnboardingState, TaskAction, TaskStatus
from onboardai.state import get_current_task


AGENT_AUTOMATION_MODES = {AutomationMode.AGENT_TERMINAL, AutomationMode.AGENT_BROWSER}


def _available_actions(task) -> list[str]:
    if not task:
        return []
    if task.automation_mode in AGENT_AUTOMATION_MODES:
        return [TaskAction.WATCH_AGENT.value, TaskAction.SELF_COMPLETE.value, TaskAction.SKIP.value]
    return [TaskAction.SELF_COMPLETE.value, TaskAction.SKIP.value]


def _next_agent_task(state: OnboardingState):
    current_index = 0
    if state.current_task_id:
        for index, task in enumerate(state.task_plan):
            if task.task_id == state.current_task_id:
                current_index = index
                break
    for task in state.task_plan[current_index + 1:]:
        if task.status in {TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS} and task.automation_mode in AGENT_AUTOMATION_MODES:
            return task
    return None


def _health_hint(health: dict[str, str], current_task, next_agent_task) -> str | None:
    browser_ready = (health.get("browser_ready") or "").lower()
    if browser_ready == "no":
        relevant_browser_task = (
            (current_task and current_task.automation_mode == AutomationMode.AGENT_BROWSER)
            or (next_agent_task and next_agent_task.automation_mode == AutomationMode.AGENT_BROWSER)
        )
        if relevant_browser_task:
            return "Browser automation is unavailable. Run `playwright install chromium` and restart the app."
    return None


def _usable_stream_url(state: OnboardingState) -> str | None:
    stream_url = state.dashboard_state.stream_url
    if not stream_url:
        return None
    if state.sandbox_session and state.sandbox_session.backend == "mock":
        return None
    if "example.invalid" in stream_url:
        return None
    return stream_url


def _step_ordinal(state: OnboardingState, current_task) -> int | None:
    if not current_task:
        return None
    for index, task in enumerate(state.task_plan, start=1):
        if task.task_id == current_task.task_id:
            return index
    return None


def _action_labels(current_task) -> dict[str, str]:
    if not current_task:
        return {
            "explain_task": "Explain this step",
            TaskAction.WATCH_AGENT.value: "Run agent",
            TaskAction.SELF_COMPLETE.value: "Mark done",
            TaskAction.SKIP.value: "Skip",
        }
    title = current_task.title.lower()
    complete_label = "Mark done"
    if "laptop" in title:
        complete_label = "I have the laptop"
    elif "google workspace" in title:
        complete_label = "I activated it"
    elif "slack" in title:
        complete_label = "I joined Slack"
    elif "vpn" in title:
        complete_label = "VPN is set up"
    return {
        "explain_task": "Explain this step",
        TaskAction.WATCH_AGENT.value: "Run agent for me",
        TaskAction.SELF_COMPLETE.value: complete_label,
        TaskAction.SKIP.value: "Skip for now",
    }


def _upcoming_tasks(state: OnboardingState, limit: int = 4) -> list[dict]:
    items = []
    current_seen = False
    for index, task in enumerate(state.task_plan, start=1):
        if task.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}:
            continue
        if not state.current_task_id or task.task_id == state.current_task_id:
            current_seen = True
        if not current_seen:
            continue
        items.append(
            {
                "index": index,
                "taskId": task.task_id,
                "title": task.title,
                "automation": task.automation_mode.value,
                "status": task.status.value,
            }
        )
        if len(items) >= limit:
            break
    return items


def _walkthrough_for_task(current_task, next_agent_task) -> dict:
    if not current_task:
        return {
            "title": "Start by introducing yourself",
            "summary": "Tell OnboardAI your role, level, and tech stack so it can select the right onboarding path.",
            "steps": [
                "Say who you are joining as, for example: Backend Intern, Frontend Engineer, or DevOps.",
                "Mention your main tech stack, for example: Node.js, React, Python, or Kubernetes.",
                "After that, the workspace will switch from waiting mode to your first guided task.",
            ],
            "completionHint": "Example: Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
            "whyItMatters": "Without your role and stack, the app cannot pick the correct checklist or starter ticket.",
            "quickReplies": [
                "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
            ],
        }

    title = current_task.title.lower()
    if "laptop" in title:
        return {
            "title": "Confirm your company laptop kit",
            "summary": "This is only a physical handoff check. You are not expected to configure anything advanced yet.",
            "steps": [
                "Check that you received the laptop, charger, and can power the machine on.",
                "If the laptop turns on and the accessories are with you, this task is complete.",
                "You do not need the agent for this step. Just confirm it and move to account setup.",
            ],
            "completionHint": "If you already have it, click Mark done or type: i have the laptop",
            "whyItMatters": "All following setup tasks depend on having the company device in hand first.",
            "quickReplies": [
                "i have the laptop",
                "what do i do for this step",
            ],
        }
    if "google workspace" in title:
        return {
            "title": "Activate your NovaByte Google account",
            "summary": "This gives you access to Gmail, Calendar, and Drive. It is the first real account-activation step.",
            "steps": [
                "Open the NovaByte welcome email or invite and accept the Google Workspace invitation.",
                "Sign in once and verify that Gmail, Calendar, and Drive open successfully.",
                "When all three open, mark the task done and the onboarding will continue.",
            ],
            "completionHint": "If you are stuck, ask: how do I activate Google Workspace?",
            "whyItMatters": "Most company systems are tied to your Google identity.",
            "quickReplies": [
                "how do i activate google workspace",
                "mark it done",
            ],
        }
    if "slack" in title:
        return {
            "title": "Join the required Slack channels",
            "summary": "This is the first task the agent can help with if browser automation is available.",
            "steps": [
                "Open Slack and join #engineering-general, #new-joiners, and your team channel.",
                "If browser automation is ready, use Run agent and let the workspace handle it.",
                "If you do it yourself, come back and mark the task done.",
            ],
            "completionHint": "Use Run agent for automation, or type: let agent do it",
            "whyItMatters": "Slack is where onboarding updates, support questions, and engineering communication happen.",
            "quickReplies": [
                "let agent do it",
                "what do i do for this step",
            ],
        }
    quick_replies = ["what do i do for this step", "mark it done"]
    if current_task.automation_mode in AGENT_AUTOMATION_MODES:
        quick_replies.insert(0, "let agent do it")
    completion_hint = "Complete the step, then click Mark done or type: mark it done"
    if next_agent_task and current_task.automation_mode not in AGENT_AUTOMATION_MODES:
        completion_hint += f". The next agent task is {next_agent_task.task_id}."
    return {
        "title": f"Do `{current_task.task_id}` now",
        "summary": "Follow the current task, then resolve it before moving forward. The workspace keeps the next action visible.",
        "steps": [
            f"Read the current task title and category: {current_task.title}.",
            "Use the grounding notes and health hints in the workspace if you are unsure what system to open.",
            "When finished, mark the task done. If it is agent-runnable, you can use Run agent instead.",
        ],
        "completionHint": completion_hint,
        "whyItMatters": "Completing tasks in order avoids missing required access or compliance setup.",
        "quickReplies": quick_replies,
    }


def build_dashboard_props(state: OnboardingState) -> dict:
    total = len(state.task_plan)
    completed = sum(
        1 for task in state.task_plan
        if task.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}
    )
    current_task = get_current_task(state)
    next_agent_task = _next_agent_task(state)
    health = state.dashboard_state.health
    walkthrough = _walkthrough_for_task(current_task, next_agent_task)
    current_task_label = state.dashboard_state.current_task or (current_task.title if current_task else "Waiting for onboarding input")
    persona_title = state.matched_persona.persona.title if state.matched_persona else None
    employee_name = state.employee_profile.name if state.employee_profile else None
    return {
        "streamUrl": _usable_stream_url(state),
        "workspaceMode": "live" if _usable_stream_url(state) else "simulated",
        "sandboxBackend": state.sandbox_session.backend if state.sandbox_session else "unknown",
        "employeeName": employee_name,
        "personaTitle": persona_title,
        "currentTask": current_task_label,
        "currentTaskId": current_task.task_id if current_task else None,
        "currentTaskIndex": _step_ordinal(state, current_task),
        "currentTaskCategory": current_task.category if current_task else None,
        "currentTaskAutomation": current_task.automation_mode.value if current_task else None,
        "currentTaskPriority": current_task.priority.value if current_task else None,
        "currentTaskStatus": current_task.status.value if current_task else None,
        "currentTaskEvidence": current_task.evidence_required if current_task else [],
        "currentTaskSources": [f"{hit.chunk.source_path.split('/')[-1]} -> {hit.chunk.title}" for hit in state.knowledge_hits[:2]],
        "availableActions": _available_actions(current_task),
        "actionLabels": _action_labels(current_task),
        "upcomingTasks": _upcoming_tasks(state),
        "nextAgentTask": (
            {
                "taskId": next_agent_task.task_id,
                "title": next_agent_task.title,
                "automation": next_agent_task.automation_mode.value,
            }
            if next_agent_task
            else None
        ),
        "latestStatus": state.dashboard_state.latest_status,
        "latestScreenshotArtifact": state.dashboard_state.latest_screenshot_artifact,
        "health": health,
        "healthHint": _health_hint(health, current_task, next_agent_task),
        "totalTasks": total,
        "completedTasks": completed,
        "remainingTasks": max(total - completed, 0),
        "walkthrough": walkthrough,
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
