from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from onboardai.adapters.browser import build_browser_adapter
from onboardai.adapters.e2b import build_sandbox_manager
from onboardai.adapters.github import GitHubAdapter
from onboardai.adapters.jira import JiraAdapter
from onboardai.adapters.slack import SlackAdapter
from onboardai.adapters.vector_store import build_vector_store
from onboardai.checklist.planner import ChecklistPlanner
from onboardai.config import AppConfig, load_config
from onboardai.content.parser import parse_contacts, parse_personas, parse_setup_guides
from onboardai.content.registry import build_default_registry, validate_registry_files
from onboardai.computer_use.worker import build_worker, ComputerUseWorker
from onboardai.email.generator import CompletionReportGenerator
from onboardai.llm_backend import LLMBackend, build_llm_backend
from onboardai.local_llm import LocalResponder
from onboardai.models import (
    AutomationMode,
    ComputerUseInstruction,
    OnboardingState,
    TaskAction,
    TaskPriority,
    TaskStatus,
)
from onboardai.persona.matcher import PersonaMatcher, extract_employee_profile
from onboardai.rag.retriever import KnowledgeRetriever
from onboardai.state import choose_next_task, get_current_task, mark_completed, mark_skipped, set_task_status


QUESTION_PREFIXES = ("how", "what", "when", "where", "who", "why", "can", "do", "should")
HELP_PATTERNS = (
    "i dont know",
    "i don't know",
    "help me",
    "i need help",
    "what do i do",
    "what should i do",
    "i am confused",
    "i'm confused",
    "not sure",
    "dont know anything",
    "don't know anything",
)
COMPLETION_HINTS = (
    "yes i have",
    "yes i did",
    "i have received",
    "i received",
    "i have recived",
    "i recived",
    "received laptop",
    "recived laptop",
    "i got",
    "i have got",
    "i completed",
    "i have completed",
    "i finished",
    "i have finished",
    "i set up",
    "i setup",
    "done with this",
    "have the laptop",
    "have my laptop",
    "received company laptop",
    "received the company laptop",
)
TYPED_ACTION_PHRASES = {
    TaskAction.WATCH_AGENT: {
        "watch agent do this",
        "watch agent",
        "agent do this",
        "let agent do it",
        "let the agent do it",
        "agent do it",
        "do this for me",
        "do it for me",
        "run it for me",
    },
    TaskAction.SELF_COMPLETE: {
        "i did it myself",
        "i did this myself",
        "done",
        "completed",
        "mark done",
        "mark it done",
        "yes mark it done",
        "complete this",
        "i finished this",
    },
    TaskAction.SKIP: {
        "skip",
        "skip this",
        "skip task",
        "skip it",
    },
}


class OnboardingEngine:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or load_config()
        self.registry = build_default_registry(self.config.dataset_root)
        missing = validate_registry_files(self.registry)
        if missing:
            raise FileNotFoundError(f"Missing required content files: {', '.join(missing)}")

        personas = parse_personas(self.config.dataset_root / "employee_personas.md")
        self.matcher = PersonaMatcher(personas)
        self.setup_guides = parse_setup_guides(self.config.dataset_root / "setup_guides.md")
        self.planner = ChecklistPlanner.from_markdown(
            self.config.dataset_root / "onboarding_checklists.md",
            self.config.dataset_root / "starter_tickets.md",
        )
        self.retriever = KnowledgeRetriever(self.config.dataset_root, build_vector_store(self.config))
        self.sandbox_manager = build_sandbox_manager(self.config)
        self.browser_adapter = build_browser_adapter(self.config)
        self.llm_backend = build_llm_backend(self.config)
        self.worker = build_worker(self.config, self.sandbox_manager, self.browser_adapter, self.llm_backend)
        self.email_generator = CompletionReportGenerator(
            self.config.dataset_root / "email_templates.md",
            self.config.outputs_dir,
        )
        self.local_responder = LocalResponder(self.config)
        self.contacts = parse_contacts(self.config.dataset_root / "org_structure.md")
        self.github = GitHubAdapter()
        self.slack = SlackAdapter()
        self.jira = JiraAdapter()

    def new_state(self) -> OnboardingState:
        state = OnboardingState(completion_status="in_progress")
        state.sandbox_session = self.sandbox_manager.start()
        state.dashboard_state.stream_url = state.sandbox_session.stream_url
        state.dashboard_state.health = self.runtime_health()
        return state

    def intake_node(self, state: OnboardingState, message: str) -> str:
        state.employee_profile = extract_employee_profile(message)
        return self.persona_match_node(state)

    def persona_match_node(self, state: OnboardingState) -> str:
        if not state.employee_profile:
            raise ValueError("Employee profile must be set before persona matching.")
        state.matched_persona = self.matcher.match(state.employee_profile)
        state.task_plan = self.planner.build_plan(state.employee_profile, state.matched_persona)
        state.selected_starter_ticket = self._starter_ticket_for_state(state)
        choose_next_task(state)
        state.completion_status = "in_progress"
        match = state.matched_persona
        current_task = get_current_task(state)
        return (
            f"Welcome {state.employee_profile.name}. "
            f"You're onboarding as {match.persona.title}. "
            f"We're starting with Step 1: `{current_task.task_id}` {current_task.title}. "
            "Look at the workspace card for the exact walkthrough and use its buttons instead of guessing commands. "
            "If you already have the laptop, click **I have the laptop** or say `i have the laptop`."
        )

    def task_presentation_node(self, state: OnboardingState) -> str:
        task = get_current_task(state) or choose_next_task(state)
        if not task:
            return self.email_generation_node(state)
        hits = self.retriever.query(task.title, profile=state.employee_profile, limit=2)
        state.knowledge_hits = hits
        citations = "\n".join(
            f"- {Path(hit.chunk.source_path).name}: {hit.chunk.title}"
            for hit in hits
        ) or "- No supporting document retrieved."
        evidence = ", ".join(task.evidence_required) if task.evidence_required else "Task acknowledgment"
        starter_context = ""
        starter_ticket = self._starter_ticket_for_state(state)
        if starter_ticket and (
            "repository" in task.title.lower()
            or task.category.lower() == "first task"
            or "git workflow" in task.title.lower()
        ):
            starter_context = (
                f"\nStarter ticket context:\n"
                f"- Ticket: {starter_ticket.get('Ticket ID', 'N/A')}\n"
                f"- Repo: {starter_ticket.get('Repo URL', 'N/A')}\n"
                f"- Tracking: {starter_ticket.get('Tracking URL', 'N/A')}\n"
            )
        actions_line = self._actions_line(task)
        return (
            f"Current task: `{task.task_id}` {task.title}\n"
            f"Category: {task.category}\n"
            f"Priority: {task.priority.value}\n"
            f"Automation: {task.automation_mode.value}\n"
            f"Evidence: {evidence}\n\n"
            f"Relevant context:\n{citations}\n\n"
            f"{starter_context}"
            f"{actions_line}"
        )

    def rag_qa_node(self, state: OnboardingState, question: str) -> str:
        hits = self.retriever.query(question, profile=state.employee_profile, limit=3)
        threshold_hits = [hit for hit in hits if hit.score >= self.config.retrieval_threshold]
        if not threshold_hits:
            contact = self._fallback_contact(question)
            return (
                "I cannot find a grounded answer for that in the provided knowledge base. "
                f"Please contact {contact.get('Contact Person', 'Tanvi Shah')} "
                f"({contact.get('Email', 'tanvi.s@novabyte.dev')})."
            )
        top = threshold_hits[0]
        context = "\n\n".join(hit.chunk.text for hit in threshold_hits)
        excerpt = top.chunk.text.strip().split("\n", 1)[-1][:600].strip()
        llm_answer = self.local_responder.answer(question, context)
        citations = "; ".join(
            f"{Path(hit.chunk.source_path).name} -> {hit.chunk.title}"
            for hit in threshold_hits
        )
        return f"{llm_answer or excerpt}\n\nSources: {citations}"

    def task_action_router_node(
        self,
        state: OnboardingState,
        action: TaskAction,
        reason: str | None = None,
    ) -> str:
        task = get_current_task(state) or choose_next_task(state)
        if not task:
            return self.email_generation_node(state)
        if action not in self._available_actions_for_task(task):
            next_agent_task = self._next_agent_task(state)
            next_agent_line = ""
            if next_agent_task:
                next_agent_line = (
                    f"\n\nThe next agent-runnable step is `{next_agent_task.task_id}` "
                    f"{next_agent_task.title}."
                )
            return (
                f"`{task.task_id}` is a manual step, so the agent cannot execute it directly."
                f"{next_agent_line}\n\n"
                "Use the workspace card on the right: it shows what this step means, how to finish it, and the exact button to click next."
            )
        if action == TaskAction.SKIP:
            mark_skipped(state, task.task_id, reason or "Skipped by user.")
            resolution_line = f"Skipped `{task.task_id}` {task.title}."
        elif action == TaskAction.SELF_COMPLETE:
            mark_completed(state, task.task_id, "self_reported", reason or "Completed by user.")
            resolution_line = f"Marked `{task.task_id}` {task.title} complete."
        else:
            set_task_status(state, task.task_id, TaskStatus.IN_PROGRESS)
            result = self.computer_use_dispatch_node(state)
            if result.success:
                detail = ", ".join(f"{key}={value}" for key, value in result.verified_values.items())
                mark_completed(state, task.task_id, "agent", detail or "Agent completed task.", artifacts=result.artifacts, verified_values=result.verified_values)
                resolution_line = f"Agent completed `{task.task_id}` {task.title}."
            else:
                set_task_status(state, task.task_id, TaskStatus.BLOCKED)
                return f"Task blocked: {result.failure_reason}\n\n{self._chat_current_task_summary(state)}"
        choose_next_task(state)
        if self._ready_for_completion_email(state):
            return self.email_generation_node(state)
        next_task = get_current_task(state)
        if not next_task:
            return resolution_line
        return (
            f"{resolution_line}\n\n"
            f"Next step: `{next_task.task_id}` {next_task.title}. "
            "I updated the workspace with the next walkthrough and actions."
        )

    def computer_use_dispatch_node(self, state: OnboardingState):
        task = get_current_task(state)
        if not task or not state.sandbox_session:
            raise ValueError("No active task or sandbox session.")
        instruction = self._build_instruction(task, state)
        return self.worker.execute(instruction, state.sandbox_session)

    def email_generation_node(self, state: OnboardingState) -> str:
        starter_ticket = self._starter_ticket_for_state(state)
        html_path, json_path = self.email_generator.generate(state, starter_ticket=starter_ticket)
        state.completion_status = "completed"
        return (
            "Generated HR completion artifacts.\n"
            f"- HTML report: {html_path}\n"
            f"- JSON summary: {json_path}\n"
            f"- Score: {self.email_generator.build_summary(state, starter_ticket).score}%"
        )

    def handle_message(self, state: OnboardingState, message: str) -> str:
        stripped = message.strip()
        if not state.employee_profile:
            return self.intake_node(state, stripped)
        lowered = stripped.lower()
        typed_action = self._parse_typed_action(stripped)
        if typed_action is not None:
            reason = None
            if typed_action == TaskAction.SKIP:
                reason = "Skipped from chat."
            elif typed_action == TaskAction.SELF_COMPLETE:
                reason = "Completed from chat."
            return self.task_action_router_node(state, typed_action, reason)
        if self._looks_like_completion_confirmation(state, lowered):
            return self.task_action_router_node(state, TaskAction.SELF_COMPLETE, "Completed from conversation.")
        if self._looks_like_help_request(lowered):
            return self.task_help_node(state, stripped)
        if stripped.endswith("?") or lowered.startswith(QUESTION_PREFIXES):
            return self.rag_qa_node(state, stripped)
        if lowered in {"next", "continue", "show next task"}:
            return self._chat_current_task_summary(state)
        return (
            "Use the workspace buttons for this step. If you need help, click **Explain this step** or ask "
            "`what do i do for this step`."
        )

    def task_help_node(self, state: OnboardingState, message: str) -> str:
        task = get_current_task(state) or choose_next_task(state)
        if not task:
            return "There is no active task right now."
        title = task.title.lower()
        if "laptop" in title:
            return (
                "For this step, you only need to confirm that you physically received the company laptop, "
                "charger, and can turn it on. There is no technical setup yet. "
                "If you already have it, click **I have the laptop** in the workspace or say `i have the laptop`."
            )
        if "google workspace" in title:
            return (
                "This step is manual. Open your NovaByte welcome email, accept the Google Workspace invite, "
                "sign in once, and make sure Gmail, Calendar, and Drive all open. "
                "When they do, click **I activated it** in the workspace."
            )
        if "slack" in title:
            return (
                "This step can be agent-assisted. In the workspace, use **Run agent for me** to automate it, "
                "or open Slack yourself, join the required channels, and then click **I joined Slack**."
            )
        hits = self.retriever.query(f"{task.title}\n{message}", profile=state.employee_profile, limit=2)
        if hits:
            excerpt = hits[0].chunk.text.strip().split("\n", 1)[-1][:260].strip()
            return (
                f"For `{task.task_id}` {task.title}: {excerpt}\n\n"
                "If you want, say `let agent do it` when the task is agent-runnable, or `mark it done` after you finish it."
            )
        return (
            f"For `{task.task_id}` {task.title}, follow the guidance in the workspace panel and then mark it done. "
            "If you are stuck, ask a direct question like `how do I do this step?`."
        )

    def serialize_dashboard(self, state: OnboardingState) -> str:
        return json.dumps(
            {
                "stream_url": state.dashboard_state.stream_url,
                "current_task": state.dashboard_state.current_task,
                "latest_status": state.dashboard_state.latest_status,
                "health": state.dashboard_state.health,
                "items": [item.model_dump(mode="json") for item in state.dashboard_state.items],
            }
        )

    def runtime_health(self) -> dict[str, str]:
        vector_health = self.retriever.vector_store.healthcheck()
        return {
            "mode": self.config.mode.value,
            "vector_backend": vector_health.get("backend", "unknown"),
            "browser_backend": self.config.browser_backend,
            "browser_impl": self.browser_adapter.__class__.__name__,
            "browser_ready": "yes" if self.browser_adapter.is_available() else "no",
            "docker": "yes" if shutil.which("docker") else "no",
            "sandbox_backend": self.sandbox_manager.__class__.__name__,
        }

    def available_actions(self, state: OnboardingState) -> list[TaskAction]:
        task = get_current_task(state) or choose_next_task(state)
        if not task:
            return []
        return self._available_actions_for_task(task)

    def next_agent_task(self, state: OnboardingState):
        return self._next_agent_task(state)

    def _fallback_contact(self, question: str) -> dict[str, str]:
        lower = question.lower()
        if "github" in lower or "access" in lower:
            return self.contacts.get("github / access issues", {})
        if "vpn" in lower or "network" in lower:
            return self.contacts.get("vpn / network access", {})
        if "training" in lower or "compliance" in lower:
            return self.contacts.get("compliance training", {})
        return self.contacts.get("onboarding general", {})

    def _ready_for_completion_email(self, state: OnboardingState) -> bool:
        required_tasks = [task for task in state.task_plan if task.priority == TaskPriority.REQUIRED]
        return bool(required_tasks) and all(
            task.status in {TaskStatus.COMPLETED, TaskStatus.SKIPPED}
            for task in required_tasks
        )

    def _starter_ticket_for_state(self, state: OnboardingState) -> dict[str, str] | None:
        if state.selected_starter_ticket:
            return state.selected_starter_ticket
        if state.matched_persona:
            return self.planner.pick_starter_ticket(state.matched_persona)
        return None

    def _actions_line(self, task) -> str:
        available = self._available_actions_for_task(task)
        action_labels = {
            TaskAction.WATCH_AGENT: "Watch agent do this",
            TaskAction.SELF_COMPLETE: "I did it myself",
            TaskAction.SKIP: "Skip",
        }
        labels = " / ".join(action_labels[action] for action in available)
        if task.automation_mode in {AutomationMode.AGENT_TERMINAL, AutomationMode.AGENT_BROWSER}:
            return f"Actions available: {labels}."
        return f"Actions available: {labels}. This is a manual step, so the agent will not execute it."

    def _available_actions_for_task(self, task) -> list[TaskAction]:
        if task.automation_mode in {AutomationMode.AGENT_TERMINAL, AutomationMode.AGENT_BROWSER}:
            return [TaskAction.WATCH_AGENT, TaskAction.SELF_COMPLETE, TaskAction.SKIP]
        return [TaskAction.SELF_COMPLETE, TaskAction.SKIP]

    def _next_agent_task(self, state: OnboardingState):
        current_index = -1
        for index, task in enumerate(state.task_plan):
            if task.task_id == state.current_task_id:
                current_index = index
                break
        for task in state.task_plan[current_index + 1:]:
            if task.status in {TaskStatus.NOT_STARTED, TaskStatus.IN_PROGRESS} and task.automation_mode in {
                AutomationMode.AGENT_TERMINAL,
                AutomationMode.AGENT_BROWSER,
            }:
                return task
        return None

    def _looks_like_help_request(self, lowered: str) -> bool:
        return any(pattern in lowered for pattern in HELP_PATTERNS)

    def _looks_like_completion_confirmation(self, state: OnboardingState, lowered: str) -> bool:
        task = get_current_task(state)
        if not task:
            return False
        normalized = lowered.replace("recived", "received").replace("setup", "set up")
        if any(pattern in lowered for pattern in COMPLETION_HINTS):
            return True
        if "laptop" in task.title.lower() and "laptop" in normalized and any(
            token in normalized for token in ("received", "have", "got")
        ):
            return True
        return False

    def _chat_current_task_summary(self, state: OnboardingState) -> str:
        task = get_current_task(state) or choose_next_task(state)
        if not task:
            return "All onboarding tasks are resolved."
        action_labels = {
            TaskAction.WATCH_AGENT: "let agent do it",
            TaskAction.SELF_COMPLETE: "mark it done",
            TaskAction.SKIP: "skip this",
        }
        actions = ", ".join(action_labels[action] for action in self._available_actions_for_task(task))
        return (
            f"Current step: `{task.task_id}` {task.title}. "
            f"Available actions: {actions}. "
            "The workspace card has the walkthrough, the buttons, and the next steps."
        )

    def _parse_typed_action(self, message: str) -> TaskAction | None:
        normalized = re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", message.lower())).strip()
        for action, phrases in TYPED_ACTION_PHRASES.items():
            if normalized in phrases:
                return action
        return None

    def _build_instruction(self, task, state: OnboardingState) -> ComputerUseInstruction:
        title = task.title.lower()
        email = state.employee_profile.email if state.employee_profile else None
        if not email and state.matched_persona:
            email = state.matched_persona.persona.email
        email = email or "new.hire@novabyte.dev"
        name = state.employee_profile.name if state.employee_profile else "New Hire"
        dataset_instruction = self._instruction_from_setup_guides(task, state, name=name, email=email)
        if dataset_instruction:
            return dataset_instruction
        if "node.js 20" in title:
            return ComputerUseInstruction(
                task_id=task.task_id,
                goal=task.title,
                success_criteria=["Node.js 20 installed", "node --version returns v20.x"],
                allowed_tools=["bash"],
                expected_patterns={"node_version": r"v20\.\d+\.\d+"},
                command_plan=[
                    'export NVM_DIR="$HOME/.nvm" && mkdir -p "$NVM_DIR"',
                    'export NVM_DIR="$HOME/.nvm" && command -v nvm >/dev/null 2>&1 || curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash',
                    'export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && nvm install 20',
                    'export NVM_DIR="$HOME/.nvm" && [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh" && node --version',
                ],
            )
        if "pnpm" in title:
            return ComputerUseInstruction(
                task_id=task.task_id,
                goal=task.title,
                success_criteria=["pnpm installed", "pnpm --version returns 8.x"],
                allowed_tools=["bash"],
                expected_patterns={"pnpm_version": r"\b8\.\d+\.\d+\b"},
                command_plan=[
                    "npm install -g pnpm@8",
                    "pnpm --version",
                ],
            )
        if "git" in title and "config" in title:
            return ComputerUseInstruction(
                task_id=task.task_id,
                goal=task.title,
                success_criteria=["git user.name configured", "git user.email configured"],
                allowed_tools=["bash"],
                expected_patterns={"git_email": r"[\w.+-]+@[\w.-]+"},
                command_plan=[
                    f'git config --global user.name "{name}"',
                    f'git config --global user.email "{email}"',
                    "git config --global user.email",
                ],
            )
        starter_ticket = self._starter_ticket_for_state(state) or {}
        repo_url = starter_ticket.get("Repo URL")
        tracking_url = starter_ticket.get("Tracking URL")
        ticket_id = starter_ticket.get("Ticket ID", "FLOW-DEMO-001")
        repo_name = starter_ticket.get("Repo", "demo-repo")
        if "clone assigned repository" in title or "clone connector-runtime" in title:
            clone_url = repo_url or f"{self.config.github_org_url}/{repo_name}"
            expected_repo_name = repo_name.replace(".git", "")
            return ComputerUseInstruction(
                task_id=task.task_id,
                goal=task.title,
                success_criteria=["Repository cloned locally"],
                allowed_tools=["bash"],
                expected_patterns={"repository": re.escape(expected_repo_name)},
                command_plan=[
                    f"rm -rf /tmp/{expected_repo_name}",
                    f"git clone {clone_url} /tmp/{expected_repo_name}",
                    f"ls /tmp/{expected_repo_name}",
                ],
            )
        if "docker compose" in title:
            return ComputerUseInstruction(
                task_id=task.task_id,
                goal=task.title,
                success_criteria=["Docker Compose command ran"],
                allowed_tools=["bash"],
                expected_patterns={"compose_status": r"(Running|Up|Created|No containers|Mock executed)"},
                command_plan=[
                    f"cd '{self.config.project_root}' && docker compose ps || true",
                ],
            )
        if "starter ticket" in title and "pick up" in title:
            return ComputerUseInstruction(
                task_id=task.task_id,
                goal=task.title,
                success_criteria=["Starter ticket opened"],
                allowed_tools=["browser"],
                url=tracking_url or self.config.jira_url,
            )
        if "submit pr" in title:
            pulls_url = f"{repo_url}/pulls" if repo_url else self.config.github_org_url
            return ComputerUseInstruction(
                task_id=task.task_id,
                goal=task.title,
                success_criteria=["Pull request page opened"],
                allowed_tools=["browser"],
                url=pulls_url,
            )
        if "git workflow practice" in title:
            branch_name = f"feat/{ticket_id.lower()}-setup-env"
            return ComputerUseInstruction(
                task_id=task.task_id,
                goal=task.title,
                success_criteria=["Git practice branch created"],
                allowed_tools=["bash"],
                expected_patterns={"branch": re.escape(branch_name)},
                command_plan=[
                    "rm -rf /tmp/onboardai-git-practice",
                    "mkdir -p /tmp/onboardai-git-practice && cd /tmp/onboardai-git-practice && git init",
                    f"cd /tmp/onboardai-git-practice && git checkout -b {branch_name}",
                    "cd /tmp/onboardai-git-practice && git branch --show-current",
                ],
            )
        if task.automation_mode == AutomationMode.AGENT_BROWSER:
            url = self.config.github_org_url
            if "slack" in title:
                url = self.config.slack_workspace_url
            elif "jira" in title:
                url = self.config.jira_url
            return ComputerUseInstruction(
                task_id=task.task_id,
                goal=task.title,
                success_criteria=[f"Opened {url}"],
                allowed_tools=["browser"],
                url=url,
            )
        return ComputerUseInstruction(
            task_id=task.task_id,
            goal=task.title,
            success_criteria=["Task acknowledged"],
            allowed_tools=["none"],
        )

    def _instruction_from_setup_guides(
        self,
        task,
        state: OnboardingState,
        *,
        name: str,
        email: str,
    ) -> ComputerUseInstruction | None:
        if task.task_id.lower() == "jfs-05":
            return self._full_stack_clone_instruction(task, state)
        step = self._find_setup_step(task, state)
        if not step or not step.commands:
            return None
        commands = self._commands_for_task(task, step.commands, state, name=name, email=email)
        if not commands:
            return None
        expected_patterns = self._expected_patterns_for_commands(commands, state)
        success_criteria = [step.expected_result] if step.expected_result else [task.title]
        return ComputerUseInstruction(
            task_id=task.task_id,
            goal=task.title,
            success_criteria=success_criteria,
            allowed_tools=["bash"],
            expected_patterns=expected_patterns,
            command_plan=commands,
        )

    def _find_setup_step(self, task, state: OnboardingState):
        relevant_sections = self._relevant_setup_sections(task, state)
        if not relevant_sections:
            return None
        query_terms = self._setup_query_terms(task)
        best_step = None
        best_score = 0
        for section in relevant_sections:
            for step in section.steps:
                haystack = " ".join([step.step_title, *step.commands, *step.notes]).lower()
                score = sum(1 for term in query_terms if term in haystack)
                if score > best_score:
                    best_step = step
                    best_score = score
        return best_step

    def _relevant_setup_sections(self, task, state: OnboardingState) -> list:
        task_id = task.task_id.lower()
        title = task.title.lower()
        section_ids: list[str] = []
        if task_id.startswith("bi-"):
            section_ids.append("backend-intern-node-js-local-setup")
        elif task_id.startswith("jbp-"):
            section_ids.append("junior-backend-python-fastapi")
        elif task_id.startswith("jfr-"):
            section_ids.append("frontend-react-typescript")
        elif task_id.startswith("sdo-"):
            section_ids.append("platform-devops")
        elif task_id.startswith("jfs-"):
            if any(
                token in title
                for token in ("frontend", "storybook", "react", "design system", "flowengine-web", "ui")
            ):
                section_ids.append("frontend-react-typescript")
            else:
                section_ids.append("backend-intern-node-js-local-setup")
        elif task_id.startswith("sbn-"):
            section_ids.append("backend-intern-node-js-local-setup")
            section_ids.append("platform-devops")
        persona = state.matched_persona.persona if state.matched_persona else None
        if persona:
            if persona.role_family == "frontend":
                section_ids.append("frontend-react-typescript")
            elif persona.role_family == "devops":
                section_ids.append("platform-devops")
            elif "python" in persona.tech_stack:
                section_ids.append("junior-backend-python-fastapi")
            else:
                section_ids.append("backend-intern-node-js-local-setup")
        unique_ids: list[str] = []
        for section_id in section_ids:
            if section_id not in unique_ids:
                unique_ids.append(section_id)
        return [self.setup_guides[section_id] for section_id in unique_ids if section_id in self.setup_guides]

    def _setup_query_terms(self, task) -> list[str]:
        title = task.title.lower()
        if "node.js" in title:
            return ["install node.js", "node.js 20", "nvm"]
        if "pnpm" in title:
            return ["install pnpm", "pnpm", "typescript", "nodemon"]
        if "git" in title and "config" in title:
            return ["configure git identity", "git config"]
        if "python 3.11" in title or "poetry" in title:
            return ["install python 3.11 and poetry", "poetry"]
        if "terraform" in title or "kubectl" in title or "helm" in title:
            return ["install required tools", "terraform", "kubectl", "helm"]
        if "clone" in title:
            return [
                "clone starter repository",
                "clone and bootstrap",
                "infrastructure repository",
                "install dependencies",
            ]
        if "docker compose" in title:
            return ["run docker compose", "docker compose", "local dependencies"]
        if any(token in title for token in ("start the service", "start development server", "verify it loads")):
            return ["run the local service", "install dependencies", "clone and bootstrap"]
        if any(token in title for token in ("unit tests", "pytest", "test suite")):
            return ["pnpm test", "pytest", "clone and bootstrap", "run the local service"]
        return [title]

    def _commands_for_task(
        self,
        task,
        commands: list[str],
        state: OnboardingState,
        *,
        name: str,
        email: str,
    ) -> list[str]:
        title = task.title.lower()
        filtered = commands
        if "python 3.11" in title and "poetry" not in title:
            narrowed = [command for command in commands if "python3.11 --version" in command.lower()]
            filtered = narrowed or commands
        elif "poetry" in title and "python 3.11" not in title:
            narrowed = [
                command
                for command in commands
                if "poetry" in command.lower() or "install.python-poetry.org" in command.lower()
            ]
            filtered = narrowed or commands
        elif any(token in title for token in ("unit tests", "pytest", "test suite")):
            narrowed = [
                command for command in commands if any(token in command.lower() for token in ("pytest", "test"))
            ]
            filtered = narrowed or commands
        elif any(token in title for token in ("start the service", "start development server", "verify it loads")):
            narrowed = [
                command
                for command in commands
                if any(token in command.lower() for token in ("pnpm dev", "uvicorn", "storybook"))
            ]
            filtered = narrowed or commands

        starter_ticket = self._starter_ticket_for_state(state) or {}
        repo_url = starter_ticket.get("Repo URL")
        repo_name = starter_ticket.get("Repo", "").strip()
        multi_repo_clone = "clone" in title and " and " in title
        adapted: list[str] = []
        for command in filtered:
            updated = command.replace("Your Name", name).replace("your.name@novabyte.dev", email)
            if repo_url and updated.startswith("git clone https://github.com/") and not multi_repo_clone:
                updated = re.sub(r"https://github\.com/\S+", repo_url, updated, count=1)
            if repo_name and "cd connector-runtime-demo" in updated:
                updated = updated.replace("connector-runtime-demo", repo_name)
            adapted.append(updated)
        return adapted

    def _expected_patterns_for_commands(
        self,
        commands: list[str],
        state: OnboardingState,
    ) -> dict[str, str]:
        patterns: dict[str, str] = {}
        combined = "\n".join(commands).lower()
        if "node --version" in combined:
            patterns["node_version"] = r"v20\.\d+\.\d+"
        if "pnpm --version" in combined:
            patterns["pnpm_version"] = r"\b8\.\d+\.\d+\b"
        if "tsc --version" in combined:
            patterns["typescript_version"] = r"Version\s+\d+\.\d+\.\d+"
        if "git config --global user.email" in combined:
            patterns["git_email"] = r"[\w.+-]+@[\w.-]+"
        if "python3.11 --version" in combined:
            patterns["python_version"] = r"Python 3\.11\.\d+"
        if "poetry --version" in combined:
            patterns["poetry_version"] = r"(?i)poetry.*\d+\.\d+\.\d+"
        if "terraform version" in combined:
            patterns["terraform_version"] = r"Terraform v\d+\.\d+\.\d+"
        if "kubectl version --client" in combined:
            patterns["kubectl_version"] = r"Client Version:\s*v?\d+\.\d+\.\d+"
        if "helm version" in combined:
            patterns["helm_version"] = r"v\d+\.\d+\.\d+"
        if "git clone " in combined:
            starter_ticket = self._starter_ticket_for_state(state) or {}
            repo_name = starter_ticket.get("Repo", "demo-repo").replace(".git", "")
            patterns["repository"] = re.escape(repo_name)
        return patterns

    def _full_stack_clone_instruction(
        self,
        task,
        state: OnboardingState,
    ) -> ComputerUseInstruction | None:
        backend_section = self.setup_guides.get("backend-intern-node-js-local-setup")
        frontend_section = self.setup_guides.get("frontend-react-typescript")
        if not backend_section or not frontend_section:
            return None
        backend_clone = next(
            (step for step in backend_section.steps if "clone starter repository" in step.step_title.lower()),
            None,
        )
        frontend_bootstrap = next(
            (step for step in frontend_section.steps if "install dependencies" in step.step_title.lower()),
            None,
        )
        if not backend_clone or not frontend_bootstrap:
            return None
        commands = []
        commands.extend(backend_clone.commands)
        commands.extend(
            [
                command
                for command in frontend_bootstrap.commands
                if command.startswith("git clone ") or "pnpm install" in command.lower()
            ]
        )
        return ComputerUseInstruction(
            task_id=task.task_id,
            goal=task.title,
            success_criteria=["Backend and frontend repositories cloned locally"],
            allowed_tools=["bash"],
            expected_patterns={
                "backend_repository": re.escape("connector-runtime-demo"),
                "frontend_repository": re.escape("flowengine-web-demo"),
            },
            command_plan=commands,
        )


def build_langgraph(engine: OnboardingEngine | None = None):
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError:
        return None

    runtime = engine or OnboardingEngine()

    def intake(state: dict):
        onboarding_state = state["state"]
        response = runtime.intake_node(onboarding_state, state["message"])
        return {"state": onboarding_state, "response": response, "message": ""}

    def rag_qa(state: dict):
        onboarding_state = state["state"]
        response = runtime.rag_qa_node(onboarding_state, state["message"])
        return {"state": onboarding_state, "response": response, "message": ""}

    def task_presentation(state: dict):
        onboarding_state = state["state"]
        response = runtime.task_presentation_node(onboarding_state)
        return {"state": onboarding_state, "response": response, "message": ""}

    def task_action_router(state: dict):
        onboarding_state = state["state"]
        action_str = state.get("action", "self_complete")
        action = TaskAction(action_str) if action_str in {a.value for a in TaskAction} else TaskAction.SELF_COMPLETE
        response = runtime.task_action_router_node(onboarding_state, action, state.get("reason"))
        return {"state": onboarding_state, "response": response, "message": ""}

    def email_generation(state: dict):
        onboarding_state = state["state"]
        response = runtime.email_generation_node(onboarding_state)
        return {"state": onboarding_state, "response": response, "message": ""}

    def route_message(state: dict) -> str:
        onboarding_state = state["state"]
        msg = (state.get("message") or "").strip()
        if not onboarding_state.employee_profile:
            return "intake"
        lowered = msg.lower()
        if runtime._parse_typed_action(msg) is not None:
            state["action"] = runtime._parse_typed_action(msg).value
            return "task_action_router"
        if msg.endswith("?") or lowered.startswith(QUESTION_PREFIXES):
            return "rag_qa"
        if lowered in {"next", "continue", "show next task"}:
            return "task_presentation"
        if state.get("action"):
            return "task_action_router"
        if runtime._ready_for_completion_email(onboarding_state):
            return "email_generation"
        return "task_presentation"

    graph = StateGraph(dict)
    graph.add_node("intake", intake)
    graph.add_node("rag_qa", rag_qa)
    graph.add_node("task_presentation", task_presentation)
    graph.add_node("task_action_router", task_action_router)
    graph.add_node("email_generation", email_generation)

    graph.add_conditional_edges(START, route_message, {
        "intake": "intake",
        "rag_qa": "rag_qa",
        "task_presentation": "task_presentation",
        "task_action_router": "task_action_router",
        "email_generation": "email_generation",
    })
    graph.add_edge("intake", END)
    graph.add_edge("rag_qa", END)
    graph.add_edge("task_presentation", END)
    graph.add_edge("task_action_router", END)
    graph.add_edge("email_generation", END)

    return graph.compile()
