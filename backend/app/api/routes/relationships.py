"""Relationships and reconciliation routes."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.facts import _fact_to_out
from app.db.models import Entity, Evidence, Fact, FactMention, Relationship, RelationshipType
from app.db.session import get_db
from app.schemas.schemas import FactOut, RelationshipOut

router = APIRouter(prefix="/api/relationships", tags=["relationships"])


async def _rel_to_out(rel: Relationship, db: AsyncSession, include_facts: bool = True) -> RelationshipOut:
    fact_a_out = None
    fact_b_out = None
    if include_facts:
        fact_a = (await db.execute(select(Fact).where(Fact.id == rel.fact_a_id))).scalar_one_or_none()
        fact_b = (await db.execute(select(Fact).where(Fact.id == rel.fact_b_id))).scalar_one_or_none()
        if fact_a:
            ent_a = None
            if fact_a.subject_entity_id:
                ent_a = (await db.execute(select(Entity.canonical_name).where(Entity.id == fact_a.subject_entity_id))).scalar_one_or_none()
            fact_a_out = _fact_to_out(fact_a, ent_a, 0, 0)
        if fact_b:
            ent_b = None
            if fact_b.subject_entity_id:
                ent_b = (await db.execute(select(Entity.canonical_name).where(Entity.id == fact_b.subject_entity_id))).scalar_one_or_none()
            fact_b_out = _fact_to_out(fact_b, ent_b, 0, 0)

    return RelationshipOut(
        id=rel.id,
        fact_a_id=rel.fact_a_id,
        fact_b_id=rel.fact_b_id,
        fact_a=fact_a_out,
        fact_b=fact_b_out,
        relationship_type=rel.relationship_type,
        confidence=rel.confidence,
        reasoning=rel.reasoning,
        context_explanation=rel.context_explanation,
        context_factors=rel.context_factors or [],
        reasoning_trace=rel.reasoning_trace,
        numeric_delta=float(rel.numeric_delta) if rel.numeric_delta is not None else None,
        numeric_delta_pct=float(rel.numeric_delta_pct) if rel.numeric_delta_pct is not None else None,
        llm_assisted=rel.llm_assisted,
        created_at=rel.created_at,
    )


@router.get("", response_model=dict)
async def list_relationships(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
    rel_type: Optional[str] = Query(None, alias="type"),
    min_confidence: float = Query(0.0),
) -> dict:
    stmt = select(Relationship)
    if rel_type:
        stmt = stmt.where(Relationship.relationship_type == rel_type)
    if min_confidence > 0:
        stmt = stmt.where(Relationship.confidence >= min_confidence)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.offset(skip).limit(limit).order_by(Relationship.confidence.desc())
    result = await db.execute(stmt)
    rels = list(result.scalars().all())

    items = [await _rel_to_out(r, db, include_facts=True) for r in rels]
    return {"items": [i.model_dump() for i in items], "total": total}


@router.get("/{rel_id}", response_model=RelationshipOut)
async def get_relationship(rel_id: str, db: AsyncSession = Depends(get_db)) -> RelationshipOut:
    stmt = select(Relationship).where(Relationship.id == rel_id)
    rel = (await db.execute(stmt)).scalar_one_or_none()
    if not rel:
        raise HTTPException(404, "Relationship not found.")
    return await _rel_to_out(rel, db, include_facts=True)
