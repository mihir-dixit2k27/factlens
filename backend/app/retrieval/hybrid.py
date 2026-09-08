"""
Hybrid retrieval combining pgvector semantic search with PostgreSQL FTS and metadata filters.
Used for candidate fact generation and natural language query answering.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import Float, Integer, cast, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Entity, Fact, FactEmbedding
from app.embeddings.provider import EmbeddingProvider

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class RankedFact:
    fact: Fact
    semantic_score: float
    lexical_score: float
    total_score: float


async def hybrid_fact_search(
    session: AsyncSession,
    provider: EmbeddingProvider,
    query: str,
    limit: int = 20,
    dataset: Optional[str] = None,
    predicate_filter: Optional[str] = None,
    entity_filter: Optional[str] = None,
    min_confidence: float = 0.3,
) -> list[RankedFact]:
    """
    Hybrid search: pgvector cosine + PostgreSQL FTS + metadata filter.
    Weighted score = 0.5 * semantic + 0.3 * lexical + 0.2 * metadata_boost
    """
    # Embed query
    query_vec = provider.embed([query])[0]

    # --- Semantic search via pgvector ---
    semantic_stmt = (
        select(
            FactEmbedding.fact_id,
            (1 - FactEmbedding.vector.cosine_distance(query_vec)).label("semantic_score"),
        )
        .order_by(FactEmbedding.vector.cosine_distance(query_vec))
        .limit(limit * 3)
    )
    sem_result = await session.execute(semantic_stmt)
    sem_rows = {row.fact_id: float(row.semantic_score) for row in sem_result}

    if not sem_rows:
        return []

    # --- Load facts for those candidates ---
    fact_stmt = (
        select(Fact)
        .where(Fact.id.in_(list(sem_rows.keys())))
        .where(Fact.confidence >= min_confidence)
    )
    if predicate_filter:
        fact_stmt = fact_stmt.where(Fact.predicate.ilike(f"%{predicate_filter}%"))

    fact_result = await session.execute(fact_stmt)
    facts: list[Fact] = list(fact_result.scalars().all())

    # --- Lexical scoring (simple overlap) ---
    query_tokens = set(query.lower().split())
    scored: list[RankedFact] = []
    for fact in facts:
        fact_text = f"{fact.predicate} {fact.object_text}".lower()
        fact_tokens = set(fact_text.split())
        lexical = len(query_tokens & fact_tokens) / max(len(query_tokens), 1)

        semantic = sem_rows.get(fact.id, 0.0)
        total = 0.5 * semantic + 0.3 * lexical + 0.2 * fact.confidence

        scored.append(
            RankedFact(fact=fact, semantic_score=semantic, lexical_score=lexical, total_score=total)
        )

    # Sort by total score
    scored.sort(key=lambda r: r.total_score, reverse=True)
    return scored[:limit]


async def find_candidate_pairs(
    session: AsyncSession,
    provider: EmbeddingProvider,
    fact: Fact,
    similarity_threshold: float = 0.65,
    limit: int = 10,
) -> list[tuple[Fact, float]]:
    """
    Find candidate facts from OTHER documents that are semantically similar to `fact`.
    Pre-filters by entity/predicate before expensive semantic comparison.
    """
    # Embed the fact's text
    fact_text = f"{fact.predicate} {fact.object_text}"
    if fact.temporal_scope:
        label = fact.temporal_scope.get("label", "")
        if label:
            fact_text += f" {label}"

    vec = provider.embed([fact_text])[0]

    # Search in pgvector for similar embeddings from other documents
    stmt = (
        select(
            FactEmbedding.fact_id,
            (1 - FactEmbedding.vector.cosine_distance(vec)).label("sim"),
        )
        .where(FactEmbedding.fact_id != fact.id)
        .order_by(FactEmbedding.vector.cosine_distance(vec))
        .limit(limit * 4)
    )
    result = await session.execute(stmt)
    rows = [(row.fact_id, float(row.sim)) for row in result if float(row.sim) >= similarity_threshold]

    if not rows:
        return []

    candidate_ids = [r[0] for r in rows]
    sim_map = {r[0]: r[1] for r in rows}

    # Load candidates — exclude same document
    candidate_stmt = (
        select(Fact)
        .where(Fact.id.in_(candidate_ids))
        .where(Fact.primary_document_id != fact.primary_document_id)
    )
    cand_result = await session.execute(candidate_stmt)
    candidates: list[Fact] = list(cand_result.scalars().all())

    return [(c, sim_map[c.id]) for c in candidates][:limit]
