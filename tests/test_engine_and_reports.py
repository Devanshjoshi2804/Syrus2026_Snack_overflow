from __future__ import annotations

import json

from onboardai.config import AppConfig
from onboardai.graph import OnboardingEngine
from onboardai.models import TaskPriority, TaskStatus
from onboardai.ui.dashboard import build_dashboard_props


def test_engine_intro_builds_personalized_plan(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root))
    state = engine.new_state()
    response = engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    assert "Welcome Riya" in response
    assert "Step 1: `C-01`" in response
    assert state.employee_profile is not None
    assert state.matched_persona is not None
    assert state.current_task_id is not None
    assert len(state.task_plan) > 10


def test_dashboard_props_handle_empty_state(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root))
    state = engine.new_state()
    props = build_dashboard_props(state)
    assert props["currentTaskId"] is None
    assert props["currentTaskEvidence"] == []
    assert props["upcomingTasks"] == []


def test_completion_report_generator_writes_artifacts(project_root, tmp_path):
    config = AppConfig(project_root=project_root, outputs_dir=tmp_path)
    engine = OnboardingEngine(config)
    state = engine.new_state()
    engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    for task in state.task_plan:
        if task.priority == TaskPriority.REQUIRED:
            task.status = TaskStatus.COMPLETED
    response = engine.email_generation_node(state)
    assert "Generated HR completion artifacts" in response
    html_files = list(tmp_path.glob("*.html"))
    json_files = list(tmp_path.glob("*.json"))
    assert html_files
    assert json_files
    payload = json.loads(json_files[0].read_text(encoding="utf-8"))
    assert payload["employee"] == "Riya"


def test_engine_uses_dataset_starter_ticket_for_repo_task(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root))
    state = engine.new_state()
    engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    repo_task = next(task for task in state.task_plan if task.task_id == "BI-05")
    instruction = engine._build_instruction(repo_task, state)
    assert "connector-runtime-demo" in "\n".join(instruction.command_plan)
    first_task = next(task for task in state.task_plan if task.task_id == "BI-18")
    starter_instruction = engine._build_instruction(first_task, state)
    assert starter_instruction.url and "FLOW-INTERN-001" in starter_instruction.url


def test_manual_task_only_offers_self_complete_and_skip(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root))
    state = engine.new_state()
    engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    response = engine.task_presentation_node(state)
    assert "Watch agent do this" not in response
    assert "I did it myself / Skip" in response
    assert "manual step" in response


def test_typed_manual_watch_returns_clear_explanation(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root))
    state = engine.new_state()
    engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    response = engine.handle_message(state, "Watch agent do this")
    assert "agent cannot execute it directly" in response
    assert state.current_task_id == "C-01"
    current_task = next(task for task in state.task_plan if task.task_id == "C-01")
    assert current_task.status == TaskStatus.NOT_STARTED


def test_typed_let_agent_do_it_is_understood(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root))
    state = engine.new_state()
    engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    response = engine.handle_message(state, "let agent do it")
    assert "agent cannot execute it directly" in response


def test_typed_self_complete_marks_current_task_done(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root))
    state = engine.new_state()
    engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    response = engine.handle_message(state, "I did it myself")
    first_task = next(task for task in state.task_plan if task.task_id == "C-01")
    assert first_task.status == TaskStatus.COMPLETED
    assert "Next step: `C-02`" in response


def test_typo_completion_confirmation_marks_laptop_step_done(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root))
    state = engine.new_state()
    engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    response = engine.handle_message(state, "i have recived company laptop")
    first_task = next(task for task in state.task_plan if task.task_id == "C-01")
    assert first_task.status == TaskStatus.COMPLETED
    assert "Next step: `C-02`" in response
