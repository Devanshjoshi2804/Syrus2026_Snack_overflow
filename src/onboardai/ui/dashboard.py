from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from onboardai.models import (
    AutomationMode,
    GuidedStepView,
    OnboardingState,
    TaskAction,
    TaskPhase,
    TaskStatus,
)
from onboardai.state import get_current_task


AGENT_AUTOMATION_MODES = {AutomationMode.AGENT_TERMINAL, AutomationMode.AGENT_BROWSER}
PHASE_LABELS = {
    TaskPhase.GET_ACCESS: "Phase 1: Get Access",
    TaskPhase.GET_CODING: "Phase 2: Get Coding",
    TaskPhase.LEARN_SYSTEM: "Phase 3: Learn the System",
    TaskPhase.ADMIN_COMPLIANCE: "Phase 4: Finish Admin & Compliance",
}


def _available_actions(task) -> list[str]:
    if not task:
        return []
    if task.automation_mode in AGENT_AUTOMATION_MODES:
        return [TaskAction.WATCH_AGENT.value, TaskAction.SELF_COMPLETE.value, TaskAction.SKIP.value]
    return [TaskAction.SELF_COMPLETE.value, TaskAction.SKIP.value]


def _next_agent_task(state: OnboardingState):
    current_index = 0
    if state.current_task_id:
        for index, task in enumerate(state.task_plan):
            if task.task_id == state.current_task_id:
                current_index = index
                break
    for task in state.task_plan[current_index + 1:]:
        if task.status in {TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS} and task.automation_mode in AGENT_AUTOMATION_MODES:
            return task
    return None


def _health_hint(health: dict[str, str], current_task, next_agent_task) -> str | None:
    browser_ready = (health.get("browser_ready") or "").lower()
    if browser_ready == "no":
        relevant_browser_task = (
            (current_task and current_task.automation_mode == AutomationMode.AGENT_BROWSER)
            or (next_agent_task and next_agent_task.automation_mode == AutomationMode.AGENT_BROWSER)
        )
        if relevant_browser_task:
            sandbox_backend = (health.get("sandbox_backend") or "").lower()
            if "localshellsandboxmanager" in sandbox_backend or sandbox_backend == "local":
                return "Playwright screenshots are unavailable. Browser steps will still open in your local browser. Run `playwright install chromium` if you want in-app browser capture."
            return "Browser automation is unavailable. Run `playwright install chromium` and restart the app."
    return None


def _usable_stream_url(state: OnboardingState) -> str | None:
    stream_url = state.dashboard_state.stream_url
    if not stream_url:
        return None
    if state.sandbox_session and state.sandbox_session.backend == "mock":
        return None
    if "example.invalid" in stream_url:
        return None
    return stream_url


def _step_ordinal(state: OnboardingState, current_task) -> int | None:
    if not current_task:
        return None
    for index, task in enumerate(state.task_plan, start=1):
        if task.task_id == current_task.task_id:
            return index
    return None


def _phase_counts(state: OnboardingState) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = {}
    for phase in TaskPhase:
        phase_tasks = [task for task in state.task_plan if task.display_phase == phase]
        resolved = sum(
            task.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}
            for task in phase_tasks
        )
        counts[phase.value] = {
            "total": len(phase_tasks),
            "resolved": int(resolved),
        }
    return counts


def _action_labels(current_task) -> dict[str, str]:
    if not current_task:
        return {
            "explain_task": "Explain this step",
            "show_full_checklist": "Show full checklist",
            TaskAction.WATCH_AGENT.value: "Run agent for me",
            TaskAction.SELF_COMPLETE.value: "I finished this",
            TaskAction.SKIP.value: "Skip for now",
        }
    title = current_task.title.lower()
    complete_label = "I finished this"
    if "laptop" in title:
        complete_label = "I have the laptop"
    elif "google workspace" in title:
        complete_label = "I activated it"
    elif "slack" in title:
        complete_label = "I joined Slack"
    elif "github organization invite" in title:
        complete_label = "I accepted GitHub"
    elif "1password" in title:
        complete_label = "1Password is ready"
    elif "mfa" in title:
        complete_label = "MFA is enabled"
    elif "vpn" in title:
        complete_label = "VPN is set up"
    elif "node.js" in title:
        complete_label = "Node is installed"
    elif "pnpm" in title:
        complete_label = "pnpm is installed"
    elif "git identity" in title or ("git" in title and "config" in title):
        complete_label = "Git is configured"
    elif "clone" in title:
        complete_label = "Repo is cloned"
    elif "start the service" in title or "start development server" in title:
        complete_label = "It runs locally"
    elif "unit tests" in title or "test suite" in title:
        complete_label = "Tests pass"
    elif "starter ticket" in title:
        complete_label = "Ticket is opened"
    elif "vpn" in title:
        complete_label = "VPN is set up"
    return {
        "explain_task": "Explain this step",
        "show_full_checklist": "Show full checklist",
        TaskAction.WATCH_AGENT.value: "Run agent for me",
        TaskAction.SELF_COMPLETE.value: complete_label,
        TaskAction.SKIP.value: "Skip for now",
    }


def _upcoming_tasks(state: OnboardingState, limit: int = 4) -> list[dict]:
    items = []
    current_seen = False
    for index, task in enumerate(state.task_plan, start=1):
        if task.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}:
            continue
        if not state.current_task_id or task.task_id == state.current_task_id:
            current_seen = True
        if not current_seen:
            continue
        items.append(
            {
                "index": index,
                "taskId": task.task_id,
                "title": task.title,
                "automation": task.automation_mode.value,
                "status": task.status.value,
                "phase": task.display_phase.value,
            }
        )
        if len(items) >= limit:
            break
    return items


def _source_citations(state: OnboardingState) -> list[str]:
    return [
        f"{Path(hit.chunk.source_path).name}: {hit.chunk.title}"
        for hit in state.knowledge_hits[:2]
    ]


def _selected_ticket(state: OnboardingState) -> dict[str, str]:
    return state.selected_starter_ticket or {}


def _machine_panel(state: OnboardingState) -> dict[str, str]:
    session = state.sandbox_session
    metadata = session.metadata if session else {}
    return {
        "backend": session.backend if session else "unknown",
        "sessionId": session.session_id if session else "none",
        "workDir": metadata.get("work_dir", ""),
        "homeDir": metadata.get("home_dir", ""),
        "lastUrl": metadata.get("last_url", ""),
        "lastCommand": metadata.get("last_command", ""),
        "lastOutput": metadata.get("last_output", ""),
        "lastTranscript": metadata.get("last_transcript", ""),
        "lastArtifacts": metadata.get("last_artifacts", []),
        "files": _machine_files(metadata.get("work_dir", "")),
        "browserMode": (
            "playwright"
            if (state.dashboard_state.health.get("browser_ready") or "").lower() == "yes"
            else "system-browser"
        ),
    }


def _machine_files(work_dir: str, limit: int = 6) -> list[str]:
    if not work_dir:
        return []
    path = Path(work_dir)
    if not path.exists():
        return []
    items: list[str] = []
    for entry in sorted(path.iterdir(), key=lambda item: item.name.lower()):
        label = entry.name + ("/" if entry.is_dir() else "")
        items.append(label)
        if len(items) >= limit:
            break
    return items


def _github_org_url(state: OnboardingState) -> str | None:
    ticket = _selected_ticket(state)
    repo_url = ticket.get("Repo URL")
    if not repo_url:
        return None
    parsed = urlparse(repo_url)
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 1:
        return f"{parsed.scheme}://{parsed.netloc}/{parts[0]}"
    return None


def _github_org_label(state: OnboardingState) -> str | None:
    org_url = _github_org_url(state)
    if not org_url:
        return None
    return org_url.rstrip("/").rsplit("/", 1)[-1]


def _jira_base_url(state: OnboardingState) -> str | None:
    ticket = _selected_ticket(state)
    tracking_url = ticket.get("Resolved Tracking URL") or ticket.get("Tracking URL")
    if not tracking_url:
        return None
    parsed = urlparse(tracking_url)
    return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else None


def _live_targets(state: OnboardingState) -> dict[str, str]:
    ticket = _selected_ticket(state)
    return {
        "githubOrgLabel": _github_org_label(state) or "",
        "githubOrgUrl": _github_org_url(state) or "",
        "jiraProjectKey": state.dashboard_state.health.get("jira_resolved_project", "") or ticket.get("Resolved Project Key", ""),
        "jiraBaseUrl": _jira_base_url(state) or "",
        "starterTicketId": ticket.get("Resolved Ticket ID") or ticket.get("Ticket ID", ""),
        "starterTicketUrl": ticket.get("Resolved Tracking URL") or ticket.get("Tracking URL", ""),
        "starterRepo": ticket.get("Repo", ""),
        "starterRepoUrl": ticket.get("Repo URL", ""),
    }


def _time_estimate(task) -> str:
    if not task:
        return "~5 min"
    title = task.title.lower()
    if "laptop" in title:
        return "~2 min"
    if "google workspace" in title or "slack" in title:
        return "~5 min"
    if "1password" in title or "mfa" in title or "vpn" in title:
        return "~10 min"
    if "github" in title or "jira" in title or "notion" in title:
        return "~5 min"
    if "node.js" in title or "python 3.11" in title or "poetry" in title:
        return "~10 min"
    if "pnpm" in title or "git identity" in title or "git config" in title:
        return "~5 min"
    if "clone" in title:
        return "~5 min"
    if "docker compose" in title or "start the service" in title or "start development server" in title:
        return "~10 min"
    if "migrations" in title:
        return "~5 min"
    if "unit tests" in title or "test suite" in title:
        return "~5 min"
    if "architecture" in title or "api standards" in title or "pr guidelines" in title or "branching" in title:
        return "~15 min"
    if "engineering standards" in title or "company overview" in title:
        return "~20 min"
    if "security" in title or "gdpr" in title or "code of conduct" in title or "compliance" in title:
        return "~20 min"
    if "nda" in title or "handbook" in title or "acceptable use" in title or "ip assignment" in title:
        return "~10 min"
    if "bamboohR" in title or "expensify" in title or "payroll" in title:
        return "~10 min"
    if "starter ticket" in title:
        return "~10 min"
    if "git workflow" in title:
        return "~10 min"
    return "~10 min"


def _escalation_contact(task) -> str:
    if not task:
        return "Contact your manager or IT: it@novabyte.dev"
    title = task.title.lower()
    category = (task.category or "").lower()
    if "laptop" in title or "it setup" in category:
        return "IT helpdesk: it@novabyte.dev · Slack #it-help"
    if "google workspace" in title:
        return "IT helpdesk: it@novabyte.dev · if invite missing, ask IT"
    if "slack" in title:
        return "HR: hr@novabyte.dev · or ask your manager"
    if "github" in title:
        return "Manager or mentor · Slack #engineering-general"
    if "jira" in title or "atlassian" in title:
        return "Engineering manager · tanvi.s@novabyte.dev"
    if "1password" in title or "mfa" in title or "vpn" in title:
        return "IT helpdesk: it@novabyte.dev"
    if "nda" in title or "handbook" in title or "ip assignment" in title or "legal" in title:
        return "HR: hr@novabyte.dev"
    if "compliance" in title or "gdpr" in title or "security" in title or "code of conduct" in title:
        return "HR: hr@novabyte.dev"
    if "bamboohR" in title or "payroll" in title or "expensify" in title:
        return "HR: hr@novabyte.dev"
    if any(kw in title for kw in ("node", "pnpm", "python", "poetry", "docker", "clone", "git", "terraform", "kubectl", "helm")):
        return "Mentor or #engineering-general on Slack"
    return "Manager or mentor · Slack #engineering-general"


def _blocked_hint(task) -> str | None:
    if not task:
        return None
    title = task.title.lower()
    if "google workspace" in title:
        return "If the invite email hasn't arrived, contact IT at it@novabyte.dev — it usually takes 15–30 min."
    if "slack" in title:
        return "If you can't sign in, try SSO with your NovaByte Google account. Ask IT if the workspace invite is missing."
    if "github organization invite" in title:
        return "If the invite hasn't arrived, ask your manager or ping #engineering-general. GitHub invites sometimes go to spam."
    if "jira workspace invite" in title:
        return "If the invite is missing, contact tanvi.s@novabyte.dev. Jira invites can take up to an hour."
    if "1password" in title:
        return "If you didn't receive a 1Password invite, contact IT at it@novabyte.dev."
    if "mfa" in title:
        return "Use Google Authenticator or Authy. If you're locked out, contact IT immediately."
    if "vpn" in title:
        return "Download WireGuard and ask IT for the config file if you don't have it. Never share the VPN config."
    if "laptop" in title:
        return "If your laptop hasn't arrived yet, contact IT at it@novabyte.dev. You can skip this and return later."
    if "node.js" in title or "pnpm" in title or "python" in title or "poetry" in title:
        return "If a command fails, paste the error in #engineering-general or ask your mentor. Type $ <command> here to run it directly."
    if "clone" in title:
        return "If the clone fails with permission denied, make sure you accepted the GitHub org invite first."
    if "docker compose" in title:
        return "If Docker isn't installed, download Docker Desktop from docker.com. Ask your mentor if it fails to start."
    return None


def _step_targets(state: OnboardingState, current_task) -> list[str]:
    if not current_task:
        return []
    targets = _live_targets(state)
    title = current_task.title.lower()
    lines: list[str] = []
    if "github" in title and targets["githubOrgLabel"]:
        lines.append(f"GitHub org: [{targets['githubOrgLabel']}]({targets['githubOrgUrl']})")
    if "slack" in title:
        slack_base = state.dashboard_state.health.get("slack_workspace_url", "").rstrip("/")
        if slack_base:
            lines.append(f"Slack workspace: [{slack_base}]({slack_base})")
            lines.append(f"Join [#engineering-general]({slack_base}/channels/engineering-general)")
            lines.append(f"Join [#new-joiners]({slack_base}/channels/new-joiners)")
    if "jira" in title and targets["jiraBaseUrl"]:
        project = targets["jiraProjectKey"] or "configured project"
        lines.append(f"Jira project: `{project}` on [{targets['jiraBaseUrl']}]({targets['jiraBaseUrl']})")
    if (
        "clone" in title
        or "repository" in title
        or "starter ticket" in title
        or "git workflow" in title
        or "pr " in title
        or title.startswith("submit pr")
    ):
        if targets["starterRepo"]:
            lines.append(f"Repository: `{targets['starterRepo']}`")
        if targets["starterRepoUrl"]:
            lines.append(f"Repo URL: [{targets['starterRepoUrl']}]({targets['starterRepoUrl']})")
    if "starter ticket" in title and targets["starterTicketId"]:
        lines.append(f"Starter ticket: `{targets['starterTicketId']}`")
        if targets["starterTicketUrl"]:
            lines.append(f"Ticket URL: [{targets['starterTicketUrl']}]({targets['starterTicketUrl']})")
    return lines


def _latest_proof(state: OnboardingState) -> str | None:
    if not state.dashboard_state.items:
        return None
    latest = state.dashboard_state.items[-1]
    detail = f" -> {latest.detail}" if latest.detail else ""
    return f"{latest.task_id} {latest.title}{detail}"


def _latest_artifacts(state: OnboardingState) -> list[str]:
    if not state.dashboard_state.items:
        return []
    return state.dashboard_state.items[-1].artifacts[:3]


def _latest_transcript(state: OnboardingState) -> str | None:
    if not state.dashboard_state.items:
        return None
    transcript = state.dashboard_state.items[-1].transcript.strip()
    if not transcript:
        return None
    lines = transcript.splitlines()
    if len(lines) > 18:
        lines = ["..."] + lines[-18:]
    return "\n".join(lines)


def _milestone_progress(state: OnboardingState) -> dict[str, int | bool]:
    target_tags = {"access", "environment", "repo", "service", "docs", "starter"}
    completed_tags = {
        task.milestone_tag
        for task in state.task_plan
        if task.status == TaskStatus.COMPLETED and task.milestone_tag in target_tags
    }
    return {
        "completed": len(completed_tags),
        "total": len(target_tags),
        "ready": completed_tags == target_tags,
    }


def _generic_steps(current_task, next_agent_task) -> list[str]:
    steps = [
        f"Open the system or repository needed for `{current_task.task_id}` {current_task.title}.",
        "Follow the dataset-backed instructions in order and verify the expected result.",
        "When the step is done, use the workspace action to resolve it and move on.",
    ]
    if current_task.automation_mode in AGENT_AUTOMATION_MODES:
        steps[1] = "Use Run agent for me if you want automation, or do it yourself and resolve the step after verification."
    elif next_agent_task:
        steps.append(f"Agent help starts at `{next_agent_task.task_id}` {next_agent_task.title}.")
    return steps


def _specific_guided_step(state: OnboardingState, current_task, next_agent_task) -> GuidedStepView | None:
    title = current_task.title.lower()
    citations = _source_citations(state)
    proof_status = _latest_proof(state)
    phase_label = PHASE_LABELS.get(current_task.display_phase, "Guided onboarding")
    targets = _live_targets(state)
    common_kwargs = {
        "source_citations": citations,
        "proof_status": proof_status,
        "time_estimate": _time_estimate(current_task),
        "escalation_contact": _escalation_contact(current_task),
        "blocked_hint": _blocked_hint(current_task),
    }

    if "1password" in title:
        return GuidedStepView(
            headline=f"{phase_label} · set up 1Password",
            summary="This secures your shared credentials before deeper engineering setup.",
            what_to_do_now=[
                "Open the 1Password invite from NovaByte and create your account.",
                "Sign in once and confirm you can open the company vault.",
                "When the vault opens successfully, finish the step in the workspace.",
            ],
            fastest_path="Open the invite, sign in, then click 1Password is ready.",
            why_it_matters="You will need company-managed credentials for repo access, secrets, and shared systems.",
            primary_actions=["Explain this step", "1Password is ready", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    if "github organization invite" in title:
        org_label = targets["githubOrgLabel"] or "NovaByte-Technologies"
        org_url = targets["githubOrgUrl"] or "https://github.com/NovaByte-Technologies"
        return GuidedStepView(
            headline=f"{phase_label} · accept the GitHub organization invite",
            summary=f"GitHub access is the last access gate before engineering setup begins. Your target org is `{org_label}`.",
            what_to_do_now=[
                f"Open the GitHub notification or invite email for `{org_label}`.",
                f"Accept the organization invite and confirm you can open `{org_url}`.",
                "If automation is available, use Run agent for me to open the org page directly.",
            ],
            fastest_path="Use Run agent for me or accept the invite manually, then click I accepted GitHub.",
            why_it_matters="The next steps require cloning repositories and viewing starter ticket context in GitHub.",
            primary_actions=["Explain this step", "Run agent for me", "I accepted GitHub", "Skip for now"],
            upcoming_steps=[],
            agent_available=True,
            agent_fallback_message="If browser automation is unavailable, accept the invite manually and then resolve the step.",
            **common_kwargs,
        )
    if "jira workspace invite" in title:
        jira_project = targets["jiraProjectKey"] or "your configured Jira project"
        jira_base = targets["jiraBaseUrl"] or "https://novabytetechnologies.atlassian.net"
        return GuidedStepView(
            headline=f"{phase_label} · accept the Jira workspace invite",
            summary=f"Jira is where starter tickets and ongoing engineering work are tracked. The current project target is `{jira_project}`.",
            what_to_do_now=[
                f"Open the Jira invitation from NovaByte Technologies and accept it.",
                f"Sign in once and confirm `{jira_base}` opens.",
                "You do not need to pick a ticket yet for this step, only confirm access.",
            ],
            fastest_path="Accept the invite, open Jira once, then mark the step done.",
            why_it_matters="Later onboarding steps reference the starter ticket in Jira.",
            primary_actions=["Explain this step", "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    if "notion workspace" in title:
        return GuidedStepView(
            headline=f"{phase_label} · open the Engineering knowledge workspace",
            summary="This gives you a persistent home for engineering notes, docs, and onboarding references.",
            what_to_do_now=[
                "Accept the Notion invite and open the Engineering space.",
                "Bookmark the engineering home page or star it for quick access.",
                "Return here and resolve the step once the workspace opens.",
            ],
            fastest_path="Open the Engineering space once and bookmark it, then click I finished this.",
            why_it_matters="A large part of day-to-day engineering context lives in shared documentation spaces.",
            primary_actions=["Explain this step", "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    if "vpn" in title:
        return GuidedStepView(
            headline=f"{phase_label} · set up the WireGuard VPN",
            summary="The VPN is usually needed before you can access internal dashboards and private engineering systems.",
            what_to_do_now=[
                "Install WireGuard if it is not already on the laptop.",
                "Import the NovaByte VPN configuration profile and connect once.",
                "Verify you can stay connected, then resolve the step.",
            ],
            fastest_path="Connect once successfully and click VPN is set up.",
            why_it_matters="Later systems such as internal docs, Storybook, and staging tools may require company network access.",
            primary_actions=["Explain this step", "VPN is set up", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    if "node.js" in title:
        return GuidedStepView(
            headline=f"{phase_label} · install Node.js 20",
            summary="This is the first real engineering environment step for the backend intern path.",
            what_to_do_now=[
                "Use Run agent for me to install Node.js 20 through nvm, or run the setup guide commands manually.",
                "Verify that `node --version` returns a `v20.x` version.",
                "Once the version check passes, resolve the step and continue to pnpm.",
            ],
            fastest_path="Use Run agent for me. The workspace will verify the Node version automatically.",
            why_it_matters="The connector runtime and local development scripts depend on Node.js 20.",
            primary_actions=["Explain this step", "Run agent for me", "Node is installed", "Skip for now"],
            upcoming_steps=[],
            agent_available=True,
            agent_fallback_message="If automation is unavailable, run the nvm commands from the setup guide and verify `node --version` yourself.",
            **common_kwargs,
        )
    if "pnpm" in title:
        return GuidedStepView(
            headline=f"{phase_label} · install pnpm and core tools",
            summary="pnpm is the package manager used by the JavaScript and TypeScript repositories.",
            what_to_do_now=[
                "Use Run agent for me to install pnpm, or install it manually from the setup guide.",
                "Verify that `pnpm --version` succeeds before moving on.",
                "After that, you can configure Git and clone the repo.",
            ],
            fastest_path="Use Run agent for me and let the workspace verify `pnpm --version`.",
            why_it_matters="You need pnpm before you can install dependencies or run the local app.",
            primary_actions=["Explain this step", "Run agent for me", "pnpm is installed", "Skip for now"],
            upcoming_steps=[],
            agent_available=True,
            agent_fallback_message="If automation is unavailable, install pnpm manually and verify the version before resolving the step.",
            **common_kwargs,
        )
    if "git identity" in title or ("git" in title and "config" in title):
        return GuidedStepView(
            headline=f"{phase_label} · configure Git for NovaByte work",
            summary="Set your Git name and NovaByte email before cloning or opening branches.",
            what_to_do_now=[
                "Use Run agent for me to set your Git identity, or run the git config commands manually.",
                "Verify that `git config --global user.email` shows your NovaByte email.",
                "Resolve the step once Git is configured correctly.",
            ],
            fastest_path="Use Run agent for me. The workspace will verify the Git email for you.",
            why_it_matters="Correct Git identity is required before commits, branches, and PRs.",
            primary_actions=["Explain this step", "Run agent for me", "Git is configured", "Skip for now"],
            upcoming_steps=[],
            agent_available=True,
            **common_kwargs,
        )
    if "clone" in title:
        repo_hint = targets["starterRepo"] or ("connector-runtime-demo" if "connector" in title else "flowengine-web-demo")
        repo_url = targets["starterRepoUrl"]
        return GuidedStepView(
            headline=f"{phase_label} · clone the working repository",
            summary=f"This step brings the assigned codebase onto your machine so the agent can verify a real developer setup. Expected repo: `{repo_hint}`.",
            what_to_do_now=[
                (
                    f"Use Run agent for me to clone `{repo_hint}` from `{repo_url}`, or run the clone command from the setup guide."
                    if repo_url
                    else "Use Run agent for me to clone the assigned repository, or run the clone command from the setup guide."
                ),
                "Confirm the repository folder exists locally and contains the expected project files.",
                "Resolve the step once the clone succeeds.",
            ],
            fastest_path="Use Run agent for me. The workspace will verify the cloned repository name.",
            why_it_matters="All local setup, docs review, and starter task work depends on having the repo checked out.",
            primary_actions=["Explain this step", "Run agent for me", "Repo is cloned", "Skip for now"],
            upcoming_steps=[],
            agent_available=True,
            **common_kwargs,
        )
    if ".env" in title or "local environment" in title:
        return GuidedStepView(
            headline=f"{phase_label} · set up local configuration",
            summary="Configure the local environment files and dependencies needed to boot the service.",
            what_to_do_now=[
                "Follow the repository's local environment setup instructions from the setup guide or README.",
                "Create the required environment file and fill only the documented development values.",
                "Resolve the step once the project is configured and ready to start.",
            ],
            fastest_path="Complete the local environment file setup, then click I finished this.",
            why_it_matters="The service cannot start without the expected local configuration values.",
            primary_actions=["Explain this step", "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    if "docker compose" in title:
        return GuidedStepView(
            headline=f"{phase_label} · start local dependencies with Docker Compose",
            summary="Bring up the local supporting services before running the app or migrations.",
            what_to_do_now=[
                "Use Run agent for me to run the Docker Compose check or start command, or do it manually in the repo.",
                "Confirm the local services are up and there are no blocking container errors.",
                "Resolve the step once the dependencies are available.",
            ],
            fastest_path="Use Run agent for me and let the workspace capture the Docker Compose proof.",
            why_it_matters="Databases and supporting services usually need to be running before the app can boot cleanly.",
            primary_actions=["Explain this step", "Run agent for me", "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=True,
            **common_kwargs,
        )
    if "migrations" in title or "seed data" in title:
        return GuidedStepView(
            headline=f"{phase_label} · run migrations and seed data",
            summary="Initialize the local database so the service has the expected schema and sample data.",
            what_to_do_now=[
                "Run the migration and seed commands documented for the repo.",
                "Watch for a clean success message and no schema errors.",
                "Resolve the step after the database is initialized successfully.",
            ],
            fastest_path="Run the documented migration/seed commands, confirm success, then click I finished this.",
            why_it_matters="The local service will usually fail or behave incorrectly if the database is not initialized.",
            primary_actions=["Explain this step", "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    if "start the service" in title or "start development server" in title:
        product = "service" if "service" in title else "development server"
        return GuidedStepView(
            headline=f"{phase_label} · run the local {product}",
            summary="This is the proof point that your engineering environment actually works.",
            what_to_do_now=[
                "Use Run agent for me to start the local app, or run the documented start command yourself.",
                "Confirm the app prints a local URL or a successful running message.",
                "Resolve the step after the app starts cleanly.",
            ],
            fastest_path="Use Run agent for me. The workspace will verify the local run output.",
            why_it_matters="Running the app locally is the main milestone before you move into docs review and the starter task.",
            primary_actions=["Explain this step", "Run agent for me", "It runs locally", "Skip for now"],
            upcoming_steps=[],
            agent_available=True,
            **common_kwargs,
        )
    if "unit tests" in title or "test suite" in title:
        return GuidedStepView(
            headline=f"{phase_label} · verify the test suite passes",
            summary="Use the project's basic tests to confirm the local setup is healthy.",
            what_to_do_now=[
                "Run the unit tests from the repository root.",
                "Verify the test command finishes cleanly with passing output.",
                "Resolve the step once the test suite is green.",
            ],
            fastest_path="Run the tests and click Tests pass when the command succeeds.",
            why_it_matters="Passing tests are a quick health check before you start making changes or pick up a ticket.",
            primary_actions=["Explain this step", "Tests pass", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    if "architecture documentation" in title or "architecture" in title:
        return GuidedStepView(
            headline=f"{phase_label} · review the relevant architecture section",
            summary="This is where you connect your local setup to the real system shape and repository responsibilities.",
            what_to_do_now=[
                "Read the architecture section that matches your role path.",
                "Focus on the repositories, services, and data flow mentioned for your team.",
                "Resolve the step once you understand which codebase you are working in and how it fits into the system.",
            ],
            fastest_path="Read the cited architecture section, then click I finished this.",
            why_it_matters="You should understand the system boundaries before you take a starter ticket.",
            primary_actions=["Explain this step", "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    if "api standards" in title:
        return GuidedStepView(
            headline=f"{phase_label} · read the API standards",
            summary="This step grounds your backend work in NovaByte's expected REST conventions and validation style.",
            what_to_do_now=[
                "Read the API Standards section in the engineering standards document.",
                "Pay attention to versioning, resource naming, status codes, and validation rules.",
                "Resolve the step once you understand how the project expects APIs to behave.",
            ],
            fastest_path="Open the cited standards section, skim the API rules, then click I finished this.",
            why_it_matters="Your starter backend task and future PRs should follow the same API conventions used across the company.",
            primary_actions=["Explain this step", "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    if "pr guidelines" in title:
        return GuidedStepView(
            headline=f"{phase_label} · review PR expectations",
            summary="This step teaches you how NovaByte expects engineering work to be submitted and reviewed.",
            what_to_do_now=[
                "Read the PR requirements and code review expectations in engineering standards.",
                "Notice the Jira ticket reference format and PR title pattern.",
                "Resolve the step once you understand how your first starter task should be submitted.",
            ],
            fastest_path="Read the PR guidelines, then click I finished this.",
            why_it_matters="The starter task is not complete until it follows the expected branch, PR, and review process.",
            primary_actions=["Explain this step", "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    if "branching strategy" in title or "git workflow practice" in title:
        ticket_id = targets["starterTicketId"] or "the starter ticket"
        return GuidedStepView(
            headline=f"{phase_label} · practice the Git workflow",
            summary=f"This simulates the exact flow you will use for the starter task: branch, commit, and PR. The live ticket reference is `{ticket_id}`.",
            what_to_do_now=[
                "Use Run agent for me to create a practice branch, or do it manually in a local repo.",
                f"Confirm the branch name follows the Jira-linked naming style and references `{ticket_id}` when appropriate.",
                "Resolve the step once the branch workflow is clear.",
            ],
            fastest_path="Use Run agent for me and let the workspace verify the branch name.",
            why_it_matters="You need the branch and PR workflow before you can complete the first real engineering ticket.",
            primary_actions=["Explain this step", "Run agent for me", "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=True,
            **common_kwargs,
        )
    if "starter ticket" in title:
        ticket_id = targets["starterTicketId"] or "your assigned starter ticket"
        ticket_url = targets["starterTicketUrl"]
        repo = targets["starterRepo"]
        return GuidedStepView(
            headline=f"{phase_label} · open the starter ticket",
            summary=(
                f"This is the first concrete engineering task for the onboarding path. "
                f"The live Jira issue is `{ticket_id}`{f' for `{repo}`' if repo else ''}."
            ),
            what_to_do_now=[
                (
                    f"Use Run agent for me to open `{ticket_url}`, or open it manually."
                    if ticket_url
                    else "Use Run agent for me to open the starter ticket tracking page, or open it manually."
                ),
                f"Read the ticket summary, repository, and expected scope before starting work.",
                "Resolve the step once the ticket is open and understood.",
            ],
            fastest_path="Use Run agent for me. The workspace will open the starter ticket URL.",
            why_it_matters="This bridges onboarding into actual engineering work and is the main milestone for the demo.",
            primary_actions=["Explain this step", "Run agent for me", "Ticket is opened", "Skip for now"],
            upcoming_steps=[],
            agent_available=True,
            **common_kwargs,
        )
    if "design system" in title or "ui-kit" in title:
        return GuidedStepView(
            headline=f"{phase_label} · review the design system",
            summary="This step grounds the frontend path in the shared UI kit and Storybook references.",
            what_to_do_now=[
                "Read the design system notes and inspect the UI kit references mentioned in the architecture docs.",
                "Focus on reusable components like Badge, Table, and Card since the starter ticket depends on them.",
                "Resolve the step once you know where shared components live.",
            ],
            fastest_path="Read the design system references, then click I finished this.",
            why_it_matters="Senior frontend onboarding should quickly connect you to the component system you will extend or review.",
            primary_actions=["Explain this step", "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    if "deployment standards" in title or "deployment health" in title:
        return GuidedStepView(
            headline=f"{phase_label} · review deployment expectations",
            summary="This synthetic senior frontend step compresses the operational context needed for production-aware UI work.",
            what_to_do_now=[
                "Read the deployment standards in the engineering standards document.",
                "Note deployment windows, CI/CD flow, and rollout expectations relevant to frontend changes.",
                "Resolve the step once you understand the operational constraints around shipping UI changes.",
            ],
            fastest_path="Review the deployment rules, then click I finished this.",
            why_it_matters="Senior frontend work needs system and deployment awareness, not just component-level knowledge.",
            primary_actions=["Explain this step", "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **common_kwargs,
        )
    return None


def _guided_step_view(state: OnboardingState, current_task, next_agent_task) -> GuidedStepView:
    citations = _source_citations(state)
    proof_status = _latest_proof(state)
    agent_available = bool(current_task and current_task.automation_mode in AGENT_AUTOMATION_MODES)
    phase_label = PHASE_LABELS.get(current_task.display_phase, "Guided onboarding") if current_task else "Guided onboarding"
    fallback_kwargs = {
        "time_estimate": _time_estimate(current_task),
        "escalation_contact": _escalation_contact(current_task),
        "blocked_hint": _blocked_hint(current_task),
    }
    if not current_task:
        return GuidedStepView(
            headline="Start by introducing yourself",
            summary="Tell OnboardAI your role, level, and tech stack so it can pick the right onboarding path.",
            what_to_do_now=[
                "Say who you are joining as, for example Backend Intern, Frontend Engineer, or DevOps.",
                "Mention your main tech stack, for example Node.js, React, Python, or Kubernetes.",
                "After that, the workspace will switch to your first guided step.",
            ],
            fastest_path="Example: Hi, I'm Riya. I've joined as a Backend Intern working on Node.js.",
            why_it_matters="Without your role and stack, the app cannot personalize your onboarding path.",
            primary_actions=["Introduce yourself"],
            upcoming_steps=["Persona matching", "Guided task plan", "First onboarding step"],
            agent_available=False,
        )

    specific = _specific_guided_step(state, current_task, next_agent_task)
    if specific is not None:
        upcoming = _upcoming_tasks(state)[1:4]
        specific.upcoming_steps = [f"Step {item['index']}: {item['taskId']} {item['title']}" for item in upcoming]
        return specific

    title = current_task.title.lower()
    if "laptop" in title:
        view = GuidedStepView(
            headline=f"{phase_label} · confirm your laptop kit",
            summary="This is only a physical handoff check. You are not expected to configure anything advanced yet.",
            what_to_do_now=[
                "Check that you received the laptop, charger, and can power the machine on.",
                "If the laptop turns on and the accessories are with you, this task is complete.",
                "You do not need the agent for this step.",
            ],
            fastest_path="If you already have it, click I have the laptop or type: i have the laptop",
            why_it_matters="All following setup tasks depend on having the company device in hand first.",
            source_citations=citations,
            proof_status=proof_status,
            primary_actions=["Explain this step", "I have the laptop", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **fallback_kwargs,
        )
    elif "google workspace" in title:
        view = GuidedStepView(
            headline=f"{phase_label} · activate your NovaByte Google account",
            summary="This gives you access to Gmail, Calendar, and Drive. It is the first real account-activation step.",
            what_to_do_now=[
                "Open the NovaByte invite email and accept the Google Workspace invitation.",
                "Sign in once and verify that Gmail, Calendar, and Drive all open successfully.",
                "When all three open, mark the task done to continue.",
            ],
            fastest_path="If you are stuck, ask: how do I activate Google Workspace?",
            why_it_matters="Most company systems are tied to your Google identity.",
            source_citations=citations,
            proof_status=proof_status,
            primary_actions=["Explain this step", "I activated it", "Skip for now"],
            upcoming_steps=[],
            agent_available=False,
            **fallback_kwargs,
        )
    elif "slack" in title:
        slack_base = state.dashboard_state.health.get("slack_workspace_url", "https://novabytetechnologies.slack.com").rstrip("/")
        eng_channel_url = f"{slack_base}/channels/engineering-general"
        joiners_url = f"{slack_base}/channels/new-joiners"
        view = GuidedStepView(
            headline=f"{phase_label} · join the required Slack channels",
            summary=f"Join the NovaByte Slack workspace at {slack_base} and then join the mandatory channels below.",
            what_to_do_now=[
                f"Open {slack_base} — sign in with your NovaByte Google account if prompted.",
                f"Join #engineering-general: {eng_channel_url}",
                f"Join #new-joiners: {joiners_url}",
                "Once you can see both channels, come back and click I joined Slack.",
            ],
            fastest_path=f"Click Run agent for me to open the workspace automatically, or go to {slack_base} directly.",
            why_it_matters="Slack is where onboarding updates, support questions, and engineering communication happen. The OnboardAI bot will post your progress there.",
            source_citations=citations,
            proof_status=proof_status,
            primary_actions=["Explain this step", "Run agent for me", "I joined Slack", "Skip for now"],
            upcoming_steps=[],
            agent_available=True,
            agent_fallback_message=f"Browser automation will open {slack_base} — sign in and join #engineering-general and #new-joiners.",
            **fallback_kwargs,
        )
    else:
        view = GuidedStepView(
            headline=f"{phase_label} · {current_task.task_id} {current_task.title}",
            summary="Follow the current task, then resolve it before moving forward. The workspace keeps the next action visible.",
            what_to_do_now=_generic_steps(current_task, next_agent_task),
            fastest_path=(
                "Use Run agent for me if available, otherwise finish the step and click I finished this."
                if agent_available
                else "Complete the step, then click I finished this or type: mark it done."
            ),
            why_it_matters="Completing tasks in order avoids missing required access, setup, or documentation.",
            source_citations=citations,
            proof_status=proof_status,
            primary_actions=["Explain this step", "Run agent for me" if agent_available else "I finished this", "Skip for now"],
            upcoming_steps=[],
            agent_available=agent_available,
            agent_fallback_message=(
                "If automation is unavailable, complete this step manually and resolve it in the workspace."
                if agent_available
                else None
            ),
            **fallback_kwargs,
        )

    upcoming = _upcoming_tasks(state)[1:4]
    view.upcoming_steps = [f"Step {item['index']}: {item['taskId']} {item['title']}" for item in upcoming]
    return view


def build_dashboard_props(state: OnboardingState) -> dict:
    total = len(state.task_plan)
    completed = sum(
        1 for task in state.task_plan
        if task.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}
    )
    current_task = get_current_task(state)
    next_agent_task = _next_agent_task(state)
    health = state.dashboard_state.health
    guided_step = _guided_step_view(state, current_task, next_agent_task)
    live_targets = _live_targets(state)
    current_task_label = state.dashboard_state.current_task or (current_task.title if current_task else "Waiting for onboarding input")
    persona_title = state.matched_persona.persona.title if state.matched_persona else None
    employee_name = state.employee_profile.name if state.employee_profile else None
    current_phase = current_task.display_phase.value if current_task else None
    return {
        "streamUrl": _usable_stream_url(state),
        "workspaceMode": (
            "live"
            if _usable_stream_url(state)
            else ("local_machine" if state.sandbox_session and state.sandbox_session.backend == "local" else "simulated")
        ),
        "sandboxBackend": state.sandbox_session.backend if state.sandbox_session else "unknown",
        "machinePanel": _machine_panel(state),
        "employeeName": employee_name,
        "personaTitle": persona_title,
        "currentTask": current_task_label,
        "currentTaskId": current_task.task_id if current_task else None,
        "currentTaskIndex": _step_ordinal(state, current_task),
        "currentTaskCategory": current_task.category if current_task else None,
        "currentTaskAutomation": current_task.automation_mode.value if current_task else None,
        "currentTaskPriority": current_task.priority.value if current_task else None,
        "currentTaskStatus": current_task.status.value if current_task else None,
        "currentTaskPhase": current_phase,
        "currentTaskEvidence": current_task.evidence_required if current_task else [],
        "currentTaskSources": _source_citations(state),
        "availableActions": _available_actions(current_task),
        "actionLabels": _action_labels(current_task),
        "upcomingTasks": _upcoming_tasks(state),
        "nextAgentTask": (
            {
                "taskId": next_agent_task.task_id,
                "title": next_agent_task.title,
                "automation": next_agent_task.automation_mode.value,
            }
            if next_agent_task
            else None
        ),
        "latestStatus": state.dashboard_state.latest_status,
        "latestProof": _latest_proof(state),
        "latestArtifacts": _latest_artifacts(state),
        "latestTranscript": _latest_transcript(state),
        "latestScreenshotArtifact": state.dashboard_state.latest_screenshot_artifact,
        "health": health,
        "liveTargets": live_targets,
        "stepTargets": _step_targets(state, current_task),
        "healthHint": _health_hint(health, current_task, next_agent_task),
        "milestoneProgress": _milestone_progress(state),
        "phaseCounts": _phase_counts(state),
        "totalTasks": total,
        "completedTasks": completed,
        "remainingTasks": max(total - completed, 0),
        "guidedStep": guided_step.model_dump(mode="json"),
        "showFullChecklist": state.show_full_checklist,
        "items": [
            {
                "taskId": item.task_id,
                "title": item.title,
                "status": item.status.value,
                "detail": item.detail,
                "timestamp": item.timestamp,
            }
            for item in state.dashboard_state.items
        ],
    }
