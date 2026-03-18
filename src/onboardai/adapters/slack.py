from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from onboardai.models import CompletionKind, IntegrationResult, TaskStatus

if TYPE_CHECKING:
    from onboardai.models import ChecklistTask, CompletionSummary, OnboardingState

logger = logging.getLogger(__name__)

_PHASE_EMOJI = {
    "get_access": ":key:",
    "get_coding": ":computer:",
    "learn_system": ":books:",
    "admin_compliance": ":clipboard:",
}

_STATUS_EMOJI = {
    TaskStatus.COMPLETED: ":white_check_mark:",
    TaskStatus.SKIPPED: ":fast_forward:",
    TaskStatus.IN_PROGRESS: ":hourglass_flowing_sand:",
    TaskStatus.BLOCKED: ":x:",
}

# Default mandatory channels every new hire joins
DEFAULT_ONBOARDING_CHANNELS = ["engineering-general", "new-joiners"]


def _channel_id(channel: str) -> str:
    """Strip leading # so the SDK accepts both forms."""
    return channel.lstrip("#")


class SlackAdapter:
    def __init__(self, bot_token: str | None = None, channel: str = "#onboarding") -> None:
        self.bot_token = bot_token or os.getenv("SLACK_BOT_TOKEN")
        self.channel = channel
        self._client = None
        self._channel_cache: dict[str, str] = {}  # name → channel_id

    # ------------------------------------------------------------------
    # Client
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(self.bot_token)

    def client(self):
        if self._client is None:
            try:
                from slack_sdk import WebClient  # type: ignore
                self._client = WebClient(token=self.bot_token)
            except ImportError:
                logger.warning("slack-sdk not installed; Slack notifications disabled.")
                return None
        return self._client

    # ------------------------------------------------------------------
    # User lookup
    # ------------------------------------------------------------------

    def lookup_user_by_email(self, email: str) -> str | None:
        """
        Return the Slack member ID (U...) for the given email address.
        Requires `users:read.email` bot scope.
        Returns None if not found or on error.
        """
        if not self.is_available() or not email:
            return None
        client = self.client()
        if client is None:
            return None
        try:
            resp = client.users_lookupByEmail(email=email)
            return resp["user"]["id"]
        except Exception as exc:
            logger.debug("Slack users.lookupByEmail(%s) failed: %s", email, exc)
            return None

    # ------------------------------------------------------------------
    # Channel operations
    # ------------------------------------------------------------------

    def _resolve_channel_id(self, channel_name: str) -> str | None:
        """
        Resolve a channel name to its Slack channel ID.
        Uses pre-seeded cache (populated by seed_channel_id) or falls back to name directly.
        Full channel listing requires `channels:read` scope; we work without it by using
        the channel name directly (Slack also accepts names for public channels in most APIs).
        """
        name = _channel_id(channel_name)
        return self._channel_cache.get(name)

    def seed_channel_id(self, channel_name: str, channel_id: str) -> None:
        """Pre-populate the cache with a known channel name → ID mapping."""
        self._channel_cache[_channel_id(channel_name)] = channel_id

    def invite_user_to_channel(self, slack_user_id: str, channel_name: str) -> IntegrationResult:
        """
        Invite a user to a Slack channel by channel name.
        Requires `channels:manage` (public) or `groups:write` (private) bot scope,
        and the bot must already be in the channel.
        """
        if not self.is_available():
            return self._dry_run_plain(f"invite to #{channel_name}")

        channel_id = self._resolve_channel_id(channel_name)
        if not channel_id:
            # Try joining by name directly as fallback
            channel_id = _channel_id(channel_name)

        client = self.client()
        if client is None:
            return IntegrationResult(success=False, status="unavailable", detail="slack-sdk not installed.")
        try:
            resp = client.conversations_invite(channel=channel_id, users=slack_user_id)
            ch_name = resp.get("channel", {}).get("name", channel_name)
            return IntegrationResult(
                success=True,
                status="joined",
                detail=f"User invited to #{ch_name}.",
            )
        except Exception as exc:
            err = str(exc)
            # already_in_channel is not a failure
            if "already_in_channel" in err:
                return IntegrationResult(
                    success=True,
                    status="already_member",
                    detail=f"User is already in #{channel_name}.",
                )
            logger.debug("Slack conversations.invite to #%s failed: %s", channel_name, exc)
            return IntegrationResult(success=False, status="error", detail=err)

    def invite_user_to_workspace(self, email: str) -> IntegrationResult:
        """
        Invite a new user to the Slack workspace by email.
        Uses the undocumented users.admin.invite endpoint — works for most
        standard (non-Enterprise) Slack workspaces with a bot token.
        Falls back to a shareable invite link message if the endpoint is blocked.
        """
        if not self.is_available():
            return self._dry_run_plain(f"workspace_invite:{email}")

        client = self.client()
        if client is None:
            return IntegrationResult(success=False, status="unavailable", detail="slack-sdk not installed.")

        # Attempt undocumented users.admin.invite (legacy — widely supported)
        try:
            resp = client.api_call(
                "users.admin.invite",
                params={"email": email, "set_active": "true"},
            )
            if resp.get("ok"):
                return IntegrationResult(
                    success=True,
                    status="workspace_invited",
                    detail=f"Slack workspace invitation sent to {email}.",
                )
            err = resp.get("error", "unknown_error")
            if err == "already_in_team":
                return IntegrationResult(
                    success=True,
                    status="already_in_workspace",
                    detail=f"{email} is already a member of this workspace.",
                )
            if err in {"paid_teams_only", "not_authed", "invalid_auth", "account_inactive"}:
                # Fall through to shareable link approach
                logger.debug("users.admin.invite blocked (%s) — trying invite link", err)
        except Exception as exc:
            logger.debug("users.admin.invite call failed: %s", exc)

        # Fallback: generate a shareable invite link the user can send manually
        try:
            resp2 = client.api_call("conversations.inviteShared", json={"emails": [email]})
            if resp2.get("ok"):
                invite_link = resp2.get("invite_link", "")
                return IntegrationResult(
                    success=True,
                    status="invite_link_generated",
                    detail=f"Share this invite link with {email}: {invite_link}",
                )
        except Exception:
            pass

        return IntegrationResult(
            success=False,
            status="invite_not_sent",
            detail=(
                f"Could not auto-invite {email} to Slack workspace "
                f"(bot may lack admin permissions). "
                f"Please invite manually via Slack Settings → Invite People."
            ),
        )

    def join_channels_for_new_hire(self, state: "OnboardingState") -> IntegrationResult:
        """
        Look up the new hire in Slack by email and invite them to all
        mandatory onboarding channels.
        Returns a summary IntegrationResult.
        """
        if not self.is_available():
            return self._dry_run("slack_channels", state)

        email = None
        if state.employee_profile:
            email = state.employee_profile.email
        if not email and state.matched_persona:
            email = state.matched_persona.persona.email

        if not email:
            return IntegrationResult(
                success=False,
                status="no_email",
                detail=(
                    "No email address found for this hire — "
                    "cannot auto-invite to Slack channels. "
                    "Please have them manually join #engineering-general and #new-joiners."
                ),
            )

        # Step 0: Ensure the user is in the workspace first
        ws_result = self.invite_user_to_workspace(email)
        logger.info("Workspace invite for %s: %s", email, ws_result.detail)

        slack_user_id = self.lookup_user_by_email(email)
        if not slack_user_id:
            return IntegrationResult(
                success=False,
                status="user_not_found",
                detail=(
                    f"No Slack account found for {email}. "
                    "They may need to accept the Slack workspace invitation first, "
                    "then use /invite in #engineering-general and #new-joiners."
                ),
            )

        squad = None
        if state.matched_persona:
            squad = state.matched_persona.persona.team
        channels = list(DEFAULT_ONBOARDING_CHANNELS)
        if squad:
            channels.append(f"team-{squad.lower().replace(' ', '-')}")

        joined, failed = [], []
        for ch in channels:
            result = self.invite_user_to_channel(slack_user_id, ch)
            if result.success:
                joined.append(f"#{ch}")
            else:
                failed.append(f"#{ch} ({result.detail})")

        self.send_dm_welcome(slack_user_id, state)

        if failed:
            return IntegrationResult(
                success=bool(joined),
                status="partial",
                detail=(
                    f"Joined: {', '.join(joined)}. "
                    f"Could not join: {', '.join(failed)}."
                ),
            )
        return IntegrationResult(
            success=True,
            status="channels_joined",
            detail=f"New hire invited to: {', '.join(joined)}. Welcome DM sent.",
        )

    def send_dm_welcome(self, slack_user_id: str, state: "OnboardingState") -> None:
        """Send a personal welcome DM to the new hire."""
        if not self.is_available():
            return
        client = self.client()
        if client is None:
            return
        name = state.employee_profile.name if state.employee_profile else "there"
        persona = state.matched_persona.persona if state.matched_persona else None
        role = persona.title if persona else "the team"
        try:
            client.chat_postMessage(
                channel=slack_user_id,
                text=(
                    f":wave: Welcome to NovaByte, *{name}*!\n\n"
                    f"I'm the OnboardAI bot. You've been added to the team channels as *{role}*.\n"
                    f"Your onboarding checklist is running — I'll update <#{_channel_id(self.channel)}> "
                    f"as you complete each step.\n\n"
                    f"You can always ask your mentor or check <#{_channel_id(self.channel)}> "
                    f"for live progress updates. Good luck! :rocket:"
                ),
            )
        except Exception as exc:
            logger.debug("Slack DM welcome failed: %s", exc)

    # ------------------------------------------------------------------
    # Onboarding channel notifications
    # ------------------------------------------------------------------

    def send_welcome_message(self, state: "OnboardingState") -> IntegrationResult:
        """Post a welcome banner when a new hire starts onboarding."""
        if not self.is_available():
            return self._dry_run("welcome", state)

        profile = state.employee_profile
        persona = state.matched_persona.persona if state.matched_persona else None
        name = profile.name if profile else "New Hire"
        title = persona.title if persona else (
            f"{getattr(profile, 'role_family', 'Developer')} "
            f"{getattr(profile, 'experience_level', '')}"
        )
        stack = ", ".join(profile.tech_stack) if profile and profile.tech_stack else "—"
        first_task = next(
            (t for t in state.task_plan if t.status == TaskStatus.NOT_STARTED),
            None,
        )
        first_task_text = (
            f"`{first_task.task_id}` {first_task.title}" if first_task else "Getting started"
        )

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f":wave: New hire started onboarding — {name}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Role:*\n{title}"},
                    {"type": "mrkdwn", "text": f"*Tech Stack:*\n{stack}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":clipboard: *{len(state.task_plan)} tasks* planned · "
                        f"First step: {first_task_text}"
                    ),
                },
            },
            {"type": "divider"},
        ]
        return self._post(blocks, f"New hire {name} started onboarding as {title}.")

    def send_task_update(self, task: "ChecklistTask", state: "OnboardingState") -> IntegrationResult:
        """Post a task status update (completed / skipped / blocked)."""
        if not self.is_available():
            return self._dry_run(f"task_update:{task.task_id}", state)

        name = state.employee_profile.name if state.employee_profile else "New Hire"
        status_emoji = _STATUS_EMOJI.get(task.status, ":grey_question:")
        phase_emoji = _PHASE_EMOJI.get(task.display_phase.value, ":pushpin:")
        completed_count = sum(1 for t in state.task_plan if t.status == TaskStatus.COMPLETED)
        total = len(state.task_plan)
        pct = round(completed_count / total * 100) if total else 0
        bar_filled = round(pct / 10)
        progress_bar = (
            ":large_green_square:" * bar_filled + ":white_square_button:" * (10 - bar_filled)
        )
        status_label = task.status.value.replace("_", " ").title()

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"{status_emoji} *{name}* — {status_label}: "
                        f"{phase_emoji} `{task.task_id}` {task.title}"
                    ),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"{progress_bar}  *{pct}%*  ({completed_count}/{total} tasks) · "
                            f"Phase: {task.display_phase.value.replace('_', ' ').title()} · "
                            f"{datetime.now(timezone.utc).strftime('%H:%M UTC')}"
                        ),
                    }
                ],
            },
        ]
        return self._post(blocks, f"{name}: {status_label} — {task.task_id} {task.title} ({pct}%)")

    def send_milestone_notification(self, state: "OnboardingState") -> IntegrationResult:
        """Post engineering milestone reached notification."""
        if not self.is_available():
            return self._dry_run("milestone", state)

        name = state.employee_profile.name if state.employee_profile else "New Hire"
        persona = state.matched_persona.persona if state.matched_persona else None
        title = persona.title if persona else "Developer"
        completed_count = sum(1 for t in state.task_plan if t.status == TaskStatus.COMPLETED)
        total = len(state.task_plan)
        pct = round(completed_count / total * 100) if total else 0

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f":trophy: Engineering milestone reached — {name}"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":dart: *{name}* ({title}) has completed all engineering setup steps "
                        f"and run the first service!\n"
                        f"Environment verified · Repo cloned · Service running · "
                        f"Docs reviewed · Starter ticket assigned"
                    ),
                },
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": (
                            f"Progress: *{pct}%* ({completed_count}/{total} tasks) · "
                            f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                        ),
                    }
                ],
            },
            {"type": "divider"},
        ]
        return self._post(blocks, f":trophy: {name} hit the engineering milestone ({pct}% complete).")

    def send_completion_summary(
        self, summary: "CompletionSummary", state: "OnboardingState"
    ) -> IntegrationResult:
        """Post final onboarding completion summary to the channel."""
        if not self.is_available():
            return self._dry_run("completion", state)

        name = summary.employee_name
        role = summary.role
        team = summary.team
        done = len(summary.completed_items)
        skipped = len(summary.skipped_items)
        pending = len(summary.pending_items)
        score = summary.score

        completed_titles = "\n".join(
            f"> :white_check_mark: `{t.task_id}` {t.title}"
            for t in summary.completed_items[:12]
        )
        if len(summary.completed_items) > 12:
            completed_titles += f"\n> _…and {len(summary.completed_items) - 12} more_"

        pending_text = (
            "\n".join(
                f"> :hourglass_flowing_sand: `{t.task_id}` {t.title}"
                for t in summary.pending_items
            )
            if summary.pending_items
            else "> _None — fully complete!_"
        )

        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": f":tada: Onboarding complete — {name}"},
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Role:*\n{role}"},
                    {"type": "mrkdwn", "text": f"*Team:*\n{team}"},
                    {"type": "mrkdwn", "text": f"*Score:*\n{score}%"},
                    {"type": "mrkdwn", "text": f"*Completed:*\n{done} tasks"},
                ],
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":white_check_mark: *Completed tasks ({done})*\n{completed_titles}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":clipboard: *Pending / not started ({pending})*\n{pending_text}"
                    ),
                },
            },
        ]
        if skipped:
            blocks.append({
                "type": "context",
                "elements": [{"type": "mrkdwn", "text": f":fast_forward: {skipped} task(s) skipped"}],
            })
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        f"HR completion report generated · "
                        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"
                    ),
                }
            ],
        })

        return self._post(blocks, f":tada: {name} completed onboarding as {role} — score {score}%.")

    def post_integration_result(
        self,
        task_title: str,
        result: IntegrationResult,
        state: "OnboardingState",
    ) -> None:
        """Post a brief integration result note to the channel (non-blocking)."""
        if not self.is_available():
            return
        name = state.employee_profile.name if state.employee_profile else "New Hire"
        icon = ":white_check_mark:" if result.success else ":warning:"
        try:
            self._post(
                [
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": (
                                    f"{icon} *{name}* · {task_title} · "
                                    f"`{result.status}` — {result.detail}"
                                ),
                            }
                        ],
                    }
                ],
                f"{name}: {task_title} — {result.status}",
            )
        except Exception as exc:
            logger.debug("post_integration_result failed: %s", exc)

    # Legacy entry-point kept for backward compatibility
    def execute(self, task_title: str, state: "OnboardingState") -> IntegrationResult:
        if self.is_available():
            return IntegrationResult(
                success=True,
                status="available",
                detail=f"Slack adapter configured for task '{task_title}'.",
            )
        return self._dry_run(task_title, state)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_bot_in_channel(self, channel_name: str) -> None:
        """Auto-join the channel if the bot is not already a member."""
        client = self.client()
        if client is None:
            return
        ch_id = self._resolve_channel_id(channel_name)
        if not ch_id:
            ch_id = _channel_id(channel_name)
        try:
            client.conversations_join(channel=ch_id)
        except Exception:
            pass  # Already a member or private channel — silently ignore

    def _post(self, blocks: list, fallback_text: str) -> IntegrationResult:
        client = self.client()
        if client is None:
            return IntegrationResult(
                success=False, status="unavailable", detail="slack-sdk not installed."
            )
        try:
            resp = client.chat_postMessage(
                channel=_channel_id(self.channel),
                text=fallback_text,
                blocks=blocks,
            )
            ts = resp.get("ts", "")
            return IntegrationResult(
                success=True,
                status="sent",
                detail=f"Message posted to {self.channel} (ts={ts}).",
            )
        except Exception as exc:
            logger.warning("Slack post failed: %s", exc)
            return IntegrationResult(success=False, status="error", detail=str(exc))

    def _dry_run(self, event: str, state: "OnboardingState") -> IntegrationResult:
        name = state.employee_profile.name if state.employee_profile else "unknown"
        logger.info(
            "[Slack dry-run] event=%s employee=%s channel=%s", event, name, self.channel
        )
        return IntegrationResult(
            success=True,
            status="dry_run",
            detail=(
                f"Slack not configured — '{event}' notification for {name} "
                f"queued (dry run)."
            ),
        )

    def _dry_run_plain(self, event: str) -> IntegrationResult:
        logger.info("[Slack dry-run] event=%s", event)
        return IntegrationResult(
            success=True,
            status="dry_run",
            detail=f"Slack not configured — '{event}' queued (dry run).",
        )
