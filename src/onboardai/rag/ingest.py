from __future__ import annotations

from onboardai.content.parser import chunk_markdown
from onboardai.content.registry import build_default_registry
from onboardai.models import ContentTier, KnowledgeChunk


def load_searchable_chunks(dataset_root) -> list[KnowledgeChunk]:
    registry = build_default_registry(dataset_root)
    chunks: list[KnowledgeChunk] = []
    for content_file in registry:
        if content_file.tier != ContentTier.RAG or not content_file.searchable:
            continue
        chunks.extend(chunk_markdown(content_file.path))
    return chunks
