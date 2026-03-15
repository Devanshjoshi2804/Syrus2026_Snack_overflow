from __future__ import annotations

import base64

from onboardai.adapters.github import GitHubAdapter
from onboardai.adapters.jira import JiraAdapter
from onboardai.config import AppConfig
from onboardai.graph import OnboardingEngine
from onboardai.models import TaskAction
from onboardai.ui.dashboard import build_dashboard_props


def test_github_adapter_validates_org_and_repo(monkeypatch, project_root):
    config = AppConfig(
        project_root=project_root,
        github_token="test-token",
        github_org_url="https://github.com/NovaByte-Technologies",
    )
    adapter = GitHubAdapter(config)

    def fake_request(path: str):
        if path == "/orgs/NovaByte-Technologies":
            return {"login": "NovaByte-Technologies"}
        if path == "/repos/NovaByte-Technologies/connector-runtime-demo":
            return {"name": "connector-runtime-demo"}
        if path.startswith("/orgs/NovaByte-Technologies/repos"):
            return [{"name": "connector-runtime-demo"}]
        return None

    monkeypatch.setattr(adapter, "_request", fake_request)
    assert adapter.org_accessible() is True
    assert adapter.repo_exists("connector-runtime-demo") is True


def test_workspace_surfaces_agent_browser_proof_and_milestone_progress(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root, browser_backend="mock"))
    state = engine.new_state()
    engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    engine.task_action_router_node(state, TaskAction.SELF_COMPLETE)
    engine.task_action_router_node(state, TaskAction.SELF_COMPLETE)
    engine.task_action_router_node(state, TaskAction.WATCH_AGENT)

    props = build_dashboard_props(state)
    assert props["latestProof"] is not None
    assert "Opened https://app.slack.com/client/T0AMFTZAN8G" in props["latestProof"]
    assert props["milestoneProgress"]["completed"] >= 1


def test_jira_adapter_uses_basic_auth_when_email_is_configured(project_root):
    config = AppConfig(
        project_root=project_root,
        jira_url="https://novabytetechnologies.atlassian.net",
        atlassian_email="riya@novabyte.dev",
        atlassian_api_token="token-123",
        atlassian_cloud_id="cloud-123",
    )
    adapter = JiraAdapter(config)

    headers = adapter._headers()
    expected = base64.b64encode(b"riya@novabyte.dev:token-123").decode("ascii")

    assert headers["Authorization"] == f"Basic {expected}"
    assert adapter.auth_mode() == "basic_user_token"
    assert adapter._request_attempts("/project/search")[0][0] == (
        "https://api.atlassian.com/ex/jira/cloud-123/rest/api/3/project/search"
    )


def test_jira_adapter_falls_back_to_site_url_with_bearer_without_email(project_root):
    config = AppConfig(
        project_root=project_root,
        jira_url="https://novabytetechnologies.atlassian.net",
        atlassian_email=None,
        atlassian_api_token="token-123",
        atlassian_cloud_id="cloud-123",
    )
    adapter = JiraAdapter(config)

    headers = adapter._headers()
    attempts = adapter._request_attempts("/project/search")

    assert headers["Authorization"] == "Bearer token-123"
    assert adapter.auth_mode() == "bearer_service_token"
    assert attempts[0][0] == "https://api.atlassian.com/ex/jira/cloud-123/rest/api/3/project/search"
    assert attempts[1][0] == "https://novabytetechnologies.atlassian.net/rest/api/3/project/search"


def test_jira_adapter_resolves_real_tracking_url_from_visible_project(project_root, monkeypatch):
    config = AppConfig(
        project_root=project_root,
        jira_url="https://novabytetechnologies.atlassian.net",
        atlassian_email="riya@novabyte.dev",
        atlassian_api_token="token-123",
        atlassian_cloud_id="cloud-123",
        jira_project_key="FLOW",
    )
    adapter = JiraAdapter(config)
    starter_ticket = {
        "Ticket ID": "FLOW-INTERN-001",
        "Title": "Fix null check in connector handler",
        "Tracking URL": "https://novabytetechnologies.atlassian.net/browse/FLOW-INTERN-001",
    }

    monkeypatch.setattr(adapter, "resolve_project_key", lambda preferred_key=None: "BTS")
    monkeypatch.setattr(adapter, "_find_existing_issue", lambda ticket, project_key: "BTS-7")

    assert adapter.resolve_tracking_url(starter_ticket) == "https://novabytetechnologies.atlassian.net/browse/BTS-7"


def test_jira_adapter_builds_adf_description(project_root):
    config = AppConfig(project_root=project_root)
    adapter = JiraAdapter(config)
    ticket = {
        "Persona": "backend intern",
        "Repo": "connector-runtime-demo",
        "Repo URL": "https://github.com/NovaByte-Technologies/connector-runtime-demo",
        "Description": "Add a missing null guard in the connector runtime request handler.",
    }

    description = adapter._build_description(ticket)

    assert description["type"] == "doc"
    assert description["version"] == 1
    flattened = [node["content"][0]["text"] for node in description["content"] if node.get("content")]
    assert "Persona: backend intern" in flattened
    assert "Repository: connector-runtime-demo" in flattened


def test_dashboard_surfaces_live_targets_from_resolved_starter_ticket(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root, browser_backend="mock"))
    state = engine.new_state()
    engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    state.selected_starter_ticket = {
        "Ticket ID": "FLOW-INTERN-001",
        "Resolved Ticket ID": "BTS-7",
        "Resolved Project Key": "BTS",
        "Resolved Tracking URL": "https://novabytetechnologies.atlassian.net/browse/BTS-7",
        "Repo": "connector-runtime-demo",
        "Repo URL": "https://github.com/NovaByte-Technologies/connector-runtime-demo",
    }
    state.current_task_id = "C-07"

    props = build_dashboard_props(state)

    assert props["liveTargets"]["jiraProjectKey"] == "BTS"
    assert props["liveTargets"]["starterTicketId"] == "BTS-7"
    assert any("NovaByte-Technologies" in line for line in props["stepTargets"])


def test_dashboard_surfaces_agent_terminal_transcript(project_root):
    engine = OnboardingEngine(AppConfig(project_root=project_root, browser_backend="mock"))
    state = engine.new_state()
    engine.handle_message(
        state,
        "Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
    )
    for _ in range(4):
        engine.task_action_router_node(state, TaskAction.SELF_COMPLETE)
    engine.task_action_router_node(state, TaskAction.WATCH_AGENT)

    props = build_dashboard_props(state)

    assert props["latestTranscript"] is not None
    assert "$" in props["latestTranscript"]
    assert "node --version" in props["latestTranscript"]
