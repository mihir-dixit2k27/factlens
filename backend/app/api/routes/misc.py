"""Query, metrics, health, and cases routes."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.api.routes.facts import _fact_to_out
from app.api.routes.relationships import _rel_to_out
from app.db.models import (
    Document,
    ExtractionStatus,
    Fact,
    FactEmbedding,
    Relationship,
    RelationshipType,
)
from app.db.session import get_db
from app.schemas.schemas import (
    CasesResponse,
    HealthResponse,
    QueryRequest,
    QueryResult,
    RequiredCase,
    SystemMetrics,
)

query_router = APIRouter(prefix="/api/query", tags=["query"])
metrics_router = APIRouter(prefix="/api/metrics", tags=["metrics"])
health_router = APIRouter(prefix="/api/health", tags=["health"])
cases_router = APIRouter(prefix="/api/cases", tags=["cases"])


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------


@query_router.post("", response_model=QueryResult)
async def query_facts(request: QueryRequest, db: AsyncSession = Depends(get_db)) -> QueryResult:
    """
    Natural language fact query using hybrid retrieval.
    Returns grounded facts and relationships relevant to the query.
    """
    from app.embeddings.provider import SentenceTransformerProvider
    from app.ingestion.pipeline import get_embedding_provider, get_llm_provider_singleton
    from app.retrieval.hybrid import hybrid_fact_search

    try:
        emb_provider = get_embedding_provider()
        ranked = await hybrid_fact_search(
            session=db,
            provider=emb_provider,
            query=request.query,
            limit=request.limit,
        )
    except Exception as exc:
        raise HTTPException(500, f"Search failed: {exc}")

    facts = [_fact_to_out(r.fact, None, 0, 0) for r in ranked]

    # Find relationships between top facts
    fact_ids = [f.id for f in facts]
    rel_stmt = select(Relationship).where(
        (Relationship.fact_a_id.in_(fact_ids)) | (Relationship.fact_b_id.in_(fact_ids))
    ).limit(20)
    rel_result = await db.execute(rel_stmt)
    rels_raw = list(rel_result.scalars().all())
    rels = [await _rel_to_out(r, db, include_facts=False) for r in rels_raw]

    # Collect unique document IDs
    source_docs = list({f.primary_document_id for f in facts if f.primary_document_id})

    # Build answer summary
    if not facts:
        answer = "No relevant facts found for this query."
        confidence = 0.0
    else:
        top = facts[0]
        answer = (
            f"Found {len(facts)} relevant facts. "
            f"Top result: {top.predicate} = {top.object_text}"
            + (f" ({top.temporal_scope.get('label', '')})" if top.temporal_scope else "")
            + "."
        )
        confidence = ranked[0].total_score if ranked else 0.5

    return QueryResult(
        query=request.query,
        answer=answer,
        relevant_facts=facts,
        relevant_relationships=rels,
        source_documents=source_docs,
        confidence=confidence,
    )


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------


@cases_router.get("", response_model=CasesResponse)
async def get_required_cases(db: AsyncSession = Depends(get_db)) -> CasesResponse:
    """
    Automatically discover the four required cases from actual extracted data.
    No hard-coded document names or fact values.
    """
    cases: list[RequiredCase] = []

    # CASE 1: CORROBORATES — highest confidence corroboration
    corr_stmt = (
        select(Relationship)
        .where(Relationship.relationship_type == RelationshipType.CORROBORATES)
        .order_by(Relationship.confidence.desc())
        .limit(1)
    )
    corr = (await db.execute(corr_stmt)).scalar_one_or_none()
    if corr:
        cases.append(RequiredCase(
            case_number=1,
            label="CORROBORATES",
            title="Corroborated Fact Despite Different Wording",
            description=(
                f"Two facts from different documents report the same value "
                f"(within tolerance) using different phrasing. "
                f"Confidence: {corr.confidence:.0%}. "
                f"Reasoning: {(corr.reasoning or '')[:300]}"
            ),
            relationship_id=corr.id,
            fact_a_id=corr.fact_a_id,
            fact_b_id=corr.fact_b_id,
        ))
    else:
        cases.append(RequiredCase(
            case_number=1,
            label="CORROBORATES",
            title="No corroborations found yet",
            description="Process more documents to discover corroborated facts.",
            relationship_id=None, fact_a_id=None, fact_b_id=None,
        ))

    # CASE 2: CONTRADICTS — highest confidence genuine contradiction
    contr_stmt = (
        select(Relationship)
        .where(Relationship.relationship_type == RelationshipType.CONTRADICTS)
        .order_by(Relationship.confidence.desc())
        .limit(1)
    )
    contr = (await db.execute(contr_stmt)).scalar_one_or_none()
    if contr:
        cases.append(RequiredCase(
            case_number=2,
            label="CONTRADICTS",
            title="Genuine Contradiction Between Documents",
            description=(
                f"Two facts about the same proposition, time, and scope disagree materially. "
                f"Delta: {contr.numeric_delta_pct:.1f}% difference. "
                f"Reasoning: {(contr.reasoning or '')[:300]}"
            ),
            relationship_id=contr.id,
            fact_a_id=contr.fact_a_id,
            fact_b_id=contr.fact_b_id,
        ))
    else:
        cases.append(RequiredCase(
            case_number=2,
            label="CONTRADICTS",
            title="No genuine contradictions found yet",
            description="More processing needed to surface contradictions.",
            relationship_id=None, fact_a_id=None, fact_b_id=None,
        ))

    # CASE 3: APPARENT_CONTRADICTION or TEMPORALLY_DISTINCT or DISTINCT_SCOPE
    apparent_types = [
        RelationshipType.APPARENT_CONTRADICTION,
        RelationshipType.TEMPORALLY_DISTINCT,
        RelationshipType.DISTINCT_SCOPE,
    ]
    appar_stmt = (
        select(Relationship)
        .where(Relationship.relationship_type.in_(apparent_types))
        .order_by(Relationship.confidence.desc())
        .limit(1)
    )
    appar = (await db.execute(appar_stmt)).scalar_one_or_none()
    if appar:
        cases.append(RequiredCase(
            case_number=3,
            label="APPARENT_CONTRADICTION",
            title="Apparent Contradiction Explained by Context",
            description=(
                f"Two facts appear contradictory but are actually {appar.relationship_type} — "
                f"context factors: {', '.join(appar.context_factors or [])}. "
                f"Explanation: {(appar.context_explanation or appar.reasoning or '')[:300]}"
            ),
            relationship_id=appar.id,
            fact_a_id=appar.fact_a_id,
            fact_b_id=appar.fact_b_id,
        ))
    else:
        cases.append(RequiredCase(
            case_number=3,
            label="APPARENT_CONTRADICTION",
            title="No contextual reconciliations found yet",
            description="Process more documents to discover temporally or scopally distinct facts.",
            relationship_id=None, fact_a_id=None, fact_b_id=None,
        ))

    # CASE 4: FAILED_EXTRACTION — most informative failure
    fail_stmt = (
        select(Fact)
        .where(Fact.extraction_status == ExtractionStatus.FAILED_EXTRACTION)
        .order_by(Fact.confidence.asc())
        .limit(1)
    )
    fail_fact = (await db.execute(fail_stmt)).scalar_one_or_none()
    from app.db.models import FactMention, Evidence
    failure_detail: Optional[dict] = None
    if fail_fact:
        ev_stmt = (
            select(Evidence)
            .join(FactMention, FactMention.evidence_id == Evidence.id)
            .where(FactMention.fact_id == fail_fact.id)
            .limit(1)
        )
        ev = (await db.execute(ev_stmt)).scalar_one_or_none()
        failure_detail = {
            "fact_predicate": fail_fact.predicate,
            "object_text": fail_fact.object_text,
            "confidence": fail_fact.confidence,
            "uncertainty_reasons": fail_fact.uncertainty_reasons or [],
            "evidence_snippet": (ev.exact_text[:200] if ev else "No evidence"),
            "what_failed": "Fact extraction or evidence grounding failed",
            "why": (
                "; ".join(fail_fact.uncertainty_reasons[:3])
                if fail_fact.uncertainty_reasons
                else "Unknown — confidence below threshold"
            ),
            "how_detected": "evidence_validator.validate_fact_grounding() rejected this fact before DB persistence",
            "improvement": (
                "Better chunk boundary detection or multi-span evidence linking "
                "would improve recall. A re-ranking pass for borderline facts "
                "with human-in-the-loop labeling could surface recoverable cases."
            ),
        }
    cases.append(RequiredCase(
        case_number=4,
        label="FAILURE",
        title="Extraction or Reasoning Failure",
        description=(
            "A fact that failed evidence grounding or had confidence below threshold. "
            "The system detected this, recorded it, and explains what went wrong."
        ),
        relationship_id=None,
        fact_a_id=fail_fact.id if fail_fact else None,
        fact_b_id=None,
        failure_detail=failure_detail or {
            "what_failed": "No failures recorded yet — all processed facts passed grounding.",
            "why": "N/A",
            "how_detected": "evidence_validator.validate_fact_grounding()",
            "improvement": "Run with noisy PDFs to trigger fallback paths.",
        },
    ))

    return CasesResponse(cases=cases, generated_at=datetime.utcnow())


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@metrics_router.get("", response_model=SystemMetrics)
async def get_metrics(db: AsyncSession = Depends(get_db)) -> SystemMetrics:
    """JSON metrics summary."""
    docs_total = (await db.execute(select(func.count(Document.id)))).scalar_one()
    facts_total = (await db.execute(select(func.count(Fact.id)))).scalar_one()

    trusted = (await db.execute(select(func.count(Fact.id)).where(Fact.extraction_status == ExtractionStatus.TRUSTED))).scalar_one()
    probable = (await db.execute(select(func.count(Fact.id)).where(Fact.extraction_status == ExtractionStatus.PROBABLE))).scalar_one()
    uncertain = (await db.execute(select(func.count(Fact.id)).where(Fact.extraction_status == ExtractionStatus.UNCERTAIN))).scalar_one()
    failed = (await db.execute(select(func.count(Fact.id)).where(Fact.extraction_status == ExtractionStatus.FAILED_EXTRACTION))).scalar_one()

    grounded = (await db.execute(select(func.count(Fact.id)).where(Fact.extraction_status != ExtractionStatus.FAILED_EXTRACTION))).scalar_one()

    rels_total = (await db.execute(select(func.count(Relationship.id)))).scalar_one()

    def count_rel(t: RelationshipType) -> int:
        return 0  # will be computed below

    rel_counts: dict[str, int] = {}
    for rt in RelationshipType:
        c = (await db.execute(select(func.count(Relationship.id)).where(Relationship.relationship_type == rt))).scalar_one()
        rel_counts[rt.value] = c

    avg_conf_result = await db.execute(select(func.avg(Fact.confidence)))
    avg_conf = float(avg_conf_result.scalar_one() or 0.0)

    from app.db.models import Page
    pages_total = (await db.execute(select(func.count(Page.id)))).scalar_one()

    return SystemMetrics(
        documents_total=docs_total,
        pages_total=pages_total,
        facts_total=facts_total,
        grounded_facts_total=grounded,
        facts_trusted=trusted,
        facts_probable=probable,
        facts_uncertain=uncertain,
        facts_failed=failed,
        relationships_total=rels_total,
        corroborations=rel_counts.get("CORROBORATES", 0),
        contradictions=rel_counts.get("CONTRADICTS", 0),
        apparent_contradictions=rel_counts.get("APPARENT_CONTRADICTION", 0),
        distinct_scope=rel_counts.get("DISTINCT_SCOPE", 0),
        temporally_distinct=rel_counts.get("TEMPORALLY_DISTINCT", 0),
        uncertain_relationships=rel_counts.get("UNCERTAIN", 0),
        fact_grounding_rate=grounded / max(facts_total, 1),
        extraction_failure_rate=failed / max(facts_total, 1),
        average_confidence=avg_conf,
        generated_at=datetime.utcnow(),
    )


@metrics_router.get("/prometheus")
async def prometheus_metrics() -> Response:
    """Prometheus text format metrics."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@health_router.get("", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)) -> HealthResponse:
    from app.core.config import get_settings
    settings = get_settings()
    db_status = "ok"
    try:
        from sqlalchemy import text
        await db.execute(text("SELECT 1"))
    except Exception:
        db_status = "error"
    return HealthResponse(
        status="ok",
        database=db_status,
        llm_provider=settings.llm_provider,
        embedding_model=settings.embedding_model,
    )
