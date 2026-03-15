from __future__ import annotations

import json
from onboardai.graph import OnboardingEngine
from onboardai.models import TaskAction, TaskPhase, TaskStatus
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
        phase_labels = {
            TaskPhase.GET_ACCESS: "Get Access",
            TaskPhase.GET_CODING: "Get Coding",
            TaskPhase.LEARN_SYSTEM: "Learn the System",
            TaskPhase.ADMIN_COMPLIANCE: "Finish Admin & Compliance",
        }
        phase_label = phase_labels.get(current_task.display_phase, "Guided onboarding")
        hidden = _hidden_task_count(state)
        suffix = f" · {hidden} hidden" if hidden else ""
        return f"{phase_label} · Step {current_index}/{total} · {resolved} done{suffix}"
    return f"Complete · {resolved}/{total} done"


def _visible_tasks(state, window: int = 8):
    if not state.task_plan:
        return []
    if state.show_full_checklist:
        return state.task_plan
    current_index = 0
    if state.current_task_id:
        for index, task in enumerate(state.task_plan):
            if task.task_id == state.current_task_id:
                current_index = index
                break
    start = max(0, current_index - 1)
    end = min(len(state.task_plan), start + window)
    return state.task_plan[start:end]


def _compact_task_title(task, max_len: int = 54) -> str:
    title = (
        f"{task.task_id} {task.title}"
        if task.status != TaskStatus.SKIPPED
        else f"{task.task_id} {task.title} (skipped)"
    )
    if len(title) <= max_len:
        return title
    return title[: max_len - 1].rstrip() + "…"


def _hidden_task_count(state) -> int:
    if state.show_full_checklist:
        return 0
    visible = _visible_tasks(state)
    return max(len(state.task_plan) - len(visible), 0)


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
    toggle_label = "Hide full checklist" if state.show_full_checklist else labels.get("show_full_checklist", "Show full checklist")
    actions.append(cl.Action(name="toggle_full_checklist", label=toggle_label, payload={"action": "toggle_full_checklist"}))
    return actions


def _workspace_element(state, note: str | None = None):
    if cl is None or not hasattr(cl, "CustomElement"):
        return None
    props = build_dashboard_props(state)
    if note:
        props["note"] = note
    return cl.CustomElement(
        name="OnboardingDashboard",
        props=props,
        display="inline",
    )


def _workspace_content(state, note: str | None = None) -> str:
    props = build_dashboard_props(state)
    guided_step = props.get("guidedStep", {})
    phase_counts = props.get("phaseCounts", {})
    lines: list[str] = []
    if props.get("workspaceMode") == "local_machine":
        lines.append(_machine_content(state))
    lines.append("## Guided Workspace")
    if note:
        lines.append(note)
    if not props.get("currentTaskId"):
        lines.append("Tell me your role, level, and tech stack to start the onboarding plan.")
        lines.append(guided_step.get("fastest_path") or "Example: `Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.`")
        return "\n\n".join(lines)

    lines.append(
        f"**Step {props.get('currentTaskIndex')}/{props.get('totalTasks')}**  \n"
        f"`{props.get('currentTaskId')}` {props.get('currentTask')}"
    )
    if props.get("currentTaskPhase"):
        lines.append(f"**Current phase:** {props.get('currentTaskPhase').replace('_', ' ').title()}")
    if guided_step.get("headline"):
        lines.append(f"**{guided_step['headline']}**")
    if guided_step.get("summary"):
        lines.append(guided_step["summary"])
    steps = guided_step.get("what_to_do_now") or []
    if steps:
        lines.append("**What to do now**")
        lines.extend(f"{index}. {step}" for index, step in enumerate(steps, start=1))
    if guided_step.get("fastest_path"):
        lines.append(f"**Fastest way to finish:** {guided_step['fastest_path']}")
    if guided_step.get("why_it_matters"):
        lines.append(f"**Why this matters:** {guided_step['why_it_matters']}")
    if guided_step.get("source_citations"):
        lines.append("**Grounded sources**")
        lines.extend(f"- {citation}" for citation in guided_step["source_citations"])
    if props.get("stepTargets"):
        lines.append("**Live targets for this step**")
        lines.extend(f"- {target}" for target in props["stepTargets"])

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

    if props.get("latestProof"):
        lines.append(f"**Latest proof:** {props['latestProof']}")
    if props.get("latestArtifacts"):
        lines.append("**Latest artifacts**")
        lines.extend(f"- {artifact}" for artifact in props["latestArtifacts"])
    if props.get("latestTranscript") and props.get("workspaceMode") != "local_machine":
        lines.append("**Agent execution log**")
        lines.append("```bash")
        lines.append(props["latestTranscript"])
        lines.append("```")
    live_targets = props.get("liveTargets") or {}
    if live_targets.get("starterTicketId") and props.get("currentTaskAutomation") in {"agent_browser", "agent_terminal"}:
        lines.append(
            f"**Current engineering target:** `{live_targets['starterTicketId']}`"
            + (
                f" in `{live_targets.get('jiraProjectKey')}`"
                if live_targets.get("jiraProjectKey")
                else ""
            )
        )
    milestone = props.get("milestoneProgress") or {}
    if milestone:
        lines.append(
            f"**Engineering milestone:** {milestone.get('completed', 0)}/{milestone.get('total', 0)} checkpoints complete"
        )
    if props.get("healthHint") and props.get("workspaceMode") != "local_machine":
        lines.append(f"**Automation hint:** {props['healthHint']}")
    if phase_counts:
        compact_counts = " · ".join(
            f"{phase.replace('_', ' ').title()}: {values['resolved']}/{values['total']}"
            for phase, values in phase_counts.items()
            if values["total"]
        )
        lines.append(f"**Phase progress:** {compact_counts}")

    return "\n\n".join(lines)


def _machine_content(state, note: str | None = None) -> str:
    props = build_dashboard_props(state)
    machine = props.get("machinePanel", {})
    lines: list[str] = ["## Local Machine"]
    if note:
        lines.append(note)
    if props.get("workspaceMode") != "local_machine":
        lines.append("A local workbench is not enabled for this session.")
        return "\n\n".join(lines)

    lines.append(
        "This agent runs terminal steps in an isolated local workbench on your Mac. "
        "Browser steps use Playwright when available, or open the target in your local browser."
    )
    lines.append(
        f"**Status:** {state.dashboard_state.latest_status or 'Ready for the first agent step'}  \n"
        f"**Backend:** `{machine.get('backend', 'local')}` · "
        f"**Browser:** `{machine.get('browserMode', 'system-browser')}` · "
        f"**Session:** `{machine.get('sessionId', 'none')}`"
    )
    if machine.get("workDir"):
        lines.append(f"**Work directory:** `{machine['workDir']}`")
    if machine.get("homeDir"):
        lines.append(f"**Isolated HOME:** `{machine['homeDir']}`")
    if machine.get("files"):
        lines.append("**Workbench files**")
        lines.extend(f"- `{entry}`" for entry in machine["files"])
    if machine.get("lastUrl"):
        lines.append(f"**Last opened URL:** {machine['lastUrl']}")
    if machine.get("lastArtifacts"):
        lines.append("**Latest browser artifacts**")
        lines.extend(f"- `{artifact}`" for artifact in machine["lastArtifacts"])
    last_command = machine.get("lastCommand") or "Waiting for the first Run agent for me action."
    lines.append(f"**Last command:** `{last_command}`")
    transcript = (
        machine.get("lastTranscript")
        or machine.get("lastOutput")
        or props.get("latestTranscript")
        or "# Waiting for the first agent-run step..."
    )
    lines.append("**Terminal / browser log**")
    lines.append("```bash")
    lines.append(transcript)
    lines.append("```")
    if props.get("healthHint"):
        lines.append(f"**Automation hint:** {props['healthHint']}")
    return "\n\n".join(lines)


if cl is not None:  # pragma: no cover - exercised in Chainlit runtime
    @cl.on_chat_start
    async def on_chat_start():
        state = ENGINE.new_state()
        cl.user_session.set("state", state)
        await cl.Message(
            content=(
                "## OnboardAI\n\n"
                "Introduce yourself with your **role**, **level**, and **tech stack**.\n\n"
                "**Example:** *Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.*\n\n"
                "You do not need to guess commands. I will guide you one step at a time.\n\n"
                "The **Local Machine** card runs terminal and browser steps for you.\n\n"
                "The **Guided Workspace** card keeps one active step visible at a time.\n\n"
                "Use the sidebar for progress. Use the workspace for action."
            ),
            author="OnboardAI",
        ).send()

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
        visible_tasks = _visible_tasks(state)
        tasks = [
            cl.Task(
                title=_compact_task_title(task),
                status=_chainlit_task_status(task, state.current_task_id, cl),
            )
            for task in visible_tasks
        ]
        hidden = max(len(state.task_plan) - len(visible_tasks), 0)
        if hidden:
            tasks.append(
                cl.Task(
                    title=f"... {hidden} more tasks hidden — use Show full checklist",
                    status=cl.TaskStatus.READY,
                )
            )
        task_list.tasks = tasks
        await task_list.update()

    async def _sync_workspace_message(state, note: str | None = None):
        await cl.Message(
            content=_workspace_content(state, note),
            actions=_workspace_actions(state),
            author="OnboardAI",
        ).send()

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
        task = get_current_task(state)
        if task:
            state.dashboard_state.latest_status = f"Running {task.task_id} on the local machine"
            await _sync_workspace(
                state,
                f"Executing `{task.task_id}` {task.title} on the local machine workbench...",
            )

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

    @cl.action_callback("toggle_full_checklist")
    async def on_toggle_full_checklist(action: cl.Action):
        state = cl.user_session.get("state")
        state.show_full_checklist = not state.show_full_checklist
        response = (
            "Showing the full checklist in the sidebar."
            if state.show_full_checklist
            else "Switched the sidebar back to the compact guided checklist."
        )
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
