"""
Fact extractor: orchestrates LLM extraction, evidence validation, normalization,
and DB persistence for a single chunk.
"""
from __future__ import annotations

import time
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import facts_extracted_total
from app.db.models import (
    Chunk, Entity, Evidence, ExtractionStatus, Fact, FactMention, ObjectType,
)
from app.entity_resolution.resolver import EntityResolver
from app.extraction.evidence_validator import validate_fact_grounding
from app.extraction.llm_provider import ExtractedFactRaw, ExtractionResponse, LLMProvider
from app.normalization.numeric import normalize_numeric
from app.normalization.temporal import parse_temporal_scope
from app.normalization.units import normalize_unit

logger = get_logger(__name__)
settings = get_settings()


def _map_object_type(raw: str) -> ObjectType:
    mapping = {
        "NUMERIC": ObjectType.NUMERIC,
        "PERCENTAGE": ObjectType.PERCENTAGE,
        "MONETARY": ObjectType.MONETARY,
        "COUNT": ObjectType.COUNT,
        "RATIO": ObjectType.RATIO,
        "DATE": ObjectType.DATE,
        "TEXT": ObjectType.TEXT,
        "BOOLEAN": ObjectType.BOOLEAN,
        "RANGE": ObjectType.RANGE,
    }
    return mapping.get(raw.upper(), ObjectType.TEXT)


def _map_extraction_status(confidence: float, uncertainty_reasons: list[str]) -> ExtractionStatus:
    if confidence >= 0.85 and not uncertainty_reasons:
        return ExtractionStatus.TRUSTED
    elif confidence >= 0.60:
        return ExtractionStatus.PROBABLE
    elif confidence >= 0.40:
        return ExtractionStatus.UNCERTAIN
    else:
        return ExtractionStatus.FAILED_EXTRACTION


async def _get_or_create_entity(
    session: AsyncSession,
    canonical_name: str,
    entity_type: str,
    resolver: EntityResolver,
) -> Optional[Entity]:
    """Resolve entity name and upsert into DB. Safe against duplicate inserts."""
    from sqlalchemy import select, text
    from sqlalchemy.exc import IntegrityError

    resolved = resolver.resolve(canonical_name, entity_type)
    stmt = select(Entity).where(Entity.canonical_name == resolved.canonical_name)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing:
        all_aliases = list(set((existing.aliases or []) + resolved.aliases))
        existing.aliases = all_aliases
        return existing

    try:
        # Use a nested savepoint so an IntegrityError rolls back only this insert
        async with session.begin_nested():
            entity = Entity(
                canonical_name=resolved.canonical_name,
                entity_type=entity_type,
                aliases=resolved.aliases,
            )
            session.add(entity)
        return entity
    except IntegrityError:
        # Another concurrent chunk already inserted this entity — just fetch it
        await session.rollback()
        result2 = await session.execute(stmt)
        return result2.scalar_one_or_none()


async def extract_and_store_facts(
    session: AsyncSession,
    llm: LLMProvider,
    chunk: Chunk,
    document_id: str,
    entity_resolver: EntityResolver,
    document_context: str = "",
) -> tuple[int, int]:
    """
    Extract facts from a chunk and persist to DB with evidence grounding.

    Returns: (facts_stored, facts_rejected)
    """
    if not chunk.text or len(chunk.text.strip()) < 30:
        return 0, 0

    t0 = time.perf_counter()
    try:
        extraction: ExtractionResponse = await llm.extract_facts(
            chunk_text=chunk.text,
            document_context=document_context,
        )
    except Exception as exc:
        logger.error("fact_extraction_error", chunk_id=chunk.id, error=str(exc))
        return 0, 0

    stored = 0
    rejected = 0

    for raw_fact in extraction.facts:
        # 1. Validate evidence grounding
        validation = validate_fact_grounding(raw_fact, chunk.text)
        if not validation.is_valid:
            logger.info(
                "fact_rejected_no_evidence",
                subject=raw_fact.subject[:80],
                predicate=raw_fact.predicate[:80],
                reason=validation.failure_reason,
            )
            rejected += 1
            facts_extracted_total.labels(status="rejected").inc()

            # Store as FAILED_EXTRACTION fact for the Failures view
            await _store_failed_fact(session, raw_fact, chunk, document_id, validation.failure_reason)
            continue

        # 2. Normalize
        num_result = None
        if raw_fact.numeric_value is not None or raw_fact.object_text:
            num_result = normalize_numeric(raw_fact.object_text)

        unit_norm = normalize_unit(raw_fact.unit)
        temporal = None
        if raw_fact.temporal_scope:
            temporal = parse_temporal_scope(raw_fact.temporal_scope)

        # 3. Determine confidence after validation
        adjusted_confidence = max(
            0.0,
            raw_fact.confidence + validation.confidence_adjustment,
        )
        status = _map_extraction_status(adjusted_confidence, raw_fact.uncertainty_reasons)

        # 4. Resolve entity
        entity: Optional[Entity] = None
        if raw_fact.subject:
            entity = await _get_or_create_entity(
                session, raw_fact.subject, "UNKNOWN", entity_resolver
            )

        # 5. Create Evidence record
        evidence = Evidence(
            document_id=document_id,
            page_number=chunk.page_number,
            block_id=str(chunk.block_ids[0]) if chunk.block_ids else None,
            chunk_id=chunk.id,
            exact_text=validation.evidence_span,
            bbox=list(chunk.bbox.values()) if chunk.bbox else None,
            extraction_method=chunk.extraction_method,
            extraction_confidence=adjusted_confidence,
        )
        session.add(evidence)
        await session.flush()

        # 6. Create Fact record
        fact = Fact(
            subject_entity_id=entity.id if entity else None,
            predicate=raw_fact.predicate,
            object_type=_map_object_type(raw_fact.object_type),
            object_text=raw_fact.object_text,
            numeric_value=(
                float(num_result.normalized_value)
                if num_result and num_result.normalized_value is not None
                else raw_fact.numeric_value
            ),
            normalized_value=(
                float(num_result.normalized_value)
                if num_result and num_result.normalized_value is not None
                else None
            ),
            unit=raw_fact.unit,
            normalized_unit=unit_norm.canonical_unit,
            currency=raw_fact.currency or (num_result.currency if num_result else None),
            temporal_scope=temporal.__dict__ if temporal else None,
            geographic_scope=raw_fact.geographic_scope,
            population_scope=raw_fact.population_scope,
            methodology=raw_fact.methodology,
            qualifiers=raw_fact.qualifiers,
            modality=raw_fact.modality,
            confidence=adjusted_confidence,
            extraction_status=status,
            uncertainty_reasons=raw_fact.uncertainty_reasons or [],
            primary_document_id=document_id,
        )
        session.add(fact)
        await session.flush()

        # 7. Link Fact <-> Evidence
        mention = FactMention(
            fact_id=fact.id,
            evidence_id=evidence.id,
            source_confidence=adjusted_confidence,
        )
        session.add(mention)

        stored += 1
        facts_extracted_total.labels(status="stored").inc()

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        "chunk_extraction_complete",
        chunk_id=chunk.id,
        stored=stored,
        rejected=rejected,
        elapsed_ms=round(elapsed, 1),
    )
    return stored, rejected


async def _store_failed_fact(
    session: AsyncSession,
    raw_fact: ExtractedFactRaw,
    chunk: Chunk,
    document_id: str,
    failure_reason: Optional[str],
) -> None:
    """Store a failed extraction attempt for the Failures & Uncertainty view."""
    # Create a minimal Evidence from whatever span was extracted
    evidence = Evidence(
        document_id=document_id,
        page_number=chunk.page_number,
        chunk_id=chunk.id,
        exact_text=(raw_fact.evidence_span or chunk.text[:200]).strip(),
        extraction_confidence=raw_fact.confidence,
    )
    session.add(evidence)
    await session.flush()

    fact = Fact(
        predicate=raw_fact.predicate or "unknown",
        object_type=ObjectType.TEXT,
        object_text=raw_fact.object_text or "",
        confidence=raw_fact.confidence,
        extraction_status=ExtractionStatus.FAILED_EXTRACTION,
        uncertainty_reasons=(raw_fact.uncertainty_reasons or []) + ([failure_reason] if failure_reason else []),
        primary_document_id=document_id,
    )
    session.add(fact)
    await session.flush()

    mention = FactMention(fact_id=fact.id, evidence_id=evidence.id, source_confidence=raw_fact.confidence)
    session.add(mention)
