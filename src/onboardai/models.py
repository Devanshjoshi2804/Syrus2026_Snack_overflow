from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunMode(str, Enum):
    DEV_MOCK = "dev_mock"
    DEMO_REAL = "demo_real"


class VectorBackend(str, Enum):
    MEMORY = "memory"
    EMBEDDED_QDRANT = "embedded_qdrant"
    REMOTE_QDRANT = "remote_qdrant"


class EmbeddingBackend(str, Enum):
    HASH = "hash"
    SENTENCE_TRANSFORMER = "sentence_transformer"


class TaskStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"
    DEFERRED = "deferred"


class TaskPriority(str, Enum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    DEFERRED = "deferred"


class AutomationMode(str, Enum):
    KNOWLEDGE = "knowledge"
    SELF_SERVE = "self_serve"
    AGENT_TERMINAL = "agent_terminal"
    AGENT_BROWSER = "agent_browser"
    MANUAL_EXTERNAL = "manual_external"


class TaskAction(str, Enum):
    WATCH_AGENT = "watch_agent"
    SELF_COMPLETE = "self_complete"
    SKIP = "skip"


class ContentTier(str, Enum):
    RAG = "rag"
    LOGIC = "logic"
    TEMPLATE = "template"


class EmployeeProfile(BaseModel):
    name: str = "New Hire"
    role_family: str = "backend"
    experience_level: str = "intern"
    tech_stack: list[str] = Field(default_factory=list)
    department_hint: str | None = None
    preinstalled_tools: list[str] = Field(default_factory=list)
    email: str | None = None

    def search_terms(self) -> list[str]:
        terms = [self.name, self.role_family, self.experience_level, *self.tech_stack]
        if self.department_hint:
            terms.append(self.department_hint)
        return [term.lower() for term in terms if term]


class PersonaDefinition(BaseModel):
    persona_id: str
    name: str
    title: str
    role_family: str
    experience_level: str
    tech_stack: list[str] = Field(default_factory=list)
    department: str
    team: str | None = None
    manager_name: str | None = None
    manager_email: str | None = None
    mentor_name: str | None = None
    mentor_email: str | None = None
    email: str | None = None
    start_date: str | None = None
    location: str | None = None
    focus_points: list[str] = Field(default_factory=list)
    raw_fields: dict[str, str] = Field(default_factory=dict)


class PersonaMatch(BaseModel):
    persona_id: str
    score: float
    reasons: list[str] = Field(default_factory=list)
    persona: PersonaDefinition


class ChecklistTask(BaseModel):
    task_id: str
    title: str
    category: str
    deadline: str | None = None
    owner: str | None = None
    source_section: str
    automation_mode: AutomationMode = AutomationMode.SELF_SERVE
    priority: TaskPriority = TaskPriority.REQUIRED
    status: TaskStatus = TaskStatus.NOT_STARTED
    evidence_required: list[str] = Field(default_factory=list)
    notes: str | None = None


class VerificationEntry(BaseModel):
    task_id: str
    task_title: str
    status: TaskStatus
    method: str
    details: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    artifacts: list[str] = Field(default_factory=list)
    verified_values: dict[str, Any] = Field(default_factory=dict)


class DashboardItem(BaseModel):
    task_id: str
    title: str
    status: TaskStatus
    detail: str = ""
    timestamp: str | None = None


class DashboardState(BaseModel):
    stream_url: str | None = None
    current_task: str | None = None
    latest_status: str | None = None
    items: list[DashboardItem] = Field(default_factory=list)
    latest_screenshot_artifact: str | None = None
    health: dict[str, str] = Field(default_factory=dict)


class KnowledgeChunk(BaseModel):
    chunk_id: str
    source_path: str
    title: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchHit(BaseModel):
    chunk: KnowledgeChunk
    score: float


class SetupGuideStep(BaseModel):
    section_title: str
    step_id: str
    step_title: str
    commands: list[str] = Field(default_factory=list)
    expected_result: str | None = None
    notes: list[str] = Field(default_factory=list)


class SetupGuideSection(BaseModel):
    section_id: str
    title: str
    steps: list[SetupGuideStep] = Field(default_factory=list)


class ComputerUseInstruction(BaseModel):
    task_id: str
    goal: str
    success_criteria: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    expected_patterns: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int = 300
    command_plan: list[str] = Field(default_factory=list)
    url: str | None = None


class ComputerUseResult(BaseModel):
    task_id: str
    success: bool
    observations: list[str] = Field(default_factory=list)
    verified_values: dict[str, str] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    raw_transcript: str = ""
    failure_reason: str | None = None


class SandboxSession(BaseModel):
    session_id: str
    stream_url: str | None = None
    backend: str = "mock"
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompletionSummary(BaseModel):
    employee_name: str
    employee_email: str | None = None
    role: str
    team: str
    manager_name: str | None = None
    manager_email: str | None = None
    mentor_name: str | None = None
    mentor_email: str | None = None
    completed_items: list[ChecklistTask] = Field(default_factory=list)
    pending_items: list[ChecklistTask] = Field(default_factory=list)
    skipped_items: list[ChecklistTask] = Field(default_factory=list)
    verification_log: list[VerificationEntry] = Field(default_factory=list)
    score: int = 0
    notes: str = ""


class ContentFile(BaseModel):
    path: str
    tier: ContentTier
    parser: str
    searchable: bool = False
    required: bool = True


class IntegrationResult(BaseModel):
    success: bool
    status: str
    detail: str
    artifacts: list[str] = Field(default_factory=list)


class OnboardingState(BaseModel):
    employee_profile: EmployeeProfile | None = None
    matched_persona: PersonaMatch | None = None
    task_plan: list[ChecklistTask] = Field(default_factory=list)
    current_task_id: str | None = None
    verification_log: list[VerificationEntry] = Field(default_factory=list)
    artifact_paths: list[str] = Field(default_factory=list)
    completion_status: str = "not_started"
    dashboard_state: DashboardState = Field(default_factory=DashboardState)
    sandbox_session: SandboxSession | None = None
    knowledge_hits: list[SearchHit] = Field(default_factory=list)
    pending_reason: str | None = None
    selected_starter_ticket: dict[str, str] | None = None
