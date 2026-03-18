from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.error
import urllib.request
from pathlib import Path

from onboardai.config import AppConfig, load_config
from onboardai.content.parser import parse_starter_tickets
from onboardai.models import IntegrationResult, OnboardingState


class JiraAdapter:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        self.base_url = self.config.jira_url.rstrip("/")
        self.cloud_id = self.config.atlassian_cloud_id
        self.email = self.config.atlassian_email
        self.api_token = self.config.atlassian_api_token
        self.project_key = self.config.jira_project_key

    def is_available(self) -> bool:
        return bool(self.api_token and self.base_url and (self.email or self.cloud_id))

    def auth_mode(self) -> str:
        if self.email and self.api_token:
            return "basic_user_token"
        if self.cloud_id and self.api_token:
            return "bearer_service_token"
        if self.api_token:
            return "token_missing_identity"
        return "unconfigured"

    def execute(self, task_title: str, state: OnboardingState) -> IntegrationResult:
        if self.is_available():
            starter_ticket = state.selected_starter_ticket or {}
            tracking_url = starter_ticket.get("Tracking URL")
            issue_key = self.issue_key_from_url(tracking_url) if tracking_url else None
            issue_visible = self.issue_exists(issue_key) if issue_key else None
            project_key = self.resolve_project_key()
            detail_parts = [f"Jira project={project_key or 'unresolved'}"]
            if issue_key:
                detail_parts.append(f"issue `{issue_key}` accessible={issue_visible}")
            return IntegrationResult(
                success=bool(project_key) and (issue_visible if issue_visible is not None else True),
                status="available" if project_key else "blocked",
                detail=". ".join(detail_parts),
            )
        return self.dry_run(task_title, state)

    def dry_run(self, task_title: str, state: OnboardingState) -> IntegrationResult:
        return IntegrationResult(
            success=True,
            status="queued",
            detail=f"Jira action '{task_title}' is queued for manual completion or demo mode.",
        )

    def project_exists(self, project_key: str | None = None) -> bool:
        if not self.is_available():
            return False
        key = project_key or self.project_key
        payload = self._request(f"/project/{key}")
        return payload is not None and "key" in payload

    def issue_url(self, issue_key: str | None) -> str | None:
        if not issue_key:
            return None
        return f"{self.base_url}/browse/{issue_key}"

    def issue_exists(self, issue_key: str | None) -> bool:
        if not self.is_available() or not issue_key:
            return False
        payload = self._request(f"/issue/{issue_key}")
        return payload is not None and payload.get("key") == issue_key

    def resolve_tracking_url(self, starter_ticket: dict[str, str] | None) -> str | None:
        if not starter_ticket:
            return None
        issue_key = self.resolve_issue_key(starter_ticket)
        if issue_key:
            return self.issue_url(issue_key)
        return starter_ticket.get("Tracking URL")

    @staticmethod
    def issue_key_from_url(url: str | None) -> str | None:
        if not url:
            return None
        parsed = urllib.parse.urlparse(url)
        if "/browse/" not in parsed.path:
            return None
        return parsed.path.rsplit("/", 1)[-1] or None

    def accessible_projects(self) -> list[dict]:
        if not self.is_available():
            return []
        payload = self._request("/project/search")
        if not payload:
            return []
        return payload.get("values", [])

    def resolve_project_key(self, preferred_key: str | None = None) -> str | None:
        preferred = preferred_key or self.project_key
        if preferred and self.project_exists(preferred):
            return preferred
        projects = self.accessible_projects()
        if len(projects) == 1:
            return projects[0].get("key")
        return None

    def resolve_issue_key(self, starter_ticket: dict[str, str] | None) -> str | None:
        if not starter_ticket:
            return None
        target_project_key = self.resolve_project_key()
        if target_project_key:
            existing_issue = self._find_existing_issue(starter_ticket, target_project_key)
            if existing_issue:
                return existing_issue
        fallback = self.issue_key_from_url(starter_ticket.get("Tracking URL"))
        if fallback and self.issue_exists(fallback):
            return fallback
        return fallback

    def seed_starter_issues(
        self,
        starter_ticket_path: str | Path,
        *,
        project_key: str | None = None,
    ) -> IntegrationResult:
        if not self.is_available():
            return IntegrationResult(
                success=False,
                status="unconfigured",
                detail="Jira API is not configured. Set ONBOARDAI_ATLASSIAN_API_TOKEN and cloud ID.",
            )
        target_project_key = self.resolve_project_key(project_key)
        if not target_project_key:
            visible_keys = ", ".join(project.get("key", "?") for project in self.accessible_projects()) or "none"
            return IntegrationResult(
                success=False,
                status="blocked",
                detail=(
                    f"Jira project '{project_key or self.project_key}' does not exist yet. "
                    f"Visible projects: {visible_keys}."
                ),
            )

        created_keys: list[str] = []
        existing_keys: list[str] = []
        failures: list[str] = []
        for ticket in parse_starter_tickets(starter_ticket_path).values():
            dataset_issue_id = ticket["Ticket ID"]
            existing_issue = self._find_existing_issue(ticket, target_project_key)
            if existing_issue:
                existing_keys.append(existing_issue)
                continue
            body = {
                "fields": {
                    "project": {"key": target_project_key},
                    "summary": f"{dataset_issue_id}: {ticket['Title']}",
                    "issuetype": {"name": "Task"},
                    "description": self._build_description(ticket),
                }
            }
            payload = self._request("/issue", method="POST", body=body)
            if payload and payload.get("key"):
                created_keys.append(payload["key"])
            else:
                failures.append(dataset_issue_id)

        success = not failures
        detail_parts = []
        if created_keys:
            detail_parts.append(f"Created: {', '.join(created_keys)}")
        if existing_keys:
            detail_parts.append(f"Already present: {', '.join(existing_keys)}")
        if failures:
            detail_parts.append(f"Failed: {', '.join(failures)}")
        return IntegrationResult(
            success=success,
            status="seeded" if success else "partial_failure",
            detail=". ".join(detail_parts) or "No starter issues were created.",
        )

    # ------------------------------------------------------------------
    # User management
    # ------------------------------------------------------------------

    def find_user_by_email(self, email: str) -> dict | None:
        """
        Search for a Jira Cloud user by email address.
        Tries multiple endpoints since Jira Cloud permissions vary.
        Returns the user object (with accountId) or None.
        """
        if not self.is_available() or not email:
            return None
        # Primary: /user/search?query=email (works for most Jira Cloud instances)
        payload = self._request(
            f"/user/search?query={urllib.parse.quote(email)}&maxResults=5"
        )
        if isinstance(payload, list):
            for user in payload:
                if user and (
                    (user.get("emailAddress") or "").lower() == email.lower()
                    or (user.get("name") or "").lower() == email.lower()
                ):
                    return user
            if payload and payload[0]:
                return payload[0]

        # Fallback: /user/search?accountSearch (some cloud instances need this)
        payload2 = self._request(
            f"/user/search?accountSearch=true&query={urllib.parse.quote(email)}&maxResults=5"
        )
        if isinstance(payload2, list) and payload2:
            return payload2[0]

        # Last resort: /myself (returns the API token owner — use for self-assignment)
        me = self._request("/myself")
        if me and (me.get("emailAddress") or "").lower() == email.lower():
            return me
        return None

    def get_current_user(self) -> dict | None:
        """Return the user profile for the API token's owner."""
        return self._request("/myself")

    # ------------------------------------------------------------------
    # Issue operations
    # ------------------------------------------------------------------

    def get_issue(self, issue_key: str) -> dict | None:
        """Fetch full issue details."""
        if not issue_key:
            return None
        return self._request(f"/issue/{issue_key}")

    def assign_issue(self, issue_key: str, account_id: str) -> IntegrationResult:
        """
        Assign a Jira issue to a user by accountId.
        Uses PUT /issue/{key}/assignee.
        """
        if not self.is_available():
            return IntegrationResult(
                success=False,
                status="unconfigured",
                detail="Jira API not configured.",
            )
        result = self._request(
            f"/issue/{issue_key}/assignee",
            method="PUT",
            body={"accountId": account_id},
        )
        # 204 → success (comes back as empty dict from our helper)
        if result is not None:
            return IntegrationResult(
                success=True,
                status="assigned",
                detail=f"Issue {issue_key} assigned to accountId={account_id}.",
            )
        return IntegrationResult(
            success=False,
            status="api_error",
            detail=f"Failed to assign {issue_key} (check permissions).",
        )

    def get_transitions(self, issue_key: str) -> list[dict]:
        """Return available transitions for an issue."""
        if not self.is_available():
            return []
        payload = self._request(f"/issue/{issue_key}/transitions")
        if payload:
            return payload.get("transitions", [])
        return []

    def transition_issue(self, issue_key: str, target_name: str) -> IntegrationResult:
        """
        Move an issue to the transition whose name contains target_name (case-insensitive).
        Common names: "In Progress", "To Do", "Done".
        """
        if not self.is_available():
            return IntegrationResult(success=False, status="unconfigured", detail="Jira API not configured.")

        transitions = self.get_transitions(issue_key)
        match = next(
            (t for t in transitions if target_name.lower() in t.get("name", "").lower()),
            None,
        )
        if not match:
            available = ", ".join(t.get("name", "?") for t in transitions)
            return IntegrationResult(
                success=False,
                status="no_transition",
                detail=f"No transition matching '{target_name}' found. Available: {available or 'none'}",
            )

        result = self._request(
            f"/issue/{issue_key}/transitions",
            method="POST",
            body={"transition": {"id": match["id"]}},
        )
        if result is not None:
            return IntegrationResult(
                success=True,
                status="transitioned",
                detail=f"Issue {issue_key} transitioned to '{match['name']}'.",
            )
        return IntegrationResult(
            success=False,
            status="api_error",
            detail=f"Transition to '{target_name}' failed for {issue_key}.",
        )

    def add_comment(self, issue_key: str, comment_text: str) -> IntegrationResult:
        """
        Add a plain-text comment to an issue using Atlassian Document Format (ADF).
        """
        if not self.is_available():
            return IntegrationResult(success=False, status="unconfigured", detail="Jira not configured.")

        body = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": comment_text}],
                    }
                ],
            }
        }
        payload = self._request(f"/issue/{issue_key}/comment", method="POST", body=body)
        if payload and payload.get("id"):
            return IntegrationResult(
                success=True,
                status="commented",
                detail=f"Comment added to {issue_key} (id={payload['id']}).",
            )
        return IntegrationResult(
            success=False,
            status="api_error",
            detail=f"Failed to add comment to {issue_key}.",
        )

    def assign_and_start_starter_ticket(
        self, state: "OnboardingState"
    ) -> IntegrationResult:
        """
        Full workflow for the 'Pick up starter ticket' task:
        1. Find the issue key from state.selected_starter_ticket
        2. Look up the new hire in Jira by email
        3. Assign the issue to them
        4. Transition to 'In Progress'
        5. Add a welcome comment
        Returns a summary IntegrationResult.
        """
        if not self.is_available():
            return IntegrationResult(
                success=False,
                status="unconfigured",
                detail="Jira API not configured.",
            )

        starter_ticket = state.selected_starter_ticket or {}
        issue_key = self.resolve_issue_key(starter_ticket)
        if not issue_key:
            return IntegrationResult(
                success=False,
                status="no_issue",
                detail="No starter ticket issue key found — run seed_starter_issues first.",
            )

        email = None
        name = "New Hire"
        if state.employee_profile:
            email = state.employee_profile.email
            name = state.employee_profile.name
        if not email and state.matched_persona:
            email = state.matched_persona.persona.email
            name = state.matched_persona.persona.name

        steps: list[str] = []

        # 1. Assign
        if email:
            user = self.find_user_by_email(email)
            if user and user.get("accountId"):
                assign_result = self.assign_issue(issue_key, user["accountId"])
                steps.append(assign_result.detail)
            else:
                steps.append(f"Could not find Jira user for {email} — skipping assignment.")
        else:
            steps.append("No email — skipping assignment.")

        # 2. Transition to In Progress
        trans_result = self.transition_issue(issue_key, "In Progress")
        steps.append(trans_result.detail)

        # 3. Welcome comment
        ticket_title = starter_ticket.get("Title", issue_key)
        comment_text = (
            f"Hi {name}! This is your starter ticket: *{ticket_title}*. "
            f"It was assigned automatically by the OnboardAI onboarding agent. "
            f"Good luck, and don't hesitate to ask your mentor for guidance. :rocket:"
        )
        comment_result = self.add_comment(issue_key, comment_text)
        steps.append(comment_result.detail)

        issue_url = self.issue_url(issue_key)
        return IntegrationResult(
            success=True,
            status="starter_ticket_started",
            detail=(
                f"Starter ticket {issue_key} is ready for {name}. "
                f"URL: {issue_url}. "
                + " | ".join(steps)
            ),
        )

    def _find_existing_issue(self, ticket: dict[str, str], project_key: str) -> str | None:
        dataset_issue_id = ticket["Ticket ID"]
        if dataset_issue_id.startswith(f"{project_key}-"):
            payload = self._request(f"/issue/{dataset_issue_id}")
            if payload and payload.get("key") == dataset_issue_id:
                return dataset_issue_id
        jql = (
            f'project = "{project_key}" AND summary ~ "\\"{dataset_issue_id}\\"" '
            f'ORDER BY created DESC'
        )
        payload = self._request(f"/search/jql?maxResults=1&fields=summary&jql={urllib.parse.quote(jql)}")
        issues = (payload or {}).get("issues", [])
        if issues:
            return issues[0].get("key")
        return None

    def _build_description(self, ticket: dict[str, str]) -> dict:
        lines = [
            f"Persona: {ticket['Persona']}",
            f"Repository: {ticket['Repo']}",
            f"Repository URL: {ticket['Repo URL']}",
            "",
            ticket["Description"],
        ]
        content = []
        for line in lines:
            if line:
                content.append(
                    {
                        "type": "paragraph",
                        "content": [
                            {
                                "type": "text",
                                "text": line,
                            }
                        ],
                    }
                )
            else:
                content.append({"type": "paragraph", "content": []})
        return {
            "type": "doc",
            "version": 1,
            "content": content,
        }

    def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: dict | None = None,
    ) -> dict | None:
        if not self.is_available():
            return None
        data = None if body is None else json.dumps(body).encode("utf-8")
        last_error_status = None
        for url, headers in self._request_attempts(path):
            request = urllib.request.Request(
                url,
                data=data,
                headers=headers,
                method=method,
            )
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    raw = response.read()
                    if not raw:
                        return {}  # 204 No Content → success with empty body
                    return json.loads(raw.decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error_status = exc.code
                if exc.code in {401, 403, 404}:
                    continue
                return None
            except Exception:
                continue
        if last_error_status is not None:
            return None
        return None

    def _request_attempts(self, path: str) -> list[tuple[str, dict[str, str]]]:
        headers = self._headers()
        attempts: list[tuple[str, dict[str, str]]] = []
        if self.cloud_id:
            attempts.append(
                (
                    f"https://api.atlassian.com/ex/jira/{self.cloud_id}/rest/api/3{path}",
                    headers,
                )
            )
        attempts.append((f"{self.base_url}/rest/api/3{path}", headers))
        return attempts

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "onboardai-setup",
        }
        if self.email:
            token = base64.b64encode(f"{self.email}:{self.api_token}".encode("utf-8")).decode("ascii")
            headers["Authorization"] = f"Basic {token}"
        else:
            headers["Authorization"] = f"Bearer {self.api_token}"
        return headers
