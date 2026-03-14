from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import NAMESPACE_URL, uuid5

from onboardai.config import AppConfig
from onboardai.models import KnowledgeChunk, SearchHit, VectorBackend


TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9\-\._]+")


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class HashEmbeddingProvider(EmbeddingProvider):
    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in TOKEN_RE.findall(text.lower()):
            bucket = hash(token) % self.dimensions
            sign = -1.0 if hash(f"sign:{token}") % 2 else 1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class SentenceTransformerEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        return list(self.model.encode(text))


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right, strict=False))
    left_norm = math.sqrt(sum(a * a for a in left)) or 1.0
    right_norm = math.sqrt(sum(b * b for b in right)) or 1.0
    return numerator / (left_norm * right_norm)


class VectorStoreAdapter(ABC):
    @abstractmethod
    def upsert_documents(self, chunks: Iterable[KnowledgeChunk]) -> None:
        raise NotImplementedError

    @abstractmethod
    def query(self, query_text: str, limit: int = 3) -> list[SearchHit]:
        raise NotImplementedError

    @abstractmethod
    def healthcheck(self) -> dict[str, str]:
        raise NotImplementedError


class InMemoryVectorStoreAdapter(VectorStoreAdapter):
    def __init__(self, embedding_provider: EmbeddingProvider) -> None:
        self.embedding_provider = embedding_provider
        self._entries: dict[str, tuple[KnowledgeChunk, list[float]]] = {}

    def upsert_documents(self, chunks: Iterable[KnowledgeChunk]) -> None:
        for chunk in chunks:
            self._entries[chunk.chunk_id] = (chunk, self.embedding_provider.embed(chunk.text))

    def query(self, query_text: str, limit: int = 3) -> list[SearchHit]:
        query_vector = self.embedding_provider.embed(query_text)
        scored = [
            SearchHit(chunk=chunk, score=_cosine_similarity(query_vector, vector))
            for chunk, vector in self._entries.values()
        ]
        scored.sort(key=lambda hit: hit.score, reverse=True)
        return scored[:limit]

    def healthcheck(self) -> dict[str, str]:
        return {"backend": "memory", "documents": str(len(self._entries))}


@dataclass
class _QdrantPayload:
    chunk_id: str
    source_path: str
    title: str
    text: str
    metadata: dict


class QdrantVectorStoreAdapter(VectorStoreAdapter):
    def __init__(
        self,
        *,
        collection_name: str,
        embedding_provider: EmbeddingProvider,
        path: Path | None = None,
        url: str | None = None,
    ) -> None:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams

        self.embedding_provider = embedding_provider
        self.collection_name = collection_name
        self.PointStruct = PointStruct
        self.client = QdrantClient(path=str(path)) if path else QdrantClient(url=url)
        dim = len(self.embedding_provider.embed("healthcheck"))
        if not self.client.collection_exists(collection_name):
            self.client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert_documents(self, chunks: Iterable[KnowledgeChunk]) -> None:
        points = []
        for chunk in chunks:
            payload = _QdrantPayload(
                chunk_id=chunk.chunk_id,
                source_path=chunk.source_path,
                title=chunk.title,
                text=chunk.text,
                metadata=chunk.metadata,
            )
            points.append(
                self.PointStruct(
                    id=to_qdrant_point_id(chunk.chunk_id),
                    vector=self.embedding_provider.embed(chunk.text),
                    payload=payload.__dict__,
                )
            )
        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)

    def query(self, query_text: str, limit: int = 3) -> list[SearchHit]:
        query_vector = self.embedding_provider.embed(query_text)
        if hasattr(self.client, "query_points"):
            response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_vector,
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )
            results = response.points
        else:
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
            )
        hits: list[SearchHit] = []
        for result in results:
            payload = result.payload or {}
            hits.append(
                SearchHit(
                    chunk=KnowledgeChunk(
                        chunk_id=payload["chunk_id"],
                        source_path=payload["source_path"],
                        title=payload["title"],
                        text=payload["text"],
                        metadata=payload.get("metadata", {}),
                    ),
                    score=float(result.score),
                )
            )
        return hits

    def healthcheck(self) -> dict[str, str]:
        return {"backend": "qdrant", "collection": self.collection_name}


def build_embedding_provider(config: AppConfig) -> EmbeddingProvider:
    if config.embedding_backend.value == "sentence_transformer":
        try:
            return SentenceTransformerEmbeddingProvider()
        except Exception:
            return HashEmbeddingProvider()
    return HashEmbeddingProvider()


def to_qdrant_point_id(chunk_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, chunk_id))


def build_vector_store(config: AppConfig) -> VectorStoreAdapter:
    embedding_provider = build_embedding_provider(config)
    if config.vector_backend == VectorBackend.MEMORY:
        return InMemoryVectorStoreAdapter(embedding_provider)
    if config.vector_backend == VectorBackend.EMBEDDED_QDRANT:
        try:
            return QdrantVectorStoreAdapter(
                collection_name=config.qdrant_collection,
                embedding_provider=embedding_provider,
                path=config.qdrant_path,
            )
        except Exception:
            return InMemoryVectorStoreAdapter(embedding_provider)
    try:
        return QdrantVectorStoreAdapter(
            collection_name=config.qdrant_collection,
            embedding_provider=embedding_provider,
            url=config.qdrant_url,
        )
    except Exception:
        return InMemoryVectorStoreAdapter(embedding_provider)
