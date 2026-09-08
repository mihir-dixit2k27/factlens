"""Pydantic schemas for FactLens API layer."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Document schemas
# ---------------------------------------------------------------------------


class DocumentUploadResponse(BaseModel):
    id: str
    filename: str
    file_size_bytes: int
    processing_stage: str
    created_at: datetime


class DocumentDetail(BaseModel):
    id: str
    filename: str
    filepath: str
    file_size_bytes: int
    page_count: Optional[int]
    dataset: Optional[str]
    title: Optional[str]
    processing_stage: str
    processing_error: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentList(BaseModel):
    items: list[DocumentDetail]
    total: int


# ---------------------------------------------------------------------------
# Evidence schemas
# ---------------------------------------------------------------------------


class EvidenceOut(BaseModel):
    id: str
    document_id: str
    page_number: int
    block_id: Optional[str]
    chunk_id: Optional[str]
    exact_text: str
    bbox: Optional[list[float]]
    extraction_method: str
    extraction_confidence: float

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Fact schemas
# ---------------------------------------------------------------------------


class TemporalScope(BaseModel):
    type: str  # point, range, fiscal_year, quarter, reporting_period
    start: Optional[str] = None
    end: Optional[str] = None
    label: Optional[str] = None  # e.g. "FY2024", "Q4 FY24"
    confidence: float = 1.0


class FactOut(BaseModel):
    id: str
    subject_entity_id: Optional[str]
    subject_name: Optional[str]  # resolved via join
    predicate: str
    object_type: str
    object_text: str
    numeric_value: Optional[float]
    normalized_value: Optional[float]
    unit: Optional[str]
    normalized_unit: Optional[str]
    currency: Optional[str]
    temporal_scope: Optional[dict]
    geographic_scope: Optional[str]
    population_scope: Optional[str]
    methodology: Optional[str]
    qualifiers: Optional[dict]
    modality: Optional[str]
    confidence: float
    extraction_status: str
    uncertainty_reasons: Optional[list[str]]
    primary_document_id: Optional[str]
    evidence_count: int
    relationship_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class FactWithEvidence(FactOut):
    evidences: list[EvidenceOut]


# ---------------------------------------------------------------------------
# Relationship / Reconciliation schemas
# ---------------------------------------------------------------------------


class ReasoningTrace(BaseModel):
    step_1_candidates: Optional[str] = None
    step_2_semantic_similarity: Optional[float] = None
    step_3_entity_match: Optional[bool] = None
    step_4_predicate_match: Optional[float] = None
    step_5_time_comparison: Optional[str] = None
    step_6_scope_comparison: Optional[str] = None
    step_7_unit_comparison: Optional[str] = None
    step_8_numeric_comparison: Optional[str] = None
    step_9_final_relationship: Optional[str] = None
    step_10_confidence: Optional[float] = None


class RelationshipOut(BaseModel):
    id: str
    fact_a_id: str
    fact_b_id: str
    fact_a: Optional[FactOut] = None
    fact_b: Optional[FactOut] = None
    relationship_type: str
    confidence: float
    reasoning: Optional[str]
    context_explanation: Optional[str]
    context_factors: Optional[list[str]]
    reasoning_trace: Optional[dict]
    numeric_delta: Optional[float]
    numeric_delta_pct: Optional[float]
    llm_assisted: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Reconciliation Ledger
# ---------------------------------------------------------------------------


class LedgerEntry(BaseModel):
    fact: FactOut
    raw_claim: str
    normalized_claim: str
    evidence: list[EvidenceOut]
    related_facts: list[FactOut]
    relationships: list[RelationshipOut]
    reconciliation_summary: str


# ---------------------------------------------------------------------------
# Processing Run schemas
# ---------------------------------------------------------------------------


class ProcessingRunOut(BaseModel):
    id: str
    document_id: str
    stage: str
    status: str
    pages_processed: int
    chunks_created: int
    facts_created: int
    embeddings_created: int
    relationships_created: int
    processing_time_seconds: Optional[float]
    error_message: Optional[str]
    manifest: Optional[dict]
    started_at: datetime
    completed_at: Optional[datetime]

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Query schemas
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000)
    limit: int = Field(10, ge=1, le=50)
    dataset: Optional[str] = None


class QueryResult(BaseModel):
    query: str
    answer: str
    relevant_facts: list[FactOut]
    relevant_relationships: list[RelationshipOut]
    source_documents: list[str]
    confidence: float


# ---------------------------------------------------------------------------
# Cases schemas
# ---------------------------------------------------------------------------


class RequiredCase(BaseModel):
    case_number: int  # 1-4
    label: str  # CORROBORATES | CONTRADICTS | APPARENT_CONTRADICTION | FAILURE
    title: str
    description: str
    relationship_id: Optional[str]
    fact_a_id: Optional[str]
    fact_b_id: Optional[str]
    failure_detail: Optional[dict] = None  # for Case 4


class CasesResponse(BaseModel):
    cases: list[RequiredCase]
    generated_at: datetime


# ---------------------------------------------------------------------------
# Metrics schemas
# ---------------------------------------------------------------------------


class SystemMetrics(BaseModel):
    documents_total: int
    pages_total: int
    facts_total: int
    grounded_facts_total: int
    facts_trusted: int
    facts_probable: int
    facts_uncertain: int
    facts_failed: int
    relationships_total: int
    corroborations: int
    contradictions: int
    apparent_contradictions: int
    distinct_scope: int
    temporally_distinct: int
    uncertain_relationships: int
    fact_grounding_rate: float
    extraction_failure_rate: float
    average_confidence: float
    generated_at: datetime


class HealthResponse(BaseModel):
    status: str
    database: str
    llm_provider: str
    embedding_model: str
    version: str = "1.0.0"
