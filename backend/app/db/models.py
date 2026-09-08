"""SQLAlchemy ORM models for FactLens knowledge layer."""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProcessingStage(str, enum.Enum):
    INITIATED = "INITIATED"
    DOCUMENT_DISCOVERY = "DOCUMENT_DISCOVERY"
    PDF_EXTRACTION = "PDF_EXTRACTION"
    LAYOUT_ANALYSIS = "LAYOUT_ANALYSIS"
    CHUNKING = "CHUNKING"
    FACT_CANDIDATE_EXTRACTION = "FACT_CANDIDATE_EXTRACTION"
    NORMALIZATION = "NORMALIZATION"
    ENTITY_RESOLUTION = "ENTITY_RESOLUTION"
    EMBEDDING = "EMBEDDING"
    CANDIDATE_LINKING = "CANDIDATE_LINKING"
    RELATIONSHIP_COMPARISON = "RELATIONSHIP_COMPARISON"
    RECONCILIATION = "RECONCILIATION"
    INDEXING = "INDEXING"
    READY = "READY"
    FAILED = "FAILED"


class ExtractionStatus(str, enum.Enum):
    TRUSTED = "TRUSTED"
    PROBABLE = "PROBABLE"
    UNCERTAIN = "UNCERTAIN"
    FAILED_EXTRACTION = "FAILED_EXTRACTION"


class RelationshipType(str, enum.Enum):
    CORROBORATES = "CORROBORATES"
    CONTRADICTS = "CONTRADICTS"
    APPARENT_CONTRADICTION = "APPARENT_CONTRADICTION"
    DISTINCT_SCOPE = "DISTINCT_SCOPE"
    TEMPORALLY_DISTINCT = "TEMPORALLY_DISTINCT"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    DEFINITION_MISMATCH = "DEFINITION_MISMATCH"
    METHODOLOGY_DIFFERENCE = "METHODOLOGY_DIFFERENCE"
    RELATED = "RELATED"
    UNCERTAIN = "UNCERTAIN"


class ObjectType(str, enum.Enum):
    NUMERIC = "NUMERIC"
    PERCENTAGE = "PERCENTAGE"
    MONETARY = "MONETARY"
    COUNT = "COUNT"
    RATIO = "RATIO"
    DATE = "DATE"
    TEXT = "TEXT"
    BOOLEAN = "BOOLEAN"
    RANGE = "RANGE"


# ---------------------------------------------------------------------------
# Core Tables
# ---------------------------------------------------------------------------


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    filepath: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dataset: Mapped[str | None] = mapped_column(String(256), nullable=True)  # e.g., "delhivery"
    title: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    processing_stage: Mapped[str] = mapped_column(
        Enum(ProcessingStage), default=ProcessingStage.INITIATED, nullable=False
    )
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    pages: Mapped[list[Page]] = relationship("Page", back_populates="document", cascade="all, delete-orphan")
    chunks: Mapped[list[Chunk]] = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")
    processing_runs: Mapped[list[ProcessingRun]] = relationship("ProcessingRun", back_populates="document")


class Page(Base):
    __tablename__ = "pages"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[float | None] = mapped_column(Float, nullable=True)
    height: Mapped[float | None] = mapped_column(Float, nullable=True)
    char_count: Mapped[int] = mapped_column(Integer, default=0)
    block_count: Mapped[int] = mapped_column(Integer, default=0)
    is_sparse: Mapped[bool] = mapped_column(Boolean, default=False)
    extraction_method: Mapped[str] = mapped_column(String(64), default="pymupdf")
    plain_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped[Document] = relationship("Document", back_populates="pages")
    chunks: Mapped[list[Chunk]] = relationship("Chunk", back_populates="page")

    __table_args__ = (UniqueConstraint("document_id", "page_number"),)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_id: Mapped[str | None] = mapped_column(ForeignKey("pages.id"), nullable=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    bbox: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {x0,y0,x1,y1}
    block_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(64), default="pymupdf")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped[Document] = relationship("Document", back_populates="chunks")
    page: Mapped[Page | None] = relationship("Page", back_populates="chunks")
    evidences: Mapped[list[Evidence]] = relationship("Evidence", back_populates="chunk")


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    canonical_name: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    entity_type: Mapped[str] = mapped_column(String(128), nullable=False)  # ORG, PERSON, GPE, etc.
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    facts_as_subject: Mapped[list[Fact]] = relationship(
        "Fact", foreign_keys="[Fact.subject_entity_id]", back_populates="subject_entity"
    )


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    subject_entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id"), nullable=True)
    predicate: Mapped[str] = mapped_column(String(512), nullable=False)
    object_type: Mapped[str] = mapped_column(Enum(ObjectType), nullable=False)
    object_text: Mapped[str] = mapped_column(Text, nullable=False)  # raw extracted text
    numeric_value: Mapped[float | None] = mapped_column(Numeric(30, 10), nullable=True)
    normalized_value: Mapped[float | None] = mapped_column(Numeric(30, 10), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(128), nullable=True)
    normalized_unit: Mapped[str | None] = mapped_column(String(128), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True)
    # Scope fields (structured JSON for flexibility)
    temporal_scope: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    geographic_scope: Mapped[str | None] = mapped_column(String(512), nullable=True)
    population_scope: Mapped[str | None] = mapped_column(String(512), nullable=True)
    methodology: Mapped[str | None] = mapped_column(String(512), nullable=True)
    qualifiers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    modality: Mapped[str | None] = mapped_column(String(128), nullable=True)  # estimated, projected, audited
    # Quality
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    extraction_status: Mapped[str] = mapped_column(
        Enum(ExtractionStatus), default=ExtractionStatus.PROBABLE, nullable=False
    )
    uncertainty_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Source
    primary_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    subject_entity: Mapped[Entity | None] = relationship("Entity", back_populates="facts_as_subject")
    mentions: Mapped[list[FactMention]] = relationship("FactMention", back_populates="fact", cascade="all, delete-orphan")
    embeddings: Mapped[list[FactEmbedding]] = relationship("FactEmbedding", back_populates="fact", cascade="all, delete-orphan")
    relationships_as_a: Mapped[list[Relationship]] = relationship(
        "Relationship", foreign_keys="[Relationship.fact_a_id]", back_populates="fact_a"
    )
    relationships_as_b: Mapped[list[Relationship]] = relationship(
        "Relationship", foreign_keys="[Relationship.fact_b_id]", back_populates="fact_b"
    )


class Evidence(Base):
    __tablename__ = "evidences"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    block_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chunk_id: Mapped[str | None] = mapped_column(ForeignKey("chunks.id"), nullable=True)
    exact_text: Mapped[str] = mapped_column(Text, nullable=False)
    bbox: Mapped[list | None] = mapped_column(JSON, nullable=True)  # [x0, y0, x1, y1]
    extraction_method: Mapped[str] = mapped_column(String(64), default="pymupdf")
    extraction_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    document: Mapped[Document] = relationship("Document")
    chunk: Mapped[Chunk | None] = relationship("Chunk", back_populates="evidences")
    mentions: Mapped[list[FactMention]] = relationship("FactMention", back_populates="evidence")


class FactMention(Base):
    """Links a Fact to the Evidence that supports it."""
    __tablename__ = "fact_mentions"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    fact_id: Mapped[str] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), nullable=False)
    evidence_id: Mapped[str] = mapped_column(ForeignKey("evidences.id", ondelete="CASCADE"), nullable=False)
    source_confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    fact: Mapped[Fact] = relationship("Fact", back_populates="mentions")
    evidence: Mapped[Evidence] = relationship("Evidence", back_populates="mentions")

    __table_args__ = (UniqueConstraint("fact_id", "evidence_id"),)


class FactEmbedding(Base):
    __tablename__ = "fact_embeddings"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    fact_id: Mapped[str] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), nullable=False, unique=True)
    model_name: Mapped[str] = mapped_column(String(256), nullable=False)
    vector: Mapped[Any] = mapped_column(Vector(384), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    fact: Mapped[Fact] = relationship("Fact", back_populates="embeddings")


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    fact_a_id: Mapped[str] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), nullable=False)
    fact_b_id: Mapped[str] = mapped_column(ForeignKey("facts.id", ondelete="CASCADE"), nullable=False)
    relationship_type: Mapped[str] = mapped_column(Enum(RelationshipType), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    context_factors: Mapped[list | None] = mapped_column(JSON, nullable=True)
    reasoning_trace: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    numeric_delta: Mapped[float | None] = mapped_column(Float, nullable=True)
    numeric_delta_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    llm_assisted: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    fact_a: Mapped[Fact] = relationship("Fact", foreign_keys=[fact_a_id], back_populates="relationships_as_a")
    fact_b: Mapped[Fact] = relationship("Fact", foreign_keys=[fact_b_id], back_populates="relationships_as_b")

    __table_args__ = (UniqueConstraint("fact_a_id", "fact_b_id"),)


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[str] = mapped_column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    stage: Mapped[str] = mapped_column(Enum(ProcessingStage), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="running")  # running | completed | failed
    pages_processed: Mapped[int] = mapped_column(Integer, default=0)
    chunks_created: Mapped[int] = mapped_column(Integer, default=0)
    facts_created: Mapped[int] = mapped_column(Integer, default=0)
    embeddings_created: Mapped[int] = mapped_column(Integer, default=0)
    relationships_created: Mapped[int] = mapped_column(Integer, default=0)
    processing_time_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    document: Mapped[Document] = relationship("Document", back_populates="processing_runs")
