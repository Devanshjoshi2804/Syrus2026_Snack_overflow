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
from onboardai.computer_use.worker import ComputerUseWorker
from onboardai.email.generator import CompletionReportGenerator
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
        self.worker = ComputerUseWorker(self.config, self.sandbox_manager, self.browser_adapter)
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
        return (
            f"Matched persona: {match.persona.name} ({match.persona.title}). "
            f"Prepared {len(state.task_plan)} onboarding tasks for a {state.employee_profile.role_family} "
            f"{state.employee_profile.experience_level} path.\n\n"
            f"{self.task_presentation_node(state)}"
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
        return (
            f"Current task: `{task.task_id}` {task.title}\n"
            f"Category: {task.category}\n"
            f"Priority: {task.priority.value}\n"
            f"Automation: {task.automation_mode.value}\n"
            f"Evidence: {evidence}\n\n"
            f"Relevant context:\n{citations}\n\n"
            f"{starter_context}"
            "Actions available: Watch agent do this / I did it myself / Skip."
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
        if action == TaskAction.SKIP:
            mark_skipped(state, task.task_id, reason or "Skipped by user.")
        elif action == TaskAction.SELF_COMPLETE:
            mark_completed(state, task.task_id, "self_reported", reason or "Completed by user.")
        else:
            set_task_status(state, task.task_id, TaskStatus.IN_PROGRESS)
            result = self.computer_use_dispatch_node(state)
            if result.success:
                detail = ", ".join(f"{key}={value}" for key, value in result.verified_values.items())
                mark_completed(state, task.task_id, "agent", detail or "Agent completed task.", artifacts=result.artifacts, verified_values=result.verified_values)
            else:
                set_task_status(state, task.task_id, TaskStatus.BLOCKED)
                return f"Task blocked: {result.failure_reason}\n\n{self.task_presentation_node(state)}"
        choose_next_task(state)
        if self._ready_for_completion_email(state):
            return self.email_generation_node(state)
        return self.task_presentation_node(state)

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
        if stripped.endswith("?") or lowered.startswith(QUESTION_PREFIXES):
            return self.rag_qa_node(state, stripped)
        if lowered in {"next", "continue", "show next task"}:
            return self.task_presentation_node(state)
        return (
            "Use the task actions for completions or ask a question about onboarding. "
            f"\n\n{self.task_presentation_node(state)}"
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
        return {"state": onboarding_state, "response": response}

    graph = StateGraph(dict)
    graph.add_node("intake_node", intake)
    graph.add_edge(START, "intake_node")
    graph.add_edge("intake_node", END)
    return graph.compile()
