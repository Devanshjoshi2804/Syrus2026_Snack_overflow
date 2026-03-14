from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from onboardai.content.parser import parse_template_block
from onboardai.models import CompletionSummary, OnboardingState, TaskPriority, TaskStatus


class CompletionReportGenerator:
    def __init__(self, template_path: str | Path, output_dir: str | Path) -> None:
        self.template_path = Path(template_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_summary(self, state: OnboardingState, starter_ticket: dict[str, str] | None = None) -> CompletionSummary:
        persona = state.matched_persona.persona if state.matched_persona else None
        completed = [task for task in state.task_plan if task.status == TaskStatus.COMPLETED]
        pending = [task for task in state.task_plan if task.status in {TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED}]
        skipped = [task for task in state.task_plan if task.status == TaskStatus.SKIPPED]
        summary = CompletionSummary(
            employee_name=state.employee_profile.name if state.employee_profile else "New Hire",
            employee_email=state.employee_profile.email if state.employee_profile else None,
            role=persona.raw_fields.get("Role", persona.title) if persona else "Engineer",
            team=persona.team or persona.department if persona else "Engineering",
            manager_name=persona.manager_name if persona else None,
            manager_email=persona.manager_email if persona else None,
            mentor_name=persona.mentor_name if persona else None,
            mentor_email=persona.mentor_email if persona else None,
            completed_items=completed,
            pending_items=pending,
            skipped_items=skipped,
            verification_log=state.verification_log,
        )
        summary.score = self._compute_score(summary, state)
        if starter_ticket:
            summary.notes = f"Starter ticket selected: {starter_ticket.get('Ticket ID', 'N/A')}."
        return summary

    def generate(
        self,
        state: OnboardingState,
        starter_ticket: dict[str, str] | None = None,
    ) -> tuple[Path, Path]:
        summary = self.build_summary(state, starter_ticket=starter_ticket)
        report_id = str(uuid4())
        timestamp = datetime.utcnow()
        safe_name = summary.employee_name.lower().replace(" ", "_")
        html_path = self.output_dir / f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{safe_name}.html"
        json_path = self.output_dir / f"{timestamp.strftime('%Y%m%dT%H%M%SZ')}_{safe_name}.json"
        report_text = self._render_template_text(summary, state, report_id, timestamp, starter_ticket)
        html_path.write_text(self._render_html(summary, report_text), encoding="utf-8")
        json_path.write_text(
            json.dumps(
                {
                    "report_id": report_id,
                    "generated_at": timestamp.isoformat(),
                    "employee": summary.employee_name,
                    "role": summary.role,
                    "team": summary.team,
                    "score": summary.score,
                    "completed_items": [task.model_dump() for task in summary.completed_items],
                    "pending_items": [task.model_dump() for task in summary.pending_items],
                    "skipped_items": [task.model_dump() for task in summary.skipped_items],
                    "verification_log": [entry.model_dump(mode="json") for entry in summary.verification_log],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        return html_path, json_path

    def _compute_score(self, summary: CompletionSummary, state: OnboardingState) -> int:
        required_tasks = [task for task in state.task_plan if task.priority == TaskPriority.REQUIRED]
        env_tasks = [task for task in state.task_plan if task.category.lower() == "environment setup"]
        compliance_tasks = [task for task in state.task_plan if task.category.lower() == "compliance"]
        first_task_tasks = [task for task in state.task_plan if task.category.lower() == "first task"]

        def percentage(tasks: list) -> float:
            if not tasks:
                return 1.0
            done = sum(task.status == TaskStatus.COMPLETED for task in tasks)
            return done / len(tasks)

        score = 0.0
        score += percentage(required_tasks) * 50
        score += percentage(env_tasks) * 20
        score += percentage(compliance_tasks) * 20
        score += percentage(first_task_tasks) * 10
        return int(round(score))

    def _render_template_text(
        self,
        summary: CompletionSummary,
        state: OnboardingState,
        report_id: str,
        timestamp: datetime,
        starter_ticket: dict[str, str] | None,
    ) -> str:
        template = parse_template_block(
            self.template_path, "Template 1: Onboarding Completion Notification (Primary Template)"
        )
        persona = state.matched_persona.persona if state.matched_persona else None
        completed_block = "\n".join(
            f"[✓] {task.title} — Completed"
            for task in summary.completed_items[:10]
        ) or "[✓] No completed items recorded."
        pending_block = "\n".join(
            f"[○] {task.title} — Reason: {task.status.value.replace('_', ' ')}"
            for task in summary.pending_items[:10]
        ) or "[○] None"
        skipped_block = "\n".join(
            f"[—] {task.title} — Approved by: Manager"
            for task in summary.skipped_items[:10]
        ) or "[—] None"
        replacements = {
            "employee_name": summary.employee_name,
            "employee_id": persona.raw_fields.get("Employee ID", "TBD") if persona else "TBD",
            "role": summary.role,
            "department": persona.department if persona else "Engineering",
            "team": summary.team,
            "manager_name": summary.manager_name or "Manager",
            "manager_email": summary.manager_email or "manager@novabyte.dev",
            "mentor_name": summary.mentor_name or "Buddy",
            "mentor_email": summary.mentor_email or "buddy@novabyte.dev",
            "start_date": persona.start_date or "TBD" if persona else "TBD",
            "location": persona.location or "Remote" if persona else "Remote",
            "employee_email": summary.employee_email or persona.email if persona else "new.hire@novabyte.dev",
            "completion_date": timestamp.date().isoformat(),
            "completion_timestamp_iso": timestamp.isoformat(),
            "total_days": "1",
            "total_tasks": str(len(state.task_plan)),
            "completed_count": str(len(summary.completed_items)),
            "completed_percentage": str(int(round((len(summary.completed_items) / max(len(state.task_plan), 1)) * 100))),
            "skipped_count": str(len(summary.skipped_items)),
            "pending_count": str(len(summary.pending_items)),
            "score": str(summary.score),
            "any_additional_notes_or_observations": summary.notes or "Hackathon MVP completion report.",
            "generation_timestamp_iso": timestamp.isoformat(),
            "report_uuid": report_id,
            "ticket_id": (starter_ticket or {}).get("Ticket ID", "N/A"),
            "ticket_title": (starter_ticket or {}).get("Title", "Not assigned"),
            "github_pr_url": (starter_ticket or {}).get("Repo URL", "N/A"),
        }
        template = re.sub(
            r"Completed Items\n-+\n(?:\[✓\].*\n?)+",
            f"Completed Items\n---------------\n{completed_block}\n",
            template,
        )
        template = re.sub(
            r"Pending Items \(if any\)\n-+\n(?:\[○\].*\n?)+",
            f"Pending Items (if any)\n----------------------\n{pending_block}\n",
            template,
        )
        template = re.sub(
            r"Skipped Items \(if any\)\n-+\n(?:\[—\].*\n?)+",
            f"Skipped Items (if any)\n----------------------\n{skipped_block}\n",
            template,
        )
        for key, value in replacements.items():
            template = template.replace(f"{{{key}}}", str(value))
        completion_status = "COMPLETED" if not summary.pending_items else "PARTIALLY COMPLETED"
        template = template.replace("{COMPLETED / PARTIALLY COMPLETED}", completion_status)
        template = template.replace("{PR Merged / PR Submitted / In Progress / Not Started}", "In Progress")
        for label in (
            "Security Awareness Training",
            "Data Privacy & GDPR Training",
            "Code of Conduct Training",
            "Anti-Harassment Training",
            "Insider Threat Awareness",
        ):
            template = template.replace("{COMPLETED / PENDING}", "PENDING", 1)
        for label in (
            "Employee Handbook Signed",
            "NDA Signed",
            "Acceptable Use Policy Signed",
            "IP Assignment Agreement Signed",
        ):
            template = template.replace("{YES / NO}", "NO", 1)
        for label in (
            "GitHub (NovaByte-Technologies org)",
            "Jira",
            "Slack",
            "Notion",
            "VPN (WireGuard)",
        ):
            template = template.replace("{ACTIVE / PENDING}", "PENDING", 1)
        template = template.replace("{ACTIVE / PENDING / N/A}", "N/A", 1)
        return template

    @staticmethod
    def _render_html(summary: CompletionSummary, report_text: str) -> str:
        return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>OnboardAI Completion Report</title>
    <style>
      body {{ font-family: Georgia, serif; margin: 2rem; background: #f5f2ea; color: #1f2937; }}
      .card {{ background: #fffdf7; border: 1px solid #d6c8ab; border-radius: 16px; padding: 2rem; max-width: 960px; margin: 0 auto; box-shadow: 0 14px 28px rgba(15, 23, 42, 0.08); }}
      h1 {{ margin-top: 0; font-size: 2rem; }}
      .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
      .meta div {{ background: #f9f4e8; border-radius: 12px; padding: 0.75rem 1rem; }}
      pre {{ white-space: pre-wrap; font-family: "SFMono-Regular", Consolas, monospace; font-size: 0.95rem; line-height: 1.45; background: #111827; color: #f9fafb; padding: 1rem; border-radius: 12px; overflow-x: auto; }}
    </style>
  </head>
  <body>
    <div class="card">
      <h1>Onboarding Completion Report</h1>
      <div class="meta">
        <div><strong>Employee</strong><br />{html.escape(summary.employee_name)}</div>
        <div><strong>Role</strong><br />{html.escape(summary.role)}</div>
        <div><strong>Team</strong><br />{html.escape(summary.team)}</div>
        <div><strong>Score</strong><br />{summary.score}%</div>
      </div>
      <pre>{html.escape(report_text)}</pre>
    </div>
  </body>
</html>
"""
