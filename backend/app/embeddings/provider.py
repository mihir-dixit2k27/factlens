"""
Embedding provider abstraction and storage.
Default: sentence-transformers all-MiniLM-L6-v2 (384-dim, runs locally).
Stored in PostgreSQL via pgvector.
"""
from __future__ import annotations

import time
from typing import Protocol, runtime_checkable

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import embedding_duration_seconds
from app.db.models import Fact, FactEmbedding

logger = get_logger(__name__)
settings = get_settings()


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding backends. Swap implementations without changing pipelines."""

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of texts. Returns list of float vectors."""
        ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...


class SentenceTransformerProvider:
    """
    Local embedding using sentence-transformers.
    Model: all-MiniLM-L6-v2 (384-dim, Apache-2 license, no external API needed).
    """

    def __init__(self, model_name: str | None = None) -> None:
        from sentence_transformers import SentenceTransformer  # type: ignore

        _model_name = model_name or settings.embedding_model
        self._model = SentenceTransformer(_model_name)
        self._model_name = _model_name
        self._dim = self._model.get_sentence_embedding_dimension()
        logger.info("embedding_model_loaded", model=_model_name, dim=self._dim)

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vecs = self._model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vecs.tolist()

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimension(self) -> int:
        return self._dim


def _fact_to_embed_text(fact: Fact, entity_name: str | None = None) -> str:
    """
    Build a compact text representation of a fact for embedding.
    Format: "<entity> <predicate> <object_text> <temporal_scope>"
    """
    parts: list[str] = []
    if entity_name:
        parts.append(entity_name)
    parts.append(fact.predicate)
    parts.append(fact.object_text)
    if fact.temporal_scope and isinstance(fact.temporal_scope, dict):
        label = fact.temporal_scope.get("label") or fact.temporal_scope.get("start", "")
        if label:
            parts.append(str(label))
    if fact.geographic_scope:
        parts.append(fact.geographic_scope)
    return " ".join(parts)


class EmbeddingStore:
    """Manages embedding generation and persistence to pgvector."""

    def __init__(self, provider: EmbeddingProvider) -> None:
        self._provider = provider

    async def embed_new_facts(
        self,
        session: AsyncSession,
        fact_ids: list[str] | None = None,
        batch_size: int | None = None,
    ) -> int:
        """
        Generate and store embeddings for facts that don't have them yet.
        If fact_ids is provided, only embed those facts.
        Returns count of embeddings created.
        """
        bs = batch_size or settings.embedding_batch_size

        # Find facts without embeddings
        stmt = select(Fact).outerjoin(FactEmbedding, Fact.id == FactEmbedding.fact_id)
        if fact_ids:
            stmt = stmt.where(Fact.id.in_(fact_ids))
        stmt = stmt.where(FactEmbedding.id.is_(None))

        result = await session.execute(stmt)
        facts: list[Fact] = list(result.scalars().all())

        if not facts:
            return 0

        total = 0
        for i in range(0, len(facts), bs):
            batch = facts[i : i + bs]
            texts = [_fact_to_embed_text(f) for f in batch]

            t0 = time.perf_counter()
            try:
                vectors = self._provider.embed(texts)
                elapsed = time.perf_counter() - t0
                embedding_duration_seconds.labels(batch_size=str(len(batch))).observe(elapsed)
            except Exception as exc:
                logger.error("embedding_error", error=str(exc), batch_size=len(batch))
                continue

            for fact, vector in zip(batch, vectors):
                emb = FactEmbedding(
                    fact_id=fact.id,
                    model_name=self._provider.model_name,
                    vector=vector,
                )
                session.add(emb)

            await session.flush()
            total += len(batch)
            logger.info("embeddings_created", count=len(batch), offset=i)

        return total
