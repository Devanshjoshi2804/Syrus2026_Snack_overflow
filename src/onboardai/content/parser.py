from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from onboardai.models import (
    AutomationMode,
    ChecklistTask,
    KnowledgeChunk,
    PersonaDefinition,
    SetupGuideSection,
    SetupGuideStep,
    TaskPriority,
)


TABLE_SEPARATOR_RE = re.compile(r"^\|(?:\s*-+\s*\|)+\s*$")


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _strip_leading_numbering(value: str) -> str:
    return re.sub(r"^\d+\.\s*", "", value).strip()


def _parse_markdown_table(lines: Iterable[str]) -> list[dict[str, str]]:
    filtered = [line.strip() for line in lines if line.strip().startswith("|")]
    if len(filtered) < 2:
        return []
    header = [cell.strip() for cell in filtered[0].strip("|").split("|")]
    rows: list[dict[str, str]] = []
    for raw_row in filtered[1:]:
        if TABLE_SEPARATOR_RE.match(raw_row):
            continue
        values = [cell.strip() for cell in raw_row.strip("|").split("|")]
        if len(values) != len(header):
            continue
        rows.append(dict(zip(header, values, strict=False)))
    return rows


def parse_markdown_table(lines: Iterable[str]) -> list[dict[str, str]]:
    return _parse_markdown_table(lines)


def _infer_role_family(*values: str) -> str:
    joined = " ".join(values).lower()
    if "full-stack" in joined or "full stack" in joined:
        return "full-stack"
    if "frontend" in joined or "react" in joined:
        return "frontend"
    if "devops" in joined or "platform" in joined:
        return "devops"
    if "backend" in joined or "python" in joined or "node" in joined:
        return "backend"
    return "backend"


def _infer_team(department: str) -> str | None:
    if "—" in department:
        return department.split("—", 1)[1].strip()
    return department.strip() if department else None


def _infer_automation_mode(title: str, category: str) -> AutomationMode:
    title_lower = title.lower()
    category_lower = category.lower()
    if "read " in title_lower or category_lower == "knowledge":
        return AutomationMode.KNOWLEDGE
    if any(token in title_lower for token in ("install", "run", "clone", "configure", "verify")):
        return AutomationMode.AGENT_TERMINAL
    if any(token in title_lower for token in ("join", "accept", "sign", "set up slack", "set up github")):
        return AutomationMode.AGENT_BROWSER
    if any(token in category_lower for token in ("compliance", "onboarding", "finance", "hr")):
        return AutomationMode.MANUAL_EXTERNAL
    return AutomationMode.SELF_SERVE


def _infer_evidence(title: str, automation_mode: AutomationMode) -> list[str]:
    title_lower = title.lower()
    if "node.js" in title_lower:
        return ["node --version"]
    if "pnpm" in title_lower:
        return ["pnpm --version"]
    if "git" in title_lower and "config" in title_lower:
        return ["git config --global user.email"]
    if automation_mode == AutomationMode.KNOWLEDGE:
        return ["acknowledged"]
    if automation_mode == AutomationMode.MANUAL_EXTERNAL:
        return ["status update"]
    return []


def parse_personas(path: str | Path) -> list[PersonaDefinition]:
    text = Path(path).read_text(encoding="utf-8")
    chunks = re.split(r"^##\s+Persona\s+\d+:\s+", text, flags=re.MULTILINE)
    matches = re.findall(r"^##\s+Persona\s+\d+:\s+(.+)$", text, flags=re.MULTILINE)
    personas: list[PersonaDefinition] = []
    for title, body in zip(matches, chunks[1:], strict=False):
        lines = body.splitlines()
        table_lines: list[str] = []
        focus_points: list[str] = []
        collect_focus = False
        for line in lines:
            if line.startswith("|"):
                table_lines.append(line)
            if line.startswith("### Expected Onboarding Focus"):
                collect_focus = True
                continue
            if collect_focus:
                if line.startswith("- "):
                    focus_points.append(line[2:].strip())
                elif line.startswith("## "):
                    break
        row_table = _parse_markdown_table(table_lines)
        fields = {row["Field"].strip("* "): row["Value"] for row in row_table if "Field" in row}
        role = fields.get("Role", title)
        department = fields.get("Department", "Engineering")
        persona = PersonaDefinition(
            persona_id=_slugify(title),
            name=fields.get("Name", title.split("—", 1)[0].strip()),
            title=title.strip(),
            role_family=_infer_role_family(title, role, department),
            experience_level=fields.get("Experience Level", "Intern").split()[0].lower(),
            tech_stack=[part.strip().lower() for part in fields.get("Tech Stack", "").split(",") if part.strip()],
            department=department,
            team=_infer_team(department),
            manager_name=fields.get("Manager", "").split("(")[0].strip() or None,
            mentor_name=(fields.get("Mentor") or fields.get("Buddy") or "").split("(")[0].strip() or None,
            email=fields.get("Email") or None,
            start_date=fields.get("Start Date") or None,
            location=fields.get("Location") or None,
            focus_points=focus_points,
            raw_fields=fields,
        )
        personas.append(persona)
    return personas


def parse_checklists(path: str | Path) -> dict[str, list[ChecklistTask]]:
    text = Path(path).read_text(encoding="utf-8")
    sections = re.split(r"^##\s+", text, flags=re.MULTILINE)
    headings = re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)
    parsed: dict[str, list[ChecklistTask]] = {}
    for heading, body in zip(headings, sections[1:], strict=False):
        lines = body.splitlines()
        table_lines = [line for line in lines if line.startswith("|")]
        rows = _parse_markdown_table(table_lines)
        tasks: list[ChecklistTask] = []
        for row in rows:
            task_id = row.get("#") or row.get("ID")
            title = row.get("Task")
            if not task_id or not title:
                continue
            category = row.get("Category", "General")
            automation_mode = _infer_automation_mode(title, category)
            tasks.append(
                ChecklistTask(
                    task_id=task_id,
                    title=title,
                    category=category,
                    deadline=row.get("Deadline"),
                    owner=row.get("Owner"),
                    source_section=heading,
                    automation_mode=automation_mode,
                    priority=TaskPriority.REQUIRED,
                    evidence_required=_infer_evidence(title, automation_mode),
                )
            )
        if tasks:
            parsed[heading] = tasks
    return parsed


def parse_starter_tickets(path: str | Path) -> dict[str, dict[str, str]]:
    if not Path(path).exists():
        return {}
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    rows = _parse_markdown_table(lines)
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        persona_key = row.get("Persona")
        if not persona_key:
            continue
        result[persona_key.strip().lower()] = row
    return result


def normalize_shell_commands(commands: list[str]) -> list[str]:
    normalized: list[str] = []
    current_dir: str | None = None
    for raw_command in commands:
        command = raw_command.strip()
        if not command:
            continue
        if command.startswith("cd "):
            current_dir = command[3:].strip()
            continue
        if current_dir and not command.startswith("cd "):
            normalized.append(f"cd {current_dir} && {command}")
            continue
        normalized.append(command)
    return normalized


def parse_setup_guides(path: str | Path) -> dict[str, SetupGuideSection]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    sections: dict[str, SetupGuideSection] = {}
    current_section: SetupGuideSection | None = None
    current_step_title: str | None = None
    current_step_notes: list[str] = []
    current_step_commands: list[str] = []
    current_step_expected: str | None = None
    in_code_block = False

    def flush_step() -> None:
        nonlocal current_step_title, current_step_notes, current_step_commands, current_step_expected
        if not current_section or not current_step_title:
            current_step_title = None
            current_step_notes = []
            current_step_commands = []
            current_step_expected = None
            return
        current_section.steps.append(
            SetupGuideStep(
                section_title=current_section.title,
                step_id=_slugify(current_step_title),
                step_title=current_step_title,
                commands=normalize_shell_commands(current_step_commands),
                expected_result=current_step_expected,
                notes=current_step_notes.copy(),
            )
        )
        current_step_title = None
        current_step_notes = []
        current_step_commands = []
        current_step_expected = None

    def flush_section() -> None:
        nonlocal current_section
        flush_step()
        if current_section:
            sections[current_section.section_id] = current_section
        current_section = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            flush_section()
            section_title = _strip_leading_numbering(stripped[3:].strip())
            current_section = SetupGuideSection(
                section_id=_slugify(section_title),
                title=section_title,
            )
            continue
        if stripped.startswith("### "):
            flush_step()
            current_step_title = stripped[4:].strip()
            continue
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            current_step_commands.append(line)
            continue
        if current_step_title:
            if stripped.startswith("Expected result:"):
                current_step_expected = stripped.split("Expected result:", 1)[1].strip()
            elif stripped.startswith("- "):
                current_step_notes.append(stripped[2:].strip())

    flush_section()
    return sections


def parse_template_block(path: str | Path, heading: str) -> str:
    text = Path(path).read_text(encoding="utf-8")
    pattern = rf"##\s+{re.escape(heading)}.*?```(.*?)```"
    match = re.search(pattern, text, flags=re.DOTALL)
    if not match:
        raise ValueError(f"Template heading '{heading}' not found in {path}")
    return match.group(1).strip()


def parse_contacts(path: str | Path) -> dict[str, dict[str, str]]:
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    capture = False
    table_lines: list[str] = []
    for line in lines:
        if line.startswith("## 4. Key Contacts for New Employees"):
            capture = True
            continue
        if capture:
            if line.startswith("## "):
                break
            if line.startswith("|"):
                table_lines.append(line)
    rows = _parse_markdown_table(table_lines)
    return {row["Need"].lower(): row for row in rows if "Need" in row}


def chunk_markdown(path: str | Path) -> list[KnowledgeChunk]:
    source_path = str(Path(path))
    text = Path(path).read_text(encoding="utf-8")
    lines = text.splitlines()
    chunks: list[KnowledgeChunk] = []
    heading_stack: list[str] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        title = " > ".join(heading_stack) if heading_stack else Path(path).stem
        chunk_text = "\n".join(buffer).strip()
        if chunk_text:
            chunk_id = f"{Path(path).stem}:{_slugify(title)}:{len(chunks)}"
            chunks.append(
                KnowledgeChunk(
                    chunk_id=chunk_id,
                    source_path=source_path,
                    title=title,
                    text=chunk_text,
                    metadata={"headings": heading_stack.copy()},
                )
            )
        buffer.clear()

    for line in lines:
        if line.startswith("#"):
            flush()
            depth = len(line) - len(line.lstrip("#"))
            heading = line[depth:].strip()
            heading_stack[:] = heading_stack[: depth - 1]
            heading_stack.append(heading)
            buffer.append(heading)
            continue
        buffer.append(line)
    flush()
    return chunks
