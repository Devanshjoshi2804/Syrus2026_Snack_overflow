from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from onboardai.models import EmbeddingBackend, JourneyMode, RunMode, VectorBackend


load_dotenv()


def detect_dataset_root(project_root: Path) -> Path:
    explicit = os.getenv("ONBOARDAI_DATASET_ROOT")
    if explicit:
        return Path(explicit).expanduser().resolve()
    candidates = [
        project_root / "datset",
        project_root / "dataset",
        project_root / "Syrus2026-Resources" / "PS03",
        project_root,
    ]
    for candidate in candidates:
        if (candidate / "company_overview.md").exists():
            return candidate.resolve()
    return project_root.resolve()


class AppConfig(BaseModel):
    mode: RunMode = RunMode(os.getenv("ONBOARDAI_MODE", RunMode.DEV_MOCK))
    journey_mode: JourneyMode = JourneyMode(
        os.getenv("ONBOARDAI_JOURNEY_MODE", JourneyMode.GUIDED_PRODUCTIVITY_FIRST)
    )
    sandbox_backend: str = os.getenv("ONBOARDAI_SANDBOX_BACKEND", "mock")
    project_root: Path = Path(os.getenv("ONBOARDAI_PROJECT_ROOT", ".")).resolve()
    dataset_root: Path | None = None
    vector_backend: VectorBackend = VectorBackend(
        os.getenv("ONBOARDAI_VECTOR_BACKEND", VectorBackend.MEMORY)
    )
    qdrant_path: Path = Path(os.getenv("ONBOARDAI_QDRANT_PATH", ".cache/qdrant")).resolve()
    qdrant_url: str = os.getenv("ONBOARDAI_QDRANT_URL", "http://localhost:6333")
    qdrant_collection: str = os.getenv("ONBOARDAI_QDRANT_COLLECTION", "onboardai_kb")
    retrieval_threshold: float = float(os.getenv("ONBOARDAI_RETRIEVAL_THRESHOLD", "0.2"))
    embedding_backend: EmbeddingBackend = EmbeddingBackend(
        os.getenv("ONBOARDAI_EMBEDDING_BACKEND", EmbeddingBackend.HASH)
    )
    e2b_api_key: str | None = os.getenv("E2B_API_KEY")
    e2b_timeout_seconds: int = int(os.getenv("ONBOARDAI_E2B_TIMEOUT_SECONDS", "900"))
    llm_backend: str = os.getenv("ONBOARDAI_LLM_BACKEND", "groq")
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_model: str = os.getenv("ONBOARDAI_GROQ_MODEL", "llama-3.3-70b-versatile")
    mistral_api_key: str | None = os.getenv("MISTRAL_API_KEY")
    mistral_model: str = os.getenv("ONBOARDAI_MISTRAL_MODEL", "mistral-small-latest")
    ollama_host: str = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    browser_backend: str = os.getenv("ONBOARDAI_BROWSER_BACKEND", "mock")
    browser_headless: bool = os.getenv("ONBOARDAI_BROWSER_HEADLESS", "true").lower() == "true"
    github_org_url: str = os.getenv(
        "ONBOARDAI_GITHUB_ORG_URL", "https://github.com/NovaByte-Technologies"
    )
    github_token: str | None = os.getenv("GITHUB_TOKEN")
    slack_workspace_url: str = os.getenv(
        "ONBOARDAI_SLACK_WORKSPACE_URL", "https://novabyte-demo.slack.com"
    )
    jira_url: str = os.getenv("ONBOARDAI_JIRA_URL", "https://novabytetechnologies.atlassian.net")
    atlassian_email: str | None = os.getenv("ONBOARDAI_ATLASSIAN_EMAIL")
    atlassian_api_token: str | None = os.getenv("ONBOARDAI_ATLASSIAN_API_TOKEN")
    atlassian_cloud_id: str | None = os.getenv(
        "ONBOARDAI_ATLASSIAN_CLOUD_ID", "3bb1f4f8-ab91-436b-a8a7-4be6ee1a0611"
    )
    jira_project_key: str = os.getenv("ONBOARDAI_JIRA_PROJECT_KEY", "FLOW")
    local_machine_root: Path = Path(
        os.getenv("ONBOARDAI_LOCAL_MACHINE_ROOT", ".cache/local_machine")
    ).resolve()
    outputs_dir: Path = Field(default_factory=lambda: Path("outputs/completion_reports").resolve())

    def model_post_init(self, __context) -> None:
        if self.dataset_root is None:
            self.dataset_root = detect_dataset_root(self.project_root)
        else:
            self.dataset_root = Path(self.dataset_root).expanduser().resolve()

    def validate_runtime(self) -> None:
        if self.mode == RunMode.DEMO_REAL and not self.e2b_api_key:
            raise RuntimeError("demo_real mode requires E2B_API_KEY for live sandbox use.")
        if self.llm_backend == "groq" and not self.groq_api_key:
            raise RuntimeError("llm_backend=groq requires GROQ_API_KEY.")
        if self.llm_backend == "mistral" and not self.mistral_api_key:
            raise RuntimeError("llm_backend=mistral requires MISTRAL_API_KEY.")

    def ensure_directories(self) -> None:
        self.qdrant_path.mkdir(parents=True, exist_ok=True)
        self.local_machine_root.mkdir(parents=True, exist_ok=True)
        self.outputs_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    config = AppConfig()
    config.ensure_directories()
    return config
