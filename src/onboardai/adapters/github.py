from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

from onboardai.config import AppConfig, load_config
from onboardai.models import IntegrationResult, OnboardingState


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

    def _request(self, path: str):
        if not self.is_available():
            return None
        request = urllib.request.Request(
            f"https://api.github.com{path}",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "onboardai-setup",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError:
            return None
        except Exception:
            return None
