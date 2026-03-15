from __future__ import annotations

from pathlib import Path

from onboardai.config import detect_dataset_root
from onboardai.adapters.vector_store import VectorStoreAdapter
from onboardai.models import ChecklistTask, EmployeeProfile, SearchHit
from onboardai.rag.ingest import load_searchable_chunks


class KnowledgeRetriever:
    def __init__(self, dataset_root, vector_store: VectorStoreAdapter) -> None:
        candidate = Path(dataset_root)
        if not (candidate / "company_overview.md").exists():
            candidate = detect_dataset_root(candidate)
        self.dataset_root = candidate
        self.vector_store = vector_store
        self._indexed = False

    def ensure_index(self) -> None:
        if self._indexed:
            return
        self.vector_store.upsert_documents(load_searchable_chunks(self.dataset_root))
        self._indexed = True

    def query(
        self,
        question: str,
        *,
        profile: EmployeeProfile | None = None,
        limit: int = 3,
    ) -> list[SearchHit]:
        self.ensure_index()
        enriched = question
        if profile:
            enriched = f"{question}\nContext: {' '.join(profile.search_terms())}"
        return self.vector_store.query(enriched, limit=limit)

    def query_for_task(
        self,
        task: ChecklistTask,
        *,
        profile: EmployeeProfile | None = None,
        message: str | None = None,
        limit: int = 2,
    ) -> list[SearchHit]:
        preferred_sources = self._preferred_sources_for_task(task)
        question = f"{task.title}\nCategory: {task.category}\nPhase: {task.display_phase.value}"
        if message:
            question = f"{question}\nQuestion: {message}"
        candidate_hits = self.query(question, profile=profile, limit=max(limit * 4, 8))
        scored_hits: list[tuple[float, SearchHit]] = []
        for hit in candidate_hits:
            adjusted = hit.score
            source_name = Path(hit.chunk.source_path).name
            if source_name in preferred_sources:
                adjusted += 0.35
            if task.source_section and task.source_section.lower() in hit.chunk.title.lower():
                adjusted += 0.1
            scored_hits.append((adjusted, hit))
        scored_hits.sort(key=lambda item: item[0], reverse=True)
        return [hit for _, hit in scored_hits[:limit]]

    @staticmethod
    def format_citations(hits: list[SearchHit]) -> list[str]:
        return [f"{Path(hit.chunk.source_path).name}: {hit.chunk.title}" for hit in hits]

    @staticmethod
    def _preferred_sources_for_task(task: ChecklistTask) -> set[str]:
        title = task.title.lower()
        category = task.category.lower()
        if task.task_id.startswith(("BI-", "JFR-", "JBP-", "SBN-", "SDO-", "JFS-")) and category in {
            "environment setup",
            "verification",
            "exploration",
        }:
            return {"setup_guides.md"}
        if "architecture" in title:
            return {"architecture_documentation.md"}
        if any(token in title for token in ("api standards", "pr guidelines", "branching", "code review", "deployment", "security")):
            return {"engineering_standards.md"}
        if any(token in title for token in ("policy", "training", "nda", "handbook", "privacy", "conduct")):
            return {"policies.md"}
        if any(token in title for token in ("manager", "mentor", "who do i contact", "escalate")):
            return {"org_structure.md", "onboarding_faq.md"}
        if task.automation_mode.value == "knowledge":
            return {"onboarding_faq.md", "company_overview.md"}
        return {"company_overview.md", "onboarding_faq.md"}
