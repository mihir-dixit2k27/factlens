"""
Fact Reconciliation Ledger — the signature feature of FactLens.
Orchestrates the full reconciliation cycle for a pair of candidate facts:
  RAW_CLAIM -> NORMALIZED_CLAIM -> RELATED_CLAIMS -> EVIDENCE -> CONTEXT ->
  RELATIONSHIP -> FINAL_RECONCILIATION

Also builds the 10-step reasoning trace exposed in the UI.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import (
    contradictions_detected_total,
    facts_linked_total,
    relationships_created_total,
)
from app.db.models import Evidence, Fact, FactMention, Relationship, RelationshipType
from app.embeddings.provider import EmbeddingProvider
from app.extraction.llm_provider import LLMProvider
from app.reconciliation.comparison_engine import ComparisonResult, compare
from app.retrieval.hybrid import find_candidate_pairs

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class ReasoningTrace:
    """10-step reasoning trace for cross-document fact pair."""
    step_1_candidates: str = ""
    step_2_semantic_similarity: Optional[float] = None
    step_3_entity_match: Optional[bool] = None
    step_4_predicate_match: Optional[float] = None
    step_5_time_comparison: str = ""
    step_6_scope_comparison: str = ""
    step_7_unit_comparison: str = ""
    step_8_numeric_comparison: str = ""
    step_9_final_relationship: str = ""
    step_10_confidence: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "step_1_candidates": self.step_1_candidates,
            "step_2_semantic_similarity": self.step_2_semantic_similarity,
            "step_3_entity_match": self.step_3_entity_match,
            "step_4_predicate_match": self.step_4_predicate_match,
            "step_5_time_comparison": self.step_5_time_comparison,
            "step_6_scope_comparison": self.step_6_scope_comparison,
            "step_7_unit_comparison": self.step_7_unit_comparison,
            "step_8_numeric_comparison": self.step_8_numeric_comparison,
            "step_9_final_relationship": self.step_9_final_relationship,
            "step_10_confidence": self.step_10_confidence,
        }


def _predicate_similarity(pred_a: str, pred_b: str) -> float:
    words_a = set(pred_a.lower().split())
    words_b = set(pred_b.lower().split())
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / max(len(words_a), len(words_b))


async def _get_primary_evidence(session: AsyncSession, fact: Fact) -> Optional[str]:
    """Retrieve the primary evidence text for a fact."""
    stmt = (
        select(Evidence)
        .join(FactMention, FactMention.evidence_id == Evidence.id)
        .where(FactMention.fact_id == fact.id)
        .limit(1)
    )
    result = await session.execute(stmt)
    ev = result.scalar_one_or_none()
    return ev.exact_text if ev else ""


async def _pair_exists(session: AsyncSession, id_a: str, id_b: str) -> bool:
    """Check if a relationship between these two facts already exists."""
    stmt = select(Relationship).where(
        ((Relationship.fact_a_id == id_a) & (Relationship.fact_b_id == id_b))
        | ((Relationship.fact_a_id == id_b) & (Relationship.fact_b_id == id_a))
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none() is not None


async def reconcile_fact_pair(
    session: AsyncSession,
    llm: LLMProvider,
    fact_a: Fact,
    fact_b: Fact,
    semantic_similarity: float = 0.0,
) -> Optional[Relationship]:
    """
    Run the full reconciliation pipeline for a candidate fact pair.
    Returns the created Relationship (or None if skipped).
    """
    # Don't compare a fact with itself or same-document facts (configurable)
    if fact_a.id == fact_b.id:
        return None
    if fact_a.primary_document_id == fact_b.primary_document_id:
        return None  # Only cross-document relationships for now

    # Skip if already reconciled
    if await _pair_exists(session, fact_a.id, fact_b.id):
        logger.debug("relationship_already_exists", fact_a=fact_a.id, fact_b=fact_b.id)
        return None

    t0 = time.perf_counter()

    # Build reasoning trace
    trace = ReasoningTrace()
    trace.step_1_candidates = (
        f"Fact A: [{fact_a.predicate}] {fact_a.object_text} | "
        f"Fact B: [{fact_b.predicate}] {fact_b.object_text}"
    )
    trace.step_2_semantic_similarity = semantic_similarity
    trace.step_3_entity_match = (
        fact_a.subject_entity_id is not None
        and fact_a.subject_entity_id == fact_b.subject_entity_id
    )
    trace.step_4_predicate_match = _predicate_similarity(fact_a.predicate, fact_b.predicate)

    # Temporal check
    ts_a = fact_a.temporal_scope
    ts_b = fact_b.temporal_scope
    if ts_a and ts_b:
        trace.step_5_time_comparison = (
            f"A: {ts_a.get('label', ts_a.get('start', 'unknown'))} | "
            f"B: {ts_b.get('label', ts_b.get('start', 'unknown'))}"
        )
    else:
        trace.step_5_time_comparison = "Unknown temporal scope"

    # Scope check
    trace.step_6_scope_comparison = (
        f"Geo A: {fact_a.geographic_scope or 'unspecified'} | "
        f"Geo B: {fact_b.geographic_scope or 'unspecified'}"
    )

    # Unit check
    trace.step_7_unit_comparison = (
        f"Unit A: {fact_a.unit or 'none'} | Unit B: {fact_b.unit or 'none'}"
    )

    # Numeric check
    val_a = fact_a.normalized_value or fact_a.numeric_value
    val_b = fact_b.normalized_value or fact_b.numeric_value
    if val_a is not None and val_b is not None:
        delta_pct = abs(float(val_a) - float(val_b)) / max(abs(float(val_a)), abs(float(val_b)), 1) * 100
        trace.step_8_numeric_comparison = (
            f"A={float(val_a):,.4g} | B={float(val_b):,.4g} | delta={delta_pct:.1f}%"
        )
    else:
        trace.step_8_numeric_comparison = "No numeric values available"

    # Deterministic comparison
    comparison: ComparisonResult = compare(fact_a, fact_b)

    # If deterministic result is UNCERTAIN, use LLM to refine
    llm_assisted = False
    llm_classification = None
    if not comparison.deterministic or comparison.relationship_type == RelationshipType.UNCERTAIN:
        try:
            ev_a = await _get_primary_evidence(session, fact_a)
            ev_b = await _get_primary_evidence(session, fact_b)
            fact_a_text = f"{fact_a.predicate}: {fact_a.object_text}"
            fact_b_text = f"{fact_b.predicate}: {fact_b.object_text}"
            llm_classification = await llm.classify_relationship(
                fact_a_text=fact_a_text,
                fact_b_text=fact_b_text,
                evidence_a=ev_a or "",
                evidence_b=ev_b or "",
                deterministic_hint=comparison.relationship_type.value,
            )
            llm_assisted = True
            # Use LLM result if it has higher confidence
            if llm_classification.confidence > comparison.confidence:
                final_type = RelationshipType(llm_classification.relationship_type)
                final_confidence = llm_classification.confidence
                reasoning = llm_classification.reasoning
                context_explanation = llm_classification.context_explanation
                context_factors = llm_classification.context_factors
            else:
                final_type = comparison.relationship_type
                final_confidence = comparison.confidence
                reasoning = comparison.reasoning
                context_explanation = ""
                context_factors = comparison.context_factors
        except Exception as exc:
            logger.warning("llm_classification_failed", error=str(exc))
            final_type = comparison.relationship_type
            final_confidence = comparison.confidence
            reasoning = comparison.reasoning
            context_explanation = ""
            context_factors = comparison.context_factors
    else:
        final_type = comparison.relationship_type
        final_confidence = comparison.confidence
        reasoning = comparison.reasoning
        context_explanation = ""
        context_factors = comparison.context_factors

    trace.step_9_final_relationship = final_type.value
    trace.step_10_confidence = final_confidence

    # Update metrics
    facts_linked_total.inc()
    relationships_created_total.labels(relationship_type=final_type.value).inc()
    if final_type == RelationshipType.CONTRADICTS:
        contradictions_detected_total.inc()

    rel = Relationship(
        fact_a_id=fact_a.id,
        fact_b_id=fact_b.id,
        relationship_type=final_type,
        confidence=final_confidence,
        reasoning=reasoning,
        context_explanation=context_explanation or comparison.reasoning,
        context_factors=context_factors,
        reasoning_trace=trace.to_dict(),
        numeric_delta=float(comparison.numeric_delta) if comparison.numeric_delta is not None else None,
        numeric_delta_pct=float(comparison.numeric_delta_pct) if comparison.numeric_delta_pct is not None else None,
        llm_assisted=llm_assisted,
    )
    session.add(rel)
    await session.flush()

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        "relationship_created",
        type=final_type.value,
        confidence=round(final_confidence, 3),
        llm_assisted=llm_assisted,
        elapsed_ms=round(elapsed, 1),
    )
    return rel


async def run_candidate_linking(
    session: AsyncSession,
    llm: LLMProvider,
    embedding_provider: EmbeddingProvider,
    fact_ids: Optional[list[str]] = None,
    similarity_threshold: float = 0.65,
) -> int:
    """
    For each fact (or specific fact_ids), find candidate pairs and reconcile.
    Returns total relationships created.
    """
    from app.db.models import ExtractionStatus

    stmt = select(Fact).where(
        Fact.extraction_status != ExtractionStatus.FAILED_EXTRACTION
    )
    if fact_ids:
        stmt = stmt.where(Fact.id.in_(fact_ids))

    result = await session.execute(stmt)
    facts: list[Fact] = list(result.scalars().all())

    total_relationships = 0
    for fact in facts:
        try:
            candidates = await find_candidate_pairs(
                session, embedding_provider, fact, similarity_threshold
            )
            for candidate_fact, sim_score in candidates:
                rel = await reconcile_fact_pair(session, llm, fact, candidate_fact, sim_score)
                if rel:
                    total_relationships += 1
        except Exception as exc:
            logger.error("candidate_linking_error", fact_id=fact.id, error=str(exc))

    logger.info("candidate_linking_complete", relationships_created=total_relationships)
    return total_relationships
