from __future__ import annotations

from onboardai.config import AppConfig
from onboardai.content.parser import parse_setup_guides
from onboardai.graph import OnboardingEngine


def test_parse_setup_guides_normalizes_cd_sequences(dataset_root):
    guides = parse_setup_guides(dataset_root / "setup_guides.md")
    section = guides["backend-intern-node-js-local-setup"]
    clone_step = next(step for step in section.steps if "clone starter repository" in step.step_title.lower())
    assert clone_step.commands[0].startswith(
        "git clone https://github.com/NovaByte-Technologies/connector-runtime-demo.git"
    )
    assert clone_step.commands[1] == "cd connector-runtime-demo && pnpm install"


def test_engine_uses_setup_guide_for_python_tasks(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root))
    state = engine.new_state()
    engine.handle_message(
        state,
        "Hi, I'm Vikram. I've joined as a Junior Backend Engineer working on Python and FastAPI.",
    )
    python_task = next(task for task in state.task_plan if task.task_id == "JBP-01")
    poetry_task = next(task for task in state.task_plan if task.task_id == "JBP-02")

    python_instruction = engine._build_instruction(python_task, state)
    poetry_instruction = engine._build_instruction(poetry_task, state)

    assert python_instruction.command_plan == ["python3.11 --version"]
    assert "python_version" in python_instruction.expected_patterns
    assert any("install.python-poetry.org" in command for command in poetry_instruction.command_plan)
    assert "poetry_version" in poetry_instruction.expected_patterns


def test_engine_builds_frontend_and_full_stack_clone_instructions(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root))

    frontend_state = engine.new_state()
    engine.handle_message(
        frontend_state,
        "Hi, I'm Ananya. I've joined as a Junior Frontend Engineer working on React and TypeScript.",
    )
    frontend_clone_task = next(task for task in frontend_state.task_plan if task.task_id == "JFR-04")
    frontend_instruction = engine._build_instruction(frontend_clone_task, frontend_state)
    assert frontend_instruction.command_plan[0].startswith(
        "git clone https://github.com/NovaByte-Technologies/flowengine-web-demo"
    )

    full_stack_state = engine.new_state()
    engine.handle_message(
        full_stack_state,
        "Hi, I'm Arjun. I've joined as a Junior Full-Stack Engineer working on Node.js and React.",
    )
    full_stack_clone_task = next(task for task in full_stack_state.task_plan if task.task_id == "JFS-05")
    full_stack_instruction = engine._build_instruction(full_stack_clone_task, full_stack_state)
    joined = "\n".join(full_stack_instruction.command_plan)
    assert "connector-runtime-demo" in joined
    assert "flowengine-web-demo" in joined
    full_stack_ticket_task = next(task for task in full_stack_state.task_plan if task.task_id == "JFS-17")
    full_stack_ticket_instruction = engine._build_instruction(full_stack_ticket_task, full_stack_state)
    assert full_stack_ticket_instruction.url
    assert "FLOW-FS-001" in full_stack_ticket_instruction.url
