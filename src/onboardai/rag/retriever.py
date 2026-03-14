from __future__ import annotations

from pathlib import Path

from onboardai.config import detect_dataset_root
from onboardai.adapters.vector_store import VectorStoreAdapter
from onboardai.models import EmployeeProfile, SearchHit
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

    @staticmethod
    def format_citations(hits: list[SearchHit]) -> list[str]:
        return [f"{Path(hit.chunk.source_path).name}: {hit.chunk.title}" for hit in hits]
