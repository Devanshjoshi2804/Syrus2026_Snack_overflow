from __future__ import annotations

import logging
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from onboardai.models import CompletionKind, CompletionSummary, OnboardingState

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class EmailSender:
    """
    Sends real onboarding emails via SMTP.

    Required .env keys:
        SMTP_HOST        e.g. smtp.gmail.com
        SMTP_PORT        e.g. 587
        SMTP_USER        sender address
        SMTP_PASSWORD    app password / API key
        HR_EMAIL         recipient for HR reports (defaults to SMTP_USER)
    """

    def __init__(self) -> None:
        self.host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.port = int(os.getenv("SMTP_PORT", "587"))
        self.user = os.getenv("SMTP_USER", "")
        # Gmail app passwords are displayed with spaces — strip them
        self.password = (os.getenv("SMTP_PASSWORD", "") or "").replace(" ", "")
        self.hr_email = os.getenv("HR_EMAIL") or self.user
        self.from_name = os.getenv("SMTP_FROM_NAME", "OnboardAI")

    def is_available(self) -> bool:
        return bool(self.host and self.user and self.password)

    # ------------------------------------------------------------------
    # Three public send methods
    # ------------------------------------------------------------------

    def send_onboarding_started(self, state: "OnboardingState") -> bool:
        """
        Email sent to HR as soon as a new hire introduces themselves
        and their persona + task plan has been built.
        """
        if not self.is_available():
            logger.info("[EmailSender dry-run] onboarding_started — SMTP not configured.")
            return False

        profile = state.employee_profile
        persona = state.matched_persona.persona if state.matched_persona else None
        name = profile.name if profile else "New Hire"
        role = persona.title if persona else (
            f"{getattr(profile, 'role_family', 'Developer')} "
            f"{getattr(profile, 'experience_level', '')}"
        ).strip()
        stack = ", ".join(profile.tech_stack) if profile and profile.tech_stack else "—"
        manager = persona.manager_name if persona else "—"
        manager_email = persona.manager_email if persona else None
        total = len(state.task_plan)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        subject = f"[OnboardAI] New hire onboarding started — {name}"
        html = _html_shell(
            subject,
            f"""
<p>Hi HR Team,</p>
<p>A new hire has just started their onboarding journey via OnboardAI.</p>
<table style="border-collapse:collapse;width:100%">
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Name</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{name}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Role</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{role}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Tech Stack</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{stack}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Manager</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{manager}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Tasks planned</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{total}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Started at</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{now}</td></tr>
</table>
<p>The agent will send progress and completion emails automatically as onboarding proceeds.</p>
<p style="color:#6b7280;font-size:0.85rem">— OnboardAI · Autonomous Developer Onboarding</p>
""",
        )

        recipients = [self.hr_email]
        if manager_email and manager_email != self.hr_email:
            recipients.append(manager_email)

        return self._send(subject, html, recipients)

    def send_progress_report(
        self,
        summary: "CompletionSummary",
        state: "OnboardingState",
        html_path: Path | None = None,
    ) -> bool:
        """
        Progress / milestone email sent when the engineering milestone is reached.
        Attaches the generated HTML report.
        """
        if not self.is_available():
            logger.info("[EmailSender dry-run] progress_report — SMTP not configured.")
            return False

        name = summary.employee_name
        role = summary.role
        done = len(summary.completed_items)
        total = done + len(summary.pending_items) + len(summary.skipped_items)
        pct = round(done / max(total, 1) * 100)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        completed_rows = "\n".join(
            f'<tr><td style="padding:6px;border:1px solid #ddd">✓ {t.task_id}</td>'
            f'<td style="padding:6px;border:1px solid #ddd">{t.title}</td></tr>'
            for t in summary.completed_items[:10]
        )
        subject = f"[OnboardAI] Progress update — {name} ({pct}% complete)"
        html = _html_shell(
            subject,
            f"""
<p>Hi {summary.manager_name or 'Team'},</p>
<p><strong>{name}</strong> has hit the <em>Engineering Milestone</em> in their onboarding as <strong>{role}</strong>.</p>
<table style="border-collapse:collapse;width:100%">
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Progress</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{pct}% ({done} tasks done)</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Pending</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{len(summary.pending_items)} tasks remaining</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Generated at</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{now}</td></tr>
</table>
<h3>Completed tasks</h3>
<table style="border-collapse:collapse;width:100%">{completed_rows}</table>
<p style="color:#6b7280;font-size:0.85rem">— OnboardAI · Autonomous Developer Onboarding</p>
""",
        )

        recipients = [self.hr_email]
        if summary.manager_email and summary.manager_email != self.hr_email:
            recipients.append(summary.manager_email)

        return self._send(subject, html, recipients, attachment_path=html_path)

    def send_completion_report(
        self,
        summary: "CompletionSummary",
        state: "OnboardingState",
        html_path: Path | None = None,
    ) -> bool:
        """
        Final HR completion email with full report attached.
        Sent to HR + manager + mentor.
        """
        if not self.is_available():
            logger.info("[EmailSender dry-run] completion_report — SMTP not configured.")
            return False

        name = summary.employee_name
        role = summary.role
        team = summary.team
        score = summary.score
        done = len(summary.completed_items)
        skipped = len(summary.skipped_items)
        pending = len(summary.pending_items)
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        ticket_id = (summary.starter_ticket or {}).get("Ticket ID", "N/A")

        method_map = {v.task_id: v.method for v in summary.verification_log}
        completed_rows = "\n".join(
            f'<tr>'
            f'<td style="padding:6px;border:1px solid #ddd">✓ {t.task_id}</td>'
            f'<td style="padding:6px;border:1px solid #ddd">{t.title}</td>'
            f'<td style="padding:6px;border:1px solid #ddd;color:#16a34a">'
            f'{"Skipped" if method_map.get(t.task_id) == "skipped_as_done" else "Completed"}'
            f'</td></tr>'
            for t in summary.completed_items[:15]
        )

        subject = f"[OnboardAI] Onboarding COMPLETE — {name} | Score {score}%"
        html = _html_shell(
            subject,
            f"""
<p>Hi HR Team,</p>
<p>🎉 <strong>{name}</strong> has <strong>completed onboarding</strong> as <em>{role}</em> in the <strong>{team}</strong> team.</p>
<table style="border-collapse:collapse;width:100%">
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Completion Score</strong></td>
      <td style="padding:8px;border:1px solid #ddd;color:#16a34a;font-weight:bold">{score}%</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Tasks Completed</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{done}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Tasks Skipped</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{skipped}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Pending</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{pending}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Manager</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{summary.manager_name or "—"} ({summary.manager_email or "—"})</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Mentor</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{summary.mentor_name or "—"} ({summary.mentor_email or "—"})</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Starter Ticket</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{ticket_id}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Completed at</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{now}</td></tr>
</table>
<p>The full HTML report is attached to this email.</p>
<p style="color:#6b7280;font-size:0.85rem">— OnboardAI · Autonomous Developer Onboarding</p>
""",
        )

        recipients = [self.hr_email]
        for addr in (summary.manager_email, summary.mentor_email):
            if addr and addr not in recipients:
                recipients.append(addr)

        return self._send(subject, html, recipients, attachment_path=html_path)

    def send_hire_completion_email(
        self,
        summary: "CompletionSummary",
        state: "OnboardingState",
        html_path: "Path | None" = None,
    ) -> bool:
        """
        Personal congratulations email sent directly to the new hire
        when all onboarding tasks are resolved.
        """
        if not self.is_available():
            logger.info("[EmailSender dry-run] hire_completion — SMTP not configured.")
            return False

        hire_email = (
            (state.employee_profile.email if state.employee_profile else None)
            or (summary.manager_email and None)  # fallback: skip if no hire email
        )
        hire_email = (
            state.employee_profile.email
            if state.employee_profile and state.employee_profile.email
            else None
        )
        if not hire_email:
            logger.info("[EmailSender] hire_completion skipped — no hire email in profile.")
            return False

        name = summary.employee_name
        role = summary.role
        team = summary.team
        score = summary.score
        done = len(summary.completed_items)
        ticket_id = (summary.starter_ticket or {}).get("Ticket ID", "")
        ticket_url = (summary.starter_ticket or {}).get("Resolved Tracking URL") or (
            summary.starter_ticket or {}
        ).get("Tracking URL", "")
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        ticket_line = (
            f'<p>🎫 Your starter ticket: <a href="{ticket_url}">{ticket_id}</a> — this is your first real task. Get stuck in!</p>'
            if ticket_id
            else ""
        )

        subject = f"🎉 You've completed onboarding at NovaByte — {name}!"
        html = _html_shell(
            subject,
            f"""
<p>Hi <strong>{name}</strong>,</p>
<p>Congratulations! You have successfully completed your onboarding as <strong>{role}</strong>
in the <strong>{team}</strong> team at NovaByte Technologies. 🚀</p>
<table style="border-collapse:collapse;width:100%">
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Score</strong></td>
      <td style="padding:8px;border:1px solid #ddd;color:#16a34a;font-weight:bold">{score}%</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Tasks Completed</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{done}</td></tr>
  <tr><td style="padding:8px;border:1px solid #ddd"><strong>Completed at</strong></td>
      <td style="padding:8px;border:1px solid #ddd">{now}</td></tr>
</table>
{ticket_line}
<p>Your HR report has been sent to your team. You're all set — welcome aboard! 🎊</p>
<p style="color:#6b7280;font-size:0.85rem">— OnboardAI · Autonomous Developer Onboarding</p>
""",
        )
        return self._send(subject, html, [hire_email], attachment_path=html_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _send(
        self,
        subject: str,
        html_body: str,
        recipients: list[str],
        attachment_path: Path | None = None,
    ) -> bool:
        msg = MIMEMultipart("alternative") if attachment_path is None else MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.user}>"
        msg["To"] = ", ".join(recipients)

        html_part = MIMEText(html_body, "html", "utf-8")
        if attachment_path is None:
            msg.attach(html_part)
        else:
            body_wrap = MIMEMultipart("alternative")
            body_wrap.attach(html_part)
            msg.attach(body_wrap)
            if Path(attachment_path).exists():
                with open(attachment_path, "rb") as f:
                    from email.mime.base import MIMEBase
                    from email import encoders
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(f.read())
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f'attachment; filename="{Path(attachment_path).name}"',
                    )
                    msg.attach(part)

        try:
            context = ssl.create_default_context()
            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                server.ehlo()
                server.starttls(context=context)
                server.login(self.user, self.password)
                server.sendmail(self.user, recipients, msg.as_string())
            logger.info("Email sent: '%s' → %s", subject, recipients)
            return True
        except Exception as exc:
            logger.warning("Email send failed: %s", exc)
            return False


def _html_shell(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>{title}</title>
  <style>
    body{{font-family:Arial,sans-serif;background:#f9fafb;color:#111827;margin:0;padding:20px}}
    .card{{background:#fff;border-radius:12px;padding:28px 32px;max-width:680px;margin:0 auto;
           box-shadow:0 4px 16px rgba(0,0,0,.08);border:1px solid #e5e7eb}}
    h2{{color:#1d4ed8;margin-top:0}}
    table{{border-collapse:collapse;width:100%;margin-top:12px}}
    td,th{{padding:8px 12px;border:1px solid #e5e7eb;font-size:.9rem}}
    th{{background:#f3f4f6}}
  </style>
</head>
<body>
  <div class="card">
    <h2>🤖 OnboardAI Notification</h2>
    {body}
  </div>
</body>
</html>"""
