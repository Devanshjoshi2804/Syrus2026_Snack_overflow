from __future__ import annotations

import re
from pathlib import Path

from onboardai.content.parser import parse_personas
from onboardai.models import EmployeeProfile, PersonaDefinition, PersonaMatch


NAME_RE = re.compile(r"(?:i[' ]?m|i am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)", re.IGNORECASE)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


KNOWN_TECH = {
    "node.js": "node.js",
    "node": "node.js",
    "typescript": "typescript",
    "react": "react",
    "python": "python",
    "fastapi": "fastapi",
    "java": "java",
    "terraform": "terraform",
    "kubernetes": "kubernetes",
    "aws": "aws",
    "docker": "docker",
}

KNOWN_TOOLS = {"docker", "vs code", "vscode", "node.js", "node", "pnpm", "poetry", "python"}

EXPERIENCE_ORDER = ["intern", "junior", "senior"]


def _normalize_role_family(text: str) -> str:
    lowered = text.lower()
    if "full-stack" in lowered or "full stack" in lowered:
        return "full-stack"
    if "front" in lowered or "react" in lowered:
        return "frontend"
    if "devops" in lowered or "platform" in lowered:
        return "devops"
    return "backend"


def _normalize_experience(text: str) -> str:
    lowered = text.lower()
    if "senior" in lowered or "staff" in lowered:
        return "senior"
    if "junior" in lowered or "engineer i" in lowered:
        return "junior"
    return "intern"


def extract_employee_profile(message: str) -> EmployeeProfile:
    lower = message.lower()
    name_match = NAME_RE.search(message)
    email_match = EMAIL_RE.search(message)
    tech_stack = sorted(
        {
            normalized
            for token, normalized in KNOWN_TECH.items()
            if token in lower
        }
    )
    preinstalled: set[str] = set()
    if any(marker in lower for marker in ("have", "already installed", "installed")):
        for tool in KNOWN_TOOLS:
            if tool in lower:
                normalized = "vs code" if tool == "vscode" else tool
                preinstalled.add(normalized)
    department_hint = None
    if "squad" in lower or "team" in lower:
        department_hint = message
    return EmployeeProfile(
        name=name_match.group(1) if name_match else "New Hire",
        role_family=_normalize_role_family(message),
        experience_level=_normalize_experience(message),
        tech_stack=tech_stack,
        department_hint=department_hint,
        preinstalled_tools=preinstalled,
        email=email_match.group(0) if email_match else None,
    )


class PersonaMatcher:
    def __init__(self, personas: list[PersonaDefinition]) -> None:
        self.personas = personas

    @classmethod
    def from_markdown(cls, path: str | Path) -> "PersonaMatcher":
        return cls(parse_personas(path))

    def match(self, profile: EmployeeProfile) -> PersonaMatch:
        scored = [self._score(profile, persona) for persona in self.personas]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[0]

    def _score(self, profile: EmployeeProfile, persona: PersonaDefinition) -> PersonaMatch:
        role_score = 1.0 if profile.role_family == persona.role_family else 0.0
        overlap = set(profile.tech_stack) & set(persona.tech_stack)
        stack_score = len(overlap) / max(len(profile.tech_stack), 1)
        experience_score = self._experience_distance(profile.experience_level, persona.experience_level)
        dept_score = 1.0 if profile.role_family in persona.department.lower() else 0.5
        total = (
            role_score * 0.35
            + stack_score * 0.30
            + experience_score * 0.25
            + dept_score * 0.10
        )
        reasons = [
            f"Role match: {profile.role_family} -> {persona.role_family}",
            f"Tech overlap: {', '.join(sorted(overlap)) or 'none'}",
            f"Experience alignment: {profile.experience_level} -> {persona.experience_level}",
        ]
        return PersonaMatch(persona_id=persona.persona_id, score=round(total, 4), reasons=reasons, persona=persona)

    @staticmethod
    def _experience_distance(left: str, right: str) -> float:
        if left == right:
            return 1.0
        try:
            distance = abs(EXPERIENCE_ORDER.index(left) - EXPERIENCE_ORDER.index(right))
        except ValueError:
            return 0.2
        return {1: 0.6, 2: 0.2}.get(distance, 0.2)
