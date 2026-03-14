from __future__ import annotations

from pathlib import Path

from onboardai.content.parser import parse_checklists, parse_starter_tickets
from onboardai.models import (
    AutomationMode,
    ChecklistTask,
    EmployeeProfile,
    PersonaMatch,
    TaskPriority,
)


PREINSTALLED_TOOL_MAP = {
    "docker": ("docker",),
    "vs code": ("vs code", "vscode"),
    "node.js": ("node.js", "node"),
    "pnpm": ("pnpm",),
    "python": ("python", "pyenv", "poetry"),
}


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

    def build_plan(self, profile: EmployeeProfile, match: PersonaMatch) -> list[ChecklistTask]:
        common = [task.model_copy(deep=True) for task in self.checklists.get("Common Checklist (All Roles & Levels)", [])]
        role_heading = self._select_role_heading(match)
        role_tasks = [task.model_copy(deep=True) for task in self.checklists.get(role_heading, [])]
        combined = common + role_tasks
        for task in combined:
            task.priority = self._infer_priority(task)
            self._apply_preinstalled_adjustment(task, profile)
        return combined

    def _select_role_heading(self, match: PersonaMatch) -> str:
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
            if score > best_score:
                best_score = score
                best_heading = heading
        return best_heading

    def _infer_priority(self, task: ChecklistTask) -> TaskPriority:
        title = task.title.lower()
        category = task.category.lower()
        deadline = (task.deadline or "").lower()
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
