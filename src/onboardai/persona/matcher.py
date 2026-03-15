from __future__ import annotations

import re
from pathlib import Path

from onboardai.content.parser import parse_personas
from onboardai.models import (
    EmployeeProfile,
    PersonaDefinition,
    PersonaMatch,
    PersonaResolutionMode,
)


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
ROLE_DISPLAY = {
    "backend": "Backend Engineer",
    "frontend": "Frontend Engineer",
    "devops": "DevOps Engineer",
    "full-stack": "Full-Stack Engineer",
}


def _normalize_role_family(text: str) -> str:
    lowered = text.lower()
    if "full-stack" in lowered or "full stack" in lowered:
        return "full-stack"
    if "front" in lowered or "react" in lowered or "ui" in lowered:
        return "frontend"
    if "devops" in lowered or "platform" in lowered or "sre" in lowered:
        return "devops"
    return "backend"


def _normalize_experience(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("senior", "staff", "lead", "principal")):
        return "senior"
    if any(token in lowered for token in ("junior", "engineer i")):
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
        preinstalled_tools=sorted(preinstalled),
        email=email_match.group(0) if email_match else None,
    )


class PersonaMatcher:
    def __init__(self, personas: list[PersonaDefinition]) -> None:
        self.personas = personas

    @classmethod
    def from_markdown(cls, path: str | Path) -> "PersonaMatcher":
        return cls(parse_personas(path))

    def match(self, profile: EmployeeProfile) -> PersonaMatch:
        exact_candidates = [
            self._score(profile, persona, resolution_mode=PersonaResolutionMode.EXACT_DATASET_PERSONA)
            for persona in self.personas
            if persona.role_family == profile.role_family and persona.experience_level == profile.experience_level
        ]
        if exact_candidates:
            exact_candidates.sort(key=lambda item: item.score, reverse=True)
            return exact_candidates[0]

        same_role_candidates = [
            persona for persona in self.personas if persona.role_family == profile.role_family
        ]
        if same_role_candidates:
            base_persona = max(same_role_candidates, key=lambda persona: self._raw_score(profile, persona))
            synthetic_persona = self._synthesize_persona(profile, base_persona)
            return self._score(
                profile,
                synthetic_persona,
                resolution_mode=PersonaResolutionMode.SYNTHETIC_ROLE_EXPERIENCE_OVERLAY,
                base_role_persona_id=base_persona.persona_id,
                experience_overlay=profile.experience_level,
            )

        scored = [self._score(profile, persona, resolution_mode=PersonaResolutionMode.EXACT_DATASET_PERSONA) for persona in self.personas]
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[0]

    def _synthesize_persona(self, profile: EmployeeProfile, base: PersonaDefinition) -> PersonaDefinition:
        stack = sorted(set(profile.tech_stack or base.tech_stack or []))
        title = f"{ROLE_DISPLAY.get(profile.role_family, 'Engineer')} ({' + '.join(stack).title() if stack else 'General'})"
        if profile.role_family == "frontend":
            title = "Senior Frontend Engineer (React)" if profile.experience_level == "senior" else "Frontend Engineer (React)"
        elif profile.role_family == "backend":
            title = f"{profile.experience_level.title()} Backend Engineer ({'Node.js' if 'node.js' in stack else 'Python'})"
        synthesized_focus = list(base.focus_points)
        if profile.experience_level == "senior":
            synthesized_focus.extend(
                [
                    "Prioritize system architecture review before detailed setup walkthroughs.",
                    "Focus on deployment standards, code review expectations, and first-task ownership.",
                ]
            )
        elif profile.experience_level == "intern":
            synthesized_focus.extend(
                [
                    "Provide concrete setup walkthroughs and validation steps.",
                    "Front-load environment verification before deeper architecture review.",
                ]
            )
        else:
            synthesized_focus.extend(
                [
                    "Balance environment setup, standards review, and starter task prep.",
                ]
            )
        return base.model_copy(
            update={
                "persona_id": f"synthetic-{profile.role_family}-{profile.experience_level}",
                "name": profile.name if profile.name != "New Hire" else base.name,
                "title": title,
                "experience_level": profile.experience_level,
                "tech_stack": stack or base.tech_stack,
                "focus_points": synthesized_focus,
                "raw_fields": {
                    **base.raw_fields,
                    "Role": title,
                    "Experience Level": profile.experience_level.title(),
                    "Name": profile.name if profile.name != "New Hire" else base.name,
                },
            }
        )

    def _score(
        self,
        profile: EmployeeProfile,
        persona: PersonaDefinition,
        *,
        resolution_mode: PersonaResolutionMode,
        base_role_persona_id: str | None = None,
        experience_overlay: str | None = None,
    ) -> PersonaMatch:
        total, overlap = self._raw_score(profile, persona, include_overlap=True)
        reasons = [
            f"Role match: {profile.role_family} -> {persona.role_family}",
            f"Tech overlap: {', '.join(sorted(overlap)) or 'none'}",
            f"Experience alignment: {profile.experience_level} -> {persona.experience_level}",
        ]
        if resolution_mode == PersonaResolutionMode.SYNTHETIC_ROLE_EXPERIENCE_OVERLAY:
            reasons.append("Used a synthetic persona overlay because the dataset does not include this exact role and level combination.")
        return PersonaMatch(
            persona_id=persona.persona_id,
            score=round(total, 4),
            reasons=reasons,
            persona=persona,
            resolution_mode=resolution_mode,
            base_role_persona_id=base_role_persona_id,
            experience_overlay=experience_overlay,
        )

    def _raw_score(
        self,
        profile: EmployeeProfile,
        persona: PersonaDefinition,
        *,
        include_overlap: bool = False,
    ) -> tuple[float, set[str]] | float:
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
        if include_overlap:
            return total, overlap
        return total

    @staticmethod
    def _experience_distance(left: str, right: str) -> float:
        if left == right:
            return 1.0
        try:
            distance = abs(EXPERIENCE_ORDER.index(left) - EXPERIENCE_ORDER.index(right))
        except ValueError:
            return 0.2
        return {1: 0.6, 2: 0.2}.get(distance, 0.2)
