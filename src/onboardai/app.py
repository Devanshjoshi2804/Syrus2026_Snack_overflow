from __future__ import annotations

import json
from onboardai.graph import OnboardingEngine
from onboardai.models import TaskAction, TaskStatus
from onboardai.state import get_current_task
from onboardai.ui.dashboard import build_dashboard_props


try:
    import chainlit as cl
except ImportError:  # pragma: no cover - optional runtime dependency
    cl = None


ENGINE = OnboardingEngine()


def _chainlit_task_status(task, current_task_id, cl_module):
    if task.status == TaskStatus.BLOCKED:
        return cl_module.TaskStatus.FAILED
    if task.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}:
        return cl_module.TaskStatus.DONE
    if task.task_id == current_task_id or task.status == TaskStatus.IN_PROGRESS:
        return cl_module.TaskStatus.RUNNING
    return cl_module.TaskStatus.READY


def _task_list_status_text(state) -> str:
    if not state.employee_profile:
        return "Waiting for your introduction"
    total = len(state.task_plan)
    resolved = sum(
        1 for task in state.task_plan if task.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}
    )
    current_task = get_current_task(state)
    if current_task:
        current_index = next(
            (index for index, task in enumerate(state.task_plan, start=1) if task.task_id == current_task.task_id),
            1,
        )
        return f"Step {current_index}/{total} · {resolved} done"
    return f"Complete · {resolved}/{total} done"


def _visible_tasks(state, window: int = 6):
    if not state.task_plan:
        return []
    current_index = 0
    if state.current_task_id:
        for index, task in enumerate(state.task_plan):
            if task.task_id == state.current_task_id:
                current_index = index
                break
    start = max(0, current_index - 1)
    end = min(len(state.task_plan), start + window)
    return state.task_plan[start:end]


def _workspace_actions(state):
    if cl is None:
        return []
    task = get_current_task(state)
    if not task:
        return []
    props = build_dashboard_props(state)
    labels = props.get("actionLabels", {})
    actions = [
        cl.Action(name="explain_task", label=labels.get("explain_task", "Explain this step"), payload={"action": "explain_task"}),
    ]
    available = ENGINE.available_actions(state)
    if TaskAction.WATCH_AGENT in available:
        actions.append(
            cl.Action(name="watch_agent", label=labels.get("watch_agent", "Run agent for me"), payload={"action": "watch_agent"})
        )
    if TaskAction.SELF_COMPLETE in available:
        actions.append(
            cl.Action(name="self_complete", label=labels.get("self_complete", "Mark done"), payload={"action": "self_complete"})
        )
    actions.append(cl.Action(name="skip_task", label=labels.get("skip", "Skip for now"), payload={"action": "skip"}))
    return actions


def _workspace_content(state, note: str | None = None) -> str:
    props = build_dashboard_props(state)
    walkthrough = props.get("walkthrough", {})
    lines: list[str] = ["## Guided Workspace"]
    if note:
        lines.append(note)
    if not props.get("currentTaskId"):
        lines.append("Tell me your role, level, and tech stack to start the onboarding plan.")
        lines.append("Example: `Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.`")
        return "\n\n".join(lines)

    lines.append(
        f"**Step {props.get('currentTaskIndex')}/{props.get('totalTasks')}**  \n"
        f"`{props.get('currentTaskId')}` {props.get('currentTask')}"
    )
    if walkthrough.get("summary"):
        lines.append(walkthrough["summary"])
    steps = walkthrough.get("steps") or []
    if steps:
        lines.append("**What to do now**")
        lines.extend(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    if walkthrough.get("completionHint"):
        lines.append(f"**Fastest way to finish:** {walkthrough['completionHint']}")
    if walkthrough.get("whyItMatters"):
        lines.append(f"**Why this matters:** {walkthrough['whyItMatters']}")

    upcoming = props.get("upcomingTasks") or []
    if len(upcoming) > 1:
        lines.append("**Up next**")
        lines.extend(
            f"- Step {task['index']}: `{task['taskId']}` {task['title']}"
            for task in upcoming[1:4]
        )

    next_agent = props.get("nextAgentTask")
    if next_agent and props.get("currentTaskAutomation") not in {"agent_browser", "agent_terminal"}:
        lines.append(
            f"**Agent help starts at:** `{next_agent['taskId']}` {next_agent['title']}"
        )

    items = props.get("items") or []
    if items:
        latest = items[-1]
        lines.append(
            f"**Latest proof:** `{latest['taskId']}` {latest['title']} -> {latest['status']}"
        )

    return "\n\n".join(lines)


if cl is not None:  # pragma: no cover - exercised in Chainlit runtime
    @cl.on_chat_start
    async def on_chat_start():
        state = ENGINE.new_state()
        cl.user_session.set("state", state)

        intro_message = await cl.Message(
            content=(
                "## OnboardAI\n\n"
                "Introduce yourself with your **role**, **level**, and **tech stack**.\n\n"
                "**Example:** *Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.*\n\n"
                "You do not need to guess commands. I will guide you one step at a time.\n\n"
                "Use the **workspace card** for the current step. Open the sidebar anytime if you want the full checklist."
            ),
            author="OnboardAI",
        ).send()
        cl.user_session.set("workspace_message", intro_message)

        task_list = cl.TaskList(display="side", status=_task_list_status_text(state))
        await task_list.send()
        cl.user_session.set("task_list", task_list)

    async def _sync_task_list(state):
        task_list = cl.user_session.get("task_list")
        if not task_list:
            task_list = cl.TaskList(display="side")
            await task_list.send()
            cl.user_session.set("task_list", task_list)
        task_list.status = _task_list_status_text(state)
        task_list.tasks = [
            cl.Task(
                title=(
                    f"{task.task_id} {task.title}"
                    if task.status != TaskStatus.SKIPPED
                    else f"{task.task_id} {task.title} (skipped)"
                ),
                status=_chainlit_task_status(task, state.current_task_id, cl),
            )
            for task in _visible_tasks(state)
        ]
        await task_list.update()

    async def _sync_workspace_message(state, note: str | None = None):
        previous_message = cl.user_session.get("workspace_message")
        if previous_message:
            previous_message.actions = []
            await previous_message.update()
        workspace_message = await cl.Message(
            content=_workspace_content(state, note),
            actions=_workspace_actions(state),
            author="OnboardAI",
        ).send()
        cl.user_session.set("workspace_message", workspace_message)

    async def _sync_workspace(state, note: str | None = None):
        await _sync_task_list(state)
        await _sync_workspace_message(state, note)

    @cl.on_message
    async def on_message(message: cl.Message):
        state = cl.user_session.get("state")

        async with cl.Step(name="Processing", type="llm") as step:
            step.input = message.content
            response = ENGINE.handle_message(state, message.content)
            step.output = response

        cl.user_session.set("state", state)
        await _sync_workspace(state, response)

    @cl.action_callback("watch_agent")
    async def on_watch_agent(action: cl.Action):
        state = cl.user_session.get("state")

        async with cl.Step(name="Agent Executing Task", type="tool") as step:
            step.input = f"Executing task: {state.current_task_id}"
            response = ENGINE.task_action_router_node(state, TaskAction.WATCH_AGENT)
            step.output = response

        cl.user_session.set("state", state)
        await _sync_workspace(state, response)

    @cl.action_callback("self_complete")
    async def on_self_complete(action: cl.Action):
        state = cl.user_session.get("state")
        response = ENGINE.task_action_router_node(state, TaskAction.SELF_COMPLETE)
        cl.user_session.set("state", state)
        await _sync_workspace(state, response)

    @cl.action_callback("skip_task")
    async def on_skip_task(action: cl.Action):
        state = cl.user_session.get("state")
        response = ENGINE.task_action_router_node(state, TaskAction.SKIP, reason="Skipped from UI")
        cl.user_session.set("state", state)
        await _sync_workspace(state, response)

    @cl.action_callback("explain_task")
    async def on_explain_task(action: cl.Action):
        state = cl.user_session.get("state")
        response = ENGINE.task_help_node(state, "what do i do for this step")
        cl.user_session.set("state", state)
        await _sync_workspace(state, response)


def cli_demo(message: str) -> str:
    state = ENGINE.new_state()
    response = ENGINE.handle_message(state, message)
    return json.dumps(
        {
            "response": response,
            "dashboard": build_dashboard_props(state),
            "tasks": [task.model_dump(mode="json") for task in state.task_plan[:10]],
        },
        indent=2,
    )


if __name__ == "__main__":  # pragma: no cover - manual fallback
    print(cli_demo("Hi, I'm Riya. I've joined as a Backend Intern working on Node.js."))
