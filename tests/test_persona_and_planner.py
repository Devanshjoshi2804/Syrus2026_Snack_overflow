from __future__ import annotations

from onboardai.checklist.planner import ChecklistPlanner
from onboardai.persona.matcher import PersonaMatcher, extract_employee_profile
from onboardai.models import TaskPriority


def test_persona_matcher_matches_backend_intern(dataset_root):
    matcher = PersonaMatcher.from_markdown(dataset_root / "employee_personas.md")
    profile = extract_employee_profile("Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.")
    match = matcher.match(profile)
    assert match.persona.name == "Riya Sharma"
    assert match.persona.role_family == "backend"
    assert "node.js" in match.persona.tech_stack


def test_checklist_planner_marks_preinstalled_tools_optional(dataset_root):
    matcher = PersonaMatcher.from_markdown(dataset_root / "employee_personas.md")
    planner = ChecklistPlanner.from_markdown(
        dataset_root / "onboarding_checklists.md",
        dataset_root / "starter_tickets.md",
    )
    profile = extract_employee_profile(
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js and I have docker and vs code installed."
    )
    match = matcher.match(profile)
    plan = planner.build_plan(profile, match)
    docker_task = next(task for task in plan if task.task_id == "BI-03")
    vscode_task = next(task for task in plan if task.task_id == "BI-04")
    assert docker_task.priority == TaskPriority.OPTIONAL
    assert vscode_task.priority == TaskPriority.OPTIONAL


def test_checklist_planner_picks_matching_starter_ticket(dataset_root):
    matcher = PersonaMatcher.from_markdown(dataset_root / "employee_personas.md")
    planner = ChecklistPlanner.from_markdown(
        dataset_root / "onboarding_checklists.md",
        dataset_root / "starter_tickets.md",
    )
    profile = extract_employee_profile(
        "Hi, I'm Vikram. I've joined as a Junior Backend Engineer working on Python and FastAPI."
    )
    match = matcher.match(profile)
    starter_ticket = planner.pick_starter_ticket(match)
    assert starter_ticket is not None
    assert starter_ticket["Ticket ID"] == "FLOW-JUNIOR-001"
    assert starter_ticket["Repo"] == "workflow-core-demo"


def test_persona_matcher_preserves_full_stack_role(dataset_root):
    matcher = PersonaMatcher.from_markdown(dataset_root / "employee_personas.md")
    profile = extract_employee_profile(
        "Hi, I'm Arjun. I've joined as a Junior Full-Stack Engineer working on Node.js and React."
    )
    match = matcher.match(profile)
    assert profile.role_family == "full-stack"
    assert match.persona.name == "Arjun Nair"
    assert match.persona.role_family == "full-stack"
