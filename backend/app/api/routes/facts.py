"""Facts API routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import Entity, Evidence, ExtractionStatus, Fact, FactMention, Relationship
from app.db.session import get_db
from app.schemas.schemas import EvidenceOut, FactOut, FactWithEvidence

router = APIRouter(prefix="/api/facts", tags=["facts"])


def _fact_to_out(fact: Fact, entity_name: Optional[str] = None, evidence_count: int = 0, relationship_count: int = 0) -> FactOut:
    return FactOut(
        id=fact.id,
        subject_entity_id=fact.subject_entity_id,
        subject_name=entity_name,
        predicate=fact.predicate,
        object_type=fact.object_type,
        object_text=fact.object_text,
        numeric_value=float(fact.numeric_value) if fact.numeric_value is not None else None,
        normalized_value=float(fact.normalized_value) if fact.normalized_value is not None else None,
        unit=fact.unit,
        normalized_unit=fact.normalized_unit,
        currency=fact.currency,
        temporal_scope=fact.temporal_scope,
        geographic_scope=fact.geographic_scope,
        population_scope=fact.population_scope,
        methodology=fact.methodology,
        qualifiers=fact.qualifiers,
        modality=fact.modality,
        confidence=fact.confidence,
        extraction_status=fact.extraction_status,
        uncertainty_reasons=fact.uncertainty_reasons or [],
        primary_document_id=fact.primary_document_id,
        evidence_count=evidence_count,
        relationship_count=relationship_count,
        created_at=fact.created_at,
    )


@router.get("", response_model=dict)
async def list_facts(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
    status: Optional[str] = Query(None),
    document_id: Optional[str] = Query(None),
    predicate: Optional[str] = Query(None),
    min_confidence: float = Query(0.0),
) -> dict:
    stmt = select(Fact)
    if status:
        stmt = stmt.where(Fact.extraction_status == status)
    if document_id:
        stmt = stmt.where(Fact.primary_document_id == document_id)
    if predicate:
        stmt = stmt.where(Fact.predicate.ilike(f"%{predicate}%"))
    if min_confidence > 0:
        stmt = stmt.where(Fact.confidence >= min_confidence)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(total_stmt)).scalar_one()

    stmt = stmt.offset(skip).limit(limit).order_by(Fact.confidence.desc())
    result = await db.execute(stmt)
    facts = list(result.scalars().all())

    # Get entity names and counts
    fact_outs = []
    for fact in facts:
        entity_name = None
        if fact.subject_entity_id:
            ent_stmt = select(Entity.canonical_name).where(Entity.id == fact.subject_entity_id)
            entity_name = (await db.execute(ent_stmt)).scalar_one_or_none()

        ev_count_stmt = select(func.count(FactMention.id)).where(FactMention.fact_id == fact.id)
        ev_count = (await db.execute(ev_count_stmt)).scalar_one()

        rel_count_stmt = select(func.count(Relationship.id)).where(
            (Relationship.fact_a_id == fact.id) | (Relationship.fact_b_id == fact.id)
        )
        rel_count = (await db.execute(rel_count_stmt)).scalar_one()

        fact_outs.append(_fact_to_out(fact, entity_name, ev_count, rel_count))

    return {"items": [f.model_dump() for f in fact_outs], "total": total}


@router.get("/{fact_id}", response_model=FactOut)
async def get_fact(fact_id: str, db: AsyncSession = Depends(get_db)) -> FactOut:
    stmt = select(Fact).where(Fact.id == fact_id)
    fact = (await db.execute(stmt)).scalar_one_or_none()
    if not fact:
        raise HTTPException(404, "Fact not found.")

    entity_name = None
    if fact.subject_entity_id:
        ent_stmt = select(Entity.canonical_name).where(Entity.id == fact.subject_entity_id)
        entity_name = (await db.execute(ent_stmt)).scalar_one_or_none()

    ev_count_stmt = select(func.count(FactMention.id)).where(FactMention.fact_id == fact.id)
    ev_count = (await db.execute(ev_count_stmt)).scalar_one()
    rel_count_stmt = select(func.count(Relationship.id)).where(
        (Relationship.fact_a_id == fact.id) | (Relationship.fact_b_id == fact.id)
    )
    rel_count = (await db.execute(rel_count_stmt)).scalar_one()

    return _fact_to_out(fact, entity_name, ev_count, rel_count)


@router.get("/{fact_id}/evidence", response_model=list[EvidenceOut])
async def get_fact_evidence(fact_id: str, db: AsyncSession = Depends(get_db)) -> list[EvidenceOut]:
    stmt = (
        select(Evidence)
        .join(FactMention, FactMention.evidence_id == Evidence.id)
        .where(FactMention.fact_id == fact_id)
    )
    result = await db.execute(stmt)
    evidences = list(result.scalars().all())
    if not evidences:
        # Check fact exists
        fact_exists = (await db.execute(select(Fact.id).where(Fact.id == fact_id))).scalar_one_or_none()
        if not fact_exists:
            raise HTTPException(404, "Fact not found.")
    return [EvidenceOut.model_validate(e) for e in evidences]
