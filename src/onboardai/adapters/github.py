from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from onboardai.config import AppConfig, load_config
from onboardai.models import IntegrationResult, OnboardingState

logger = logging.getLogger(__name__)


class GitHubAdapter:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        self.token = self.config.github_token
        self.org_url = self.config.github_org_url.rstrip("/")
        self.org_slug = self.org_url.rstrip("/").split("/")[-1]

    def is_available(self) -> bool:
        return bool(self.token)

    def execute(self, task_title: str, state: OnboardingState) -> IntegrationResult:
        starter_ticket = state.selected_starter_ticket or {}
        repo_url = starter_ticket.get("Repo URL")
        repo_name = starter_ticket.get("Repo")
        if not self.is_available():
            return self.dry_run(task_title, state)
        org_visible = self.org_accessible()
        repo_visible = self.repo_exists(repo_name) if repo_name else None
        detail_parts = [f"GitHub org `{self.org_slug}` accessible={org_visible}"]
        if repo_name:
            detail_parts.append(f"repo `{repo_name}` accessible={repo_visible}")
        if repo_url:
            detail_parts.append(f"url={repo_url}")
        return IntegrationResult(
            success=org_visible and (repo_visible if repo_visible is not None else True),
            status="available" if org_visible else "blocked",
            detail=". ".join(detail_parts),
        )

    def dry_run(self, task_title: str, state: OnboardingState) -> IntegrationResult:
        return IntegrationResult(
            success=True,
            status="queued",
            detail=f"GitHub action '{task_title}' is queued for manual completion or demo mode.",
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def org_accessible(self) -> bool:
        payload = self._request(f"/orgs/{self.org_slug}")
        return payload is not None and payload.get("login", "").lower() == self.org_slug.lower()

    def repo_exists(self, repo_name: str | None) -> bool:
        if not repo_name:
            return False
        payload = self._request(f"/repos/{self.org_slug}/{repo_name}")
        return payload is not None and payload.get("name", "").lower() == repo_name.lower()

    def accessible_repos(self, limit: int = 20) -> list[dict]:
        payload = self._request(f"/orgs/{self.org_slug}/repos?per_page={limit}")
        if isinstance(payload, list):
            return payload
        return []

    def resolve_repo_url(self, repo_name: str) -> str:
        return f"{self.org_url}/{repo_name}"

    def is_org_member(self, username: str) -> bool:
        """Check whether a GitHub username is already a member of the org."""
        if not self.is_available() or not username:
            return False
        payload = self._request(f"/orgs/{self.org_slug}/members/{username}")
        # 204 No Content → member, 404 → not member (both come back as None with our helper)
        # We check via membership endpoint instead
        membership = self._request(f"/orgs/{self.org_slug}/memberships/{username}")
        if membership and membership.get("state") in {"active", "pending"}:
            return True
        return False

    def get_pending_invitations(self) -> list[dict]:
        """Return list of pending org invitations."""
        if not self.is_available():
            return []
        payload = self._request(f"/orgs/{self.org_slug}/invitations?per_page=100")
        if isinstance(payload, list):
            return payload
        return []

    def invitation_exists_for_email(self, email: str) -> bool:
        """Return True if an invitation is already pending for this email."""
        email_lower = email.lower()
        for inv in self.get_pending_invitations():
            if (inv.get("email") or "").lower() == email_lower:
                return True
        return False

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def invite_user_to_org(self, email: str, role: str = "direct_member") -> IntegrationResult:
        """
        Send a GitHub org invitation to the new hire.
        Requires the token to have `admin:org` scope.
        Falls back to a browser URL if permissions are insufficient.
        """
        if not self.is_available():
            return IntegrationResult(
                success=False,
                status="unconfigured",
                detail="GITHUB_TOKEN not set — cannot send org invitation.",
            )

        # Check if already invited / already a member
        if self.invitation_exists_for_email(email):
            invite_url = f"https://github.com/orgs/{self.org_slug}/invitations"
            return IntegrationResult(
                success=True,
                status="already_invited",
                detail=f"Invitation already pending for {email}. View at {invite_url}",
            )

        body = {"email": email, "role": role}
        payload = self._request(
            f"/orgs/{self.org_slug}/invitations",
            method="POST",
            body=body,
        )

        if payload and payload.get("id"):
            invite_url = f"https://github.com/orgs/{self.org_slug}/invitations"
            return IntegrationResult(
                success=True,
                status="invited",
                detail=(
                    f"GitHub org invite sent to {email} "
                    f"(invitation id={payload['id']}). "
                    f"They must accept at {invite_url}"
                ),
            )

        # If we got a 422 it's likely the email is already a GitHub user with a pending invite
        # or we lack admin:org scope — provide the manual URL as fallback
        invite_manage_url = f"https://github.com/orgs/{self.org_slug}/people"
        logger.warning("GitHub org invite API call failed for %s", email)
        return IntegrationResult(
            success=False,
            status="api_error",
            detail=(
                f"Could not auto-send GitHub invite for {email} via API "
                f"(token may lack `admin:org` scope). "
                f"Manually invite at: {invite_manage_url}"
            ),
        )

    def create_repo_for_hire(
        self,
        repo_name: str,
        *,
        private: bool = True,
        description: str = "",
    ) -> IntegrationResult:
        """Create a new repository under the org (used for starter projects)."""
        if not self.is_available():
            return self.dry_run("create_repo", None)  # type: ignore[arg-type]
        existing = self._request(f"/repos/{self.org_slug}/{repo_name}")
        if existing and existing.get("name"):
            return IntegrationResult(
                success=True,
                status="already_exists",
                detail=f"Repo {self.org_slug}/{repo_name} already exists: {existing.get('html_url')}",
            )
        body = {"name": repo_name, "private": private, "description": description}
        payload = self._request(f"/orgs/{self.org_slug}/repos", method="POST", body=body)
        if payload and payload.get("html_url"):
            return IntegrationResult(
                success=True,
                status="created",
                detail=f"Repository created: {payload['html_url']}",
            )
        return IntegrationResult(
            success=False,
            status="api_error",
            detail=f"Failed to create repo {repo_name} under {self.org_slug}.",
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _request(self, path: str, *, method: str = "GET", body: dict | None = None):
        if not self.is_available():
            return None
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.github.com{path}",
            data=data,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "Content-Type": "application/json",
                "User-Agent": "onboardai-setup",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read()
                if not raw:
                    return {}
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            logger.debug("GitHub API %s %s → HTTP %s", method, path, exc.code)
            try:
                body_text = exc.read().decode("utf-8")
                logger.debug("GitHub error body: %s", body_text)
            except Exception:
                pass
            return None
        except Exception as exc:
            logger.debug("GitHub API request failed: %s", exc)
            return None
