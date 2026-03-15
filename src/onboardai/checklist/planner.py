from __future__ import annotations

from pathlib import Path

from onboardai.content.parser import parse_checklists, parse_starter_tickets
from onboardai.models import (
    AutomationMode,
    ChecklistTask,
    EmployeeProfile,
    JourneyMode,
    PersonaMatch,
    TaskPhase,
    TaskPriority,
)


PREINSTALLED_TOOL_MAP = {
    "docker": ("docker",),
    "vs code": ("vs code", "vscode"),
    "node.js": ("node.js", "node"),
    "pnpm": ("pnpm",),
    "python": ("python", "pyenv", "poetry"),
}

ACCESS_CORE_TASKS = {"C-01", "C-02", "C-03", "C-07"}
DEFERRED_ACCESS_TASKS = {"C-04", "C-05", "C-06", "C-08", "C-09", "C-10"}
COMPLIANCE_TASKS = {"C-14", "C-15", "C-16", "C-17", "C-18", "C-19", "C-20"}
BACKEND_INTERN_SEQUENCE = [
    "C-01",
    "C-02",
    "C-03",
    "C-07",
    "BI-01",
    "BI-02",
    "BI-SYNTH-GIT",
    "BI-05",
    "BI-06",
    "BI-07",
    "BI-08",
    "BI-09",
    "BI-10",
    "BI-11",
    "BI-12",
    "BI-13",
    "BI-14",
    "BI-18",
    "BI-15",
]
SENIOR_FRONTEND_SEQUENCE = [
    "C-01",
    "C-02",
    "C-03",
    "C-07",
    "JFR-09",
    "JFR-13",
    "SFE-DEPLOY",
    "JFR-11",
    "JFR-12",
    "JFR-04",
    "JFR-05",
    "JFR-06",
    "JFR-18",
]


class ChecklistPlanner:
    def __init__(
        self,
        checklists: dict[str, list[ChecklistTask]],
        starter_tickets: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self.checklists = checklists
        self.starter_tickets = starter_tickets or {}

    @classmethod
    def from_markdown(
        cls,
        checklist_path: str | Path,
        starter_ticket_path: str | Path | None = None,
    ) -> "ChecklistPlanner":
        starter_tickets = parse_starter_tickets(starter_ticket_path) if starter_ticket_path else {}
        return cls(parse_checklists(checklist_path), starter_tickets)

    def build_plan(
        self,
        profile: EmployeeProfile,
        match: PersonaMatch,
        journey_mode: JourneyMode = JourneyMode.GUIDED_PRODUCTIVITY_FIRST,
    ) -> list[ChecklistTask]:
        common = [
            task.model_copy(deep=True)
            for task in self.checklists.get("Common Checklist (All Roles & Levels)", [])
        ]
        role_heading = self._select_role_heading(profile, match)
        role_tasks = [task.model_copy(deep=True) for task in self.checklists.get(role_heading, [])]
        role_tasks.extend(self._synthetic_overlay_tasks(profile, match))

        combined = common + role_tasks
        for canonical_order, task in enumerate(combined, start=1):
            task.canonical_order = canonical_order
            task.priority = self._infer_priority(task)
            task.role_relevance = [match.persona.role_family]
            task.experience_relevance = [profile.experience_level]
            self._apply_preinstalled_adjustment(task, profile)
            self._assign_guided_metadata(task, profile, match)

        if journey_mode == JourneyMode.GUIDED_PRODUCTIVITY_FIRST:
            sequence_map = self._preferred_sequence_map(profile, match)
            for task in combined:
                if task.task_id in sequence_map:
                    task.display_rank = sequence_map[task.task_id]
                else:
                    task.display_rank = self._fallback_display_rank(task)
            combined.sort(key=lambda task: (task.display_rank, task.canonical_order))
        else:
            combined.sort(key=lambda task: task.canonical_order)
        return combined

    def _select_role_heading(self, profile: EmployeeProfile, match: PersonaMatch) -> str:
        if profile.role_family == "frontend":
            return "Junior Frontend Checklist (React)"
        persona = match.persona
        best_heading = ""
        best_score = -1.0
        for heading in self.checklists:
            if heading.startswith("Common Checklist"):
                continue
            heading_lower = heading.lower()
            score = 0.0
            if persona.role_family in heading_lower:
                score += 1.0
            if persona.experience_level in heading_lower:
                score += 1.0
            if any(tech in heading_lower for tech in persona.tech_stack):
                score += 1.0
            if profile.role_family in heading_lower:
                score += 0.5
            if score > best_score:
                best_score = score
                best_heading = heading
        return best_heading

    def _infer_priority(self, task: ChecklistTask) -> TaskPriority:
        title = task.title.lower()
        category = task.category.lower()
        deadline = (task.deadline or "").lower()
        if task.task_id in COMPLIANCE_TASKS:
            return TaskPriority.DEFERRED
        if any(token in title for token in ("attend ", "meet ", "sign ", "training")):
            return TaskPriority.DEFERRED
        if category in {"compliance", "hr", "finance", "skill building"}:
            return TaskPriority.DEFERRED
        if "week 1" in deadline or "week 2" in deadline or "week 3" in deadline:
            return TaskPriority.DEFERRED
        if task.automation_mode == AutomationMode.KNOWLEDGE:
            return TaskPriority.OPTIONAL
        return TaskPriority.REQUIRED

    def _apply_preinstalled_adjustment(self, task: ChecklistTask, profile: EmployeeProfile) -> None:
        title = task.title.lower()
        for tool in profile.preinstalled_tools:
            keywords = PREINSTALLED_TOOL_MAP.get(tool, (tool,))
            if any(keyword in title for keyword in keywords) and task.category.lower() == "environment setup":
                task.priority = TaskPriority.OPTIONAL
                note = f"Marked optional because {tool} was reported as already installed."
                task.notes = note if not task.notes else f"{task.notes} {note}"
                return

    def _synthetic_overlay_tasks(
        self,
        profile: EmployeeProfile,
        match: PersonaMatch,
    ) -> list[ChecklistTask]:
        tasks: list[ChecklistTask] = []
        if profile.role_family == "backend" and profile.experience_level == "intern":
            tasks.append(
                ChecklistTask(
                    task_id="BI-SYNTH-GIT",
                    title="Configure Git identity for NovaByte development",
                    category="Environment Setup",
                    deadline="Day 1",
                    source_section="Synthetic Backend Intern Overlay",
                    automation_mode=AutomationMode.AGENT_TERMINAL,
                    evidence_required=["git config --global user.email"],
                    notes="Derived from setup_guides.md Configure Git identity step.",
                    role_relevance=["backend"],
                    experience_relevance=["intern"],
                )
            )
        if profile.role_family == "frontend" and profile.experience_level == "senior":
            tasks.append(
                ChecklistTask(
                    task_id="SFE-DEPLOY",
                    title="Review deployment standards and deployment health expectations",
                    category="Knowledge",
                    deadline="Day 2",
                    source_section="Synthetic Senior Frontend Overlay",
                    automation_mode=AutomationMode.KNOWLEDGE,
                    evidence_required=["acknowledged"],
                    notes="Derived from engineering standards deployment rules and senior frontend starter ticket context.",
                    role_relevance=["frontend"],
                    experience_relevance=["senior"],
                )
            )
        return tasks

    def _assign_guided_metadata(
        self,
        task: ChecklistTask,
        profile: EmployeeProfile,
        match: PersonaMatch,
    ) -> None:
        task.display_phase = self._infer_phase(task, profile, match)
        task.blocking_dependencies = self._blocking_dependencies(task.task_id)
        task.milestone_tag = self._milestone_tag(task)
        task.show_in_guided_path = True

    def _infer_phase(
        self,
        task: ChecklistTask,
        profile: EmployeeProfile,
        match: PersonaMatch,
    ) -> TaskPhase:
        task_id = task.task_id.upper()
        category = task.category.lower()
        title = task.title.lower()
        if task_id in ACCESS_CORE_TASKS:
            return TaskPhase.GET_ACCESS
        if task_id in COMPLIANCE_TASKS or any(
            token in category for token in ("compliance", "hr", "finance")
        ):
            return TaskPhase.ADMIN_COMPLIANCE
        if task_id in DEFERRED_ACCESS_TASKS:
            return TaskPhase.ADMIN_COMPLIANCE
        if category in {"environment setup", "verification", "exploration"}:
            return TaskPhase.GET_CODING
        if category == "first task":
            return TaskPhase.LEARN_SYSTEM
        if category == "knowledge":
            return TaskPhase.LEARN_SYSTEM
        if "pr" in title or "branch" in title or "starter ticket" in title:
            return TaskPhase.LEARN_SYSTEM
        if profile.role_family == "frontend" and profile.experience_level == "senior":
            return TaskPhase.LEARN_SYSTEM
        return TaskPhase.ADMIN_COMPLIANCE

    def _preferred_sequence_map(
        self,
        profile: EmployeeProfile,
        match: PersonaMatch,
    ) -> dict[str, int]:
        if profile.role_family == "backend" and profile.experience_level == "intern":
            return {task_id: index * 10 for index, task_id in enumerate(BACKEND_INTERN_SEQUENCE, start=1)}
        if profile.role_family == "frontend" and profile.experience_level == "senior":
            return {task_id: index * 10 for index, task_id in enumerate(SENIOR_FRONTEND_SEQUENCE, start=1)}
        return {}

    def _fallback_display_rank(self, task: ChecklistTask) -> int:
        phase_base = {
            TaskPhase.GET_ACCESS: 1000,
            TaskPhase.GET_CODING: 2000,
            TaskPhase.LEARN_SYSTEM: 3000,
            TaskPhase.ADMIN_COMPLIANCE: 4000,
        }[task.display_phase]
        deadline = (task.deadline or "").lower()
        deadline_bias = 0
        if "day 1" in deadline:
            deadline_bias = 10
        elif "day 2" in deadline:
            deadline_bias = 20
        elif "day 3" in deadline:
            deadline_bias = 30
        elif "week 1" in deadline:
            deadline_bias = 40
        elif "week 2" in deadline:
            deadline_bias = 50
        elif "week 3" in deadline:
            deadline_bias = 60
        return phase_base + deadline_bias + task.canonical_order

    def _blocking_dependencies(self, task_id: str) -> list[str]:
        dependency_map = {
            "C-02": ["C-01"],
            "C-03": ["C-02"],
            "C-07": ["C-02"],
            "BI-01": ["C-01", "C-02"],
            "BI-02": ["BI-01"],
            "BI-SYNTH-GIT": ["C-02"],
            "BI-05": ["BI-01", "BI-02", "BI-SYNTH-GIT"],
            "BI-06": ["BI-05"],
            "BI-07": ["BI-05"],
            "BI-08": ["BI-07"],
            "BI-09": ["BI-06", "BI-07"],
            "BI-10": ["BI-09"],
            "BI-18": ["BI-10"],
            "BI-15": ["BI-13", "BI-14"],
            "JFR-04": ["C-02"],
            "JFR-05": ["JFR-04"],
            "JFR-06": ["JFR-05"],
            "JFR-18": ["JFR-06"],
        }
        return dependency_map.get(task_id.upper(), [])

    def _milestone_tag(self, task: ChecklistTask) -> str | None:
        task_id = task.task_id.upper()
        title = task.title.lower()
        if task_id in ACCESS_CORE_TASKS:
            return "access"
        if any(token in title for token in ("node.js", "pnpm", "git identity", "python 3.11", "poetry")):
            return "environment"
        if "clone" in title:
            return "repo"
        if any(token in title for token in ("start the service", "start development server", "run unit tests", "verify it loads")):
            return "service"
        if task.category.lower() == "knowledge" and any(
            token in title for token in ("architecture", "api standards", "pr guidelines", "design system", "deployment")
        ):
            return "docs"
        if "starter ticket" in title:
            return "starter"
        return None

    def pick_starter_ticket(self, match: PersonaMatch) -> dict[str, str] | None:
        persona = match.persona
        persona_text = " ".join(
            [
                persona.title.lower(),
                persona.role_family.lower(),
                persona.experience_level.lower(),
                " ".join(persona.tech_stack).lower(),
            ]
        )
        best_ticket: dict[str, str] | None = None
        best_score = -1
        for key, ticket in self.starter_tickets.items():
            score = 0
            if key in persona_text:
                score += 5
            if persona.experience_level.lower() in key:
                score += 3
            if persona.role_family.lower() in key:
                score += 2
            if any(tech in key for tech in persona.tech_stack):
                score += 1
            if score > best_score:
                best_ticket = ticket
                best_score = score
        return best_ticket
