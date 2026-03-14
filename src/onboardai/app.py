from __future__ import annotations

import json
from pathlib import Path

from onboardai.graph import OnboardingEngine
from onboardai.models import TaskAction, TaskStatus
from onboardai.state import get_current_task
from onboardai.ui.dashboard import build_dashboard_props


try:
    import chainlit as cl
except ImportError:  # pragma: no cover - optional runtime dependency
    cl = None


ENGINE = OnboardingEngine()


def _ensure_chainlit_files_dir() -> None:
    Path(".files").mkdir(exist_ok=True)


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


if cl is not None:  # pragma: no cover - exercised in Chainlit runtime
    @cl.on_chat_start
    async def on_chat_start():
        _ensure_chainlit_files_dir()
        state = ENGINE.new_state()
        cl.user_session.set("state", state)

        dashboard_element = cl.CustomElement(
            name="OnboardingDashboard",
            props=build_dashboard_props(state),
            display="inline",
            size="large",
        )
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
        await dashboard_element.send(for_id=intro_message.id)
        cl.user_session.set("workspace_message", intro_message)
        cl.user_session.set("dashboard_element", dashboard_element)

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

    async def _sync_dashboard(state):
        _ensure_chainlit_files_dir()
        state.dashboard_state.health = ENGINE.runtime_health()
        dashboard_element = cl.user_session.get("dashboard_element")
        if not dashboard_element:
            dashboard_element = cl.CustomElement(
                name="OnboardingDashboard",
                props=build_dashboard_props(state),
                display="inline",
                size="large",
            )
            workspace_message = cl.user_session.get("workspace_message")
            if not workspace_message:
                workspace_message = await cl.Message(content="## Workspace", author="OnboardAI").send()
                cl.user_session.set("workspace_message", workspace_message)
            await dashboard_element.send(for_id=workspace_message.id)
            cl.user_session.set("dashboard_element", dashboard_element)
            return
        next_props = build_dashboard_props(state)
        dashboard_element.props.clear()
        dashboard_element.props.update(next_props)
        await dashboard_element.update()

    async def _sync_workspace(state):
        await _sync_dashboard(state)
        await _sync_task_list(state)

    @cl.on_message
    async def on_message(message: cl.Message):
        state = cl.user_session.get("state")

        async with cl.Step(name="Processing", type="llm") as step:
            step.input = message.content
            response = ENGINE.handle_message(state, message.content)
            step.output = response

        cl.user_session.set("state", state)
        await cl.Message(content=response).send()
        await _sync_workspace(state)

    @cl.action_callback("watch_agent")
    async def on_watch_agent(action: cl.Action):
        state = cl.user_session.get("state")

        async with cl.Step(name="Agent Executing Task", type="tool") as step:
            step.input = f"Executing task: {state.current_task_id}"
            response = ENGINE.task_action_router_node(state, TaskAction.WATCH_AGENT)
            step.output = response

        cl.user_session.set("state", state)
        await cl.Message(content=response).send()
        await _sync_workspace(state)

    @cl.action_callback("self_complete")
    async def on_self_complete(action: cl.Action):
        state = cl.user_session.get("state")
        response = ENGINE.task_action_router_node(state, TaskAction.SELF_COMPLETE)
        cl.user_session.set("state", state)
        await cl.Message(content=response).send()
        await _sync_workspace(state)

    @cl.action_callback("skip_task")
    async def on_skip_task(action: cl.Action):
        state = cl.user_session.get("state")
        response = ENGINE.task_action_router_node(state, TaskAction.SKIP, reason="Skipped from UI")
        cl.user_session.set("state", state)
        await cl.Message(content=response).send()
        await _sync_workspace(state)

    @cl.action_callback("explain_task")
    async def on_explain_task(action: cl.Action):
        state = cl.user_session.get("state")
        response = ENGINE.task_help_node(state, "what do i do for this step")
        cl.user_session.set("state", state)
        await cl.Message(content=response).send()
        await _sync_workspace(state)


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
