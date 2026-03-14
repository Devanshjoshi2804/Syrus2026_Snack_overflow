from __future__ import annotations

from uuid import UUID

from onboardai.adapters.vector_store import (
    HashEmbeddingProvider,
    InMemoryVectorStoreAdapter,
    to_qdrant_point_id,
)
from onboardai.rag.retriever import KnowledgeRetriever


def test_retriever_returns_grounded_vpn_hit(project_root):
    retriever = KnowledgeRetriever(
        project_root,
        InMemoryVectorStoreAdapter(HashEmbeddingProvider()),
    )
    hits = retriever.query("How do I set up VPN?", limit=3)
    assert hits
    assert any(
        hit.chunk.source_path.endswith("onboarding_faq.md") or hit.chunk.source_path.endswith("policies.md")
        for hit in hits
    )


def test_qdrant_point_id_is_uuid():
    point_id = to_qdrant_point_id("company_overview:overview:0")
    assert str(UUID(point_id)) == point_id
