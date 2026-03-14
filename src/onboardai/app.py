from __future__ import annotations

import json

from onboardai.graph import OnboardingEngine
from onboardai.models import TaskAction
from onboardai.ui.dashboard import build_dashboard_props


try:
    import chainlit as cl
except ImportError:  # pragma: no cover - optional runtime dependency
    cl = None


ENGINE = OnboardingEngine()


def _task_markdown(state) -> str:
    lines = []
    for task in state.task_plan[:20]:
        lines.append(f"- [{task.status.value}] {task.task_id} {task.title}")
    return "\n".join(lines) if lines else "- No tasks prepared yet."


if cl is not None:  # pragma: no cover - exercised in Chainlit runtime
    @cl.on_chat_start
    async def on_chat_start():
        state = ENGINE.new_state()
        cl.user_session.set("state", state)
        await cl.Message(
            content=(
                "OnboardAI is ready. Introduce yourself with your role, level, and stack.\n"
                "Example: Hi, I'm Riya. I've joined as a Backend Intern working on Node.js."
            )
        ).send()

    async def _render_task_panel(state):
        await cl.Message(content=f"### Checklist\n{_task_markdown(state)}").send()
        await cl.CustomElement(
            name="OnboardingDashboard",
            props=build_dashboard_props(state),
            display="side",
        ).send()

    async def _render_actions():
        actions = [
            cl.Action(name="watch_agent", label="Watch agent do this", payload={"action": "watch_agent"}),
            cl.Action(name="self_complete", label="I did it myself", payload={"action": "self_complete"}),
            cl.Action(name="skip_task", label="Skip", payload={"action": "skip"}),
        ]
        await cl.Message(content="Choose how to handle the current task.", actions=actions).send()

    @cl.on_message
    async def on_message(message: cl.Message):
        state = cl.user_session.get("state")
        response = ENGINE.handle_message(state, message.content)
        cl.user_session.set("state", state)
        await cl.Message(content=response).send()
        await _render_task_panel(state)
        await _render_actions()

    @cl.action_callback("watch_agent")
    async def on_watch_agent(action: cl.Action):
        state = cl.user_session.get("state")
        response = ENGINE.task_action_router_node(state, TaskAction.WATCH_AGENT)
        cl.user_session.set("state", state)
        await cl.Message(content=response).send()
        await _render_task_panel(state)
        await _render_actions()

    @cl.action_callback("self_complete")
    async def on_self_complete(action: cl.Action):
        state = cl.user_session.get("state")
        response = ENGINE.task_action_router_node(state, TaskAction.SELF_COMPLETE)
        cl.user_session.set("state", state)
        await cl.Message(content=response).send()
        await _render_task_panel(state)
        await _render_actions()

    @cl.action_callback("skip_task")
    async def on_skip_task(action: cl.Action):
        state = cl.user_session.get("state")
        response = ENGINE.task_action_router_node(state, TaskAction.SKIP, reason="Skipped from UI")
        cl.user_session.set("state", state)
        await cl.Message(content=response).send()
        await _render_task_panel(state)
        await _render_actions()


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
