from __future__ import annotations

import json

from onboardai.config import AppConfig
from onboardai.graph import OnboardingEngine
from onboardai.models import TaskPriority, TaskStatus


def test_engine_intro_builds_personalized_plan(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root))
    state = engine.new_state()
    response = engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    assert "Matched persona" in response
    assert state.employee_profile is not None
    assert state.matched_persona is not None
    assert state.current_task_id is not None
    assert len(state.task_plan) > 10


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
