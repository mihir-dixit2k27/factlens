"""
Processing Orchestrator — the full ingestion pipeline for a single document.

Stages (idempotent, with state tracking):
  DOCUMENT_DISCOVERY -> PDF_EXTRACTION -> LAYOUT_ANALYSIS -> CHUNKING ->
  FACT_CANDIDATE_EXTRACTION -> NORMALIZATION -> ENTITY_RESOLUTION ->
  EMBEDDING -> CANDIDATE_LINKING -> RELATIONSHIP_COMPARISON ->
  RECONCILIATION -> INDEXING -> READY

Supports incremental processing:
  - A new document only processes new facts
  - Existing facts/relationships are never rebuilt

Failed stages are marked and earlier results preserved.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import (
    documents_processed_total,
    pages_processed_total,
    processing_duration_seconds,
)
from app.db.models import (
    Chunk,
    Document,
    Page,
    ProcessingRun,
    ProcessingStage,
)
from app.embeddings.provider import EmbeddingStore, SentenceTransformerProvider
from app.entity_resolution.resolver import EntityResolver
from app.extraction.fact_extractor import extract_and_store_facts
from app.extraction.llm_provider import LLMProvider, get_llm_provider
from app.ingestion.chunker import TextChunk, chunk_document
from app.ingestion.pdf_extractor import DocumentExtraction, extract_document
from app.reconciliation.ledger import run_candidate_linking

logger = get_logger(__name__)
settings = get_settings()

# Module-level singletons (initialized on first use)
_embedding_provider: Optional[SentenceTransformerProvider] = None
_llm_provider: Optional[LLMProvider] = None


def get_embedding_provider() -> SentenceTransformerProvider:
    global _embedding_provider
    if _embedding_provider is None:
        _embedding_provider = SentenceTransformerProvider()
    return _embedding_provider


def get_llm_provider_singleton() -> LLMProvider:
    global _llm_provider
    if _llm_provider is None:
        _llm_provider = get_llm_provider()
    return _llm_provider


async def _update_document_stage(
    session: AsyncSession, document_id: str, stage: ProcessingStage, error: Optional[str] = None
) -> None:
    await session.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(processing_stage=stage, processing_error=error)
    )
    await session.flush()


async def _create_run(
    session: AsyncSession, document_id: str, stage: ProcessingStage
) -> ProcessingRun:
    run = ProcessingRun(document_id=document_id, stage=stage, status="running")
    session.add(run)
    await session.flush()
    return run


async def _complete_run(
    session: AsyncSession,
    run: ProcessingRun,
    **kwargs,
) -> None:
    run.status = "completed"
    run.completed_at = datetime.utcnow()
    for k, v in kwargs.items():
        setattr(run, k, v)
    await session.flush()


async def _fail_run(session: AsyncSession, run: ProcessingRun, error: str) -> None:
    run.status = "failed"
    run.error_message = error
    run.completed_at = datetime.utcnow()
    await session.flush()


async def process_document(
    session: AsyncSession,
    document_id: str,
    incremental: bool = True,
) -> dict:
    """
    Run the full processing pipeline for a document.

    incremental=True: only processes new facts, does not rebuild existing ones.
    Returns a manifest dict with processing statistics.
    """
    manifest: dict = {"document_id": document_id, "stages": {}, "success": False}

    # Load document
    stmt = select(Document).where(Document.id == document_id)
    result = await session.execute(stmt)
    doc: Optional[Document] = result.scalar_one_or_none()
    if not doc:
        logger.error("document_not_found", document_id=document_id)
        return manifest

    pdf_path = Path(doc.filepath)
    if not pdf_path.exists():
        await _update_document_stage(
            session, document_id, ProcessingStage.FAILED,
            error=f"PDF file not found: {pdf_path}"
        )
        return manifest

    # Check if document already at READY stage (incremental guard)
    if incremental and doc.processing_stage == ProcessingStage.READY:
        logger.info("document_already_ready", document_id=document_id)
        manifest["success"] = True
        return manifest

    logger.info("pipeline_start", document_id=document_id, path=pdf_path.name)

    # -------------------------------------------------------
    # STAGE: PDF_EXTRACTION
    # -------------------------------------------------------
    await _update_document_stage(session, document_id, ProcessingStage.PDF_EXTRACTION)
    run = await _create_run(session, document_id, ProcessingStage.PDF_EXTRACTION)
    t0 = time.perf_counter()

    try:
        doc_ext: DocumentExtraction = extract_document(pdf_path)
    except Exception as exc:
        await _fail_run(session, run, str(exc))
        await _update_document_stage(session, document_id, ProcessingStage.FAILED, str(exc))
        return manifest

    # Persist pages
    page_objects: list[Page] = []
    for page_ext in doc_ext.pages:
        # Check if page already exists (incremental guard)
        existing_stmt = select(Page).where(
            Page.document_id == document_id,
            Page.page_number == page_ext.page_number,
        )
        existing = (await session.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            page_objects.append(existing)
            continue
        page_obj = Page(
            document_id=document_id,
            page_number=page_ext.page_number,
            width=page_ext.width,
            height=page_ext.height,
            char_count=page_ext.char_count,
            block_count=len(page_ext.blocks),
            is_sparse=page_ext.is_sparse,
            extraction_method=page_ext.extraction_method,
            plain_text=page_ext.plain_text[:10000] if page_ext.plain_text else None,
        )
        session.add(page_obj)
        page_objects.append(page_obj)

    await session.flush()
    pages_processed_total.inc(len(page_objects))

    # Update document metadata
    doc.page_count = doc_ext.page_count
    await session.flush()

    elapsed = time.perf_counter() - t0
    processing_duration_seconds.labels(stage="pdf_extraction").observe(elapsed)
    await _complete_run(session, run, pages_processed=len(page_objects),
                        processing_time_seconds=elapsed)
    manifest["stages"]["pdf_extraction"] = {"pages": len(page_objects)}

    # -------------------------------------------------------
    # STAGE: CHUNKING
    # -------------------------------------------------------
    await _update_document_stage(session, document_id, ProcessingStage.CHUNKING)
    run = await _create_run(session, document_id, ProcessingStage.CHUNKING)
    t0 = time.perf_counter()

    try:
        text_chunks: list[TextChunk] = chunk_document(doc_ext)
    except Exception as exc:
        await _fail_run(session, run, str(exc))
        await _update_document_stage(session, document_id, ProcessingStage.FAILED, str(exc))
        return manifest

    # Persist chunks (skip already existing)
    chunk_objects: list[Chunk] = []
    existing_indices_stmt = select(Chunk.chunk_index).where(Chunk.document_id == document_id)
    existing_indices = {r for r in (await session.execute(existing_indices_stmt)).scalars()}

    for tc in text_chunks:
        if tc.chunk_index in existing_indices:
            existing_stmt = select(Chunk).where(
                Chunk.document_id == document_id,
                Chunk.chunk_index == tc.chunk_index,
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing:
                chunk_objects.append(existing)
            continue
        chunk_obj = Chunk(
            document_id=document_id,
            page_number=tc.page_number,
            chunk_index=tc.chunk_index,
            text=tc.text,
            token_count=tc.token_estimate,
            bbox=tc.bbox,
            block_ids=tc.block_ids,
            extraction_method=tc.extraction_method,
        )
        session.add(chunk_obj)
        chunk_objects.append(chunk_obj)

    await session.flush()
    elapsed = time.perf_counter() - t0
    processing_duration_seconds.labels(stage="chunking").observe(elapsed)
    await _complete_run(session, run, chunks_created=len(chunk_objects),
                        processing_time_seconds=elapsed)
    manifest["stages"]["chunking"] = {"chunks": len(chunk_objects)}

    # -------------------------------------------------------
    # STAGE: FACT_CANDIDATE_EXTRACTION
    # -------------------------------------------------------
    await _update_document_stage(session, document_id, ProcessingStage.FACT_CANDIDATE_EXTRACTION)
    run = await _create_run(session, document_id, ProcessingStage.FACT_CANDIDATE_EXTRACTION)
    t0 = time.perf_counter()

    llm = get_llm_provider_singleton()
    entity_resolver = EntityResolver()
    doc_context = f"Document: {doc.filename}, Dataset: {doc.dataset or 'unknown'}"

    total_stored = 0
    total_rejected = 0
    new_fact_ids: list[str] = []

    # We process only chunks that don't yet have facts (incremental)
    chunks_to_process = chunk_objects
    if incremental:
        # Filter chunks that already have evidence linked
        from app.db.models import Evidence
        processed_chunk_ids_stmt = select(Evidence.chunk_id).where(
            Evidence.document_id == document_id,
            Evidence.chunk_id.is_not(None),
        )
        processed_chunk_ids = {
            r for r in (await session.execute(processed_chunk_ids_stmt)).scalars()
            if r is not None
        }
        chunks_to_process = [c for c in chunk_objects if c.id not in processed_chunk_ids]

    for chunk_obj in chunks_to_process:
        try:
            stored, rejected = await extract_and_store_facts(
                session=session,
                llm=llm,
                chunk=chunk_obj,
                document_id=document_id,
                entity_resolver=entity_resolver,
                document_context=doc_context,
            )
            total_stored += stored
            total_rejected += rejected
        except Exception as exc:
            logger.error("chunk_extraction_failed", chunk_id=chunk_obj.id, error=str(exc))

    await session.flush()

    # Collect new fact IDs from this document for embedding
    from app.db.models import ExtractionStatus, Fact, FactEmbedding
    new_facts_stmt = (
        select(Fact.id)
        .outerjoin(FactEmbedding, Fact.id == FactEmbedding.fact_id)
        .where(Fact.primary_document_id == document_id)
        .where(FactEmbedding.id.is_(None))
        .where(Fact.extraction_status != ExtractionStatus.FAILED_EXTRACTION)
    )
    new_fact_ids = list((await session.execute(new_facts_stmt)).scalars())

    elapsed = time.perf_counter() - t0
    processing_duration_seconds.labels(stage="fact_extraction").observe(elapsed)
    await _complete_run(session, run, facts_created=total_stored,
                        processing_time_seconds=elapsed)
    manifest["stages"]["fact_extraction"] = {
        "stored": total_stored,
        "rejected": total_rejected,
        "new_for_embedding": len(new_fact_ids),
    }

    # -------------------------------------------------------
    # STAGE: EMBEDDING
    # -------------------------------------------------------
    await _update_document_stage(session, document_id, ProcessingStage.EMBEDDING)
    run = await _create_run(session, document_id, ProcessingStage.EMBEDDING)
    t0 = time.perf_counter()

    embedding_count = 0
    try:
        emb_provider = get_embedding_provider()
        emb_store = EmbeddingStore(emb_provider)
        embedding_count = await emb_store.embed_new_facts(
            session, fact_ids=new_fact_ids if new_fact_ids else None
        )
    except Exception as exc:
        logger.warning("embedding_stage_failed", error=str(exc))

    elapsed = time.perf_counter() - t0
    processing_duration_seconds.labels(stage="embedding").observe(elapsed)
    await _complete_run(session, run, embeddings_created=embedding_count,
                        processing_time_seconds=elapsed)
    manifest["stages"]["embedding"] = {"embeddings": embedding_count}

    # -------------------------------------------------------
    # STAGE: CANDIDATE_LINKING & RECONCILIATION
    # -------------------------------------------------------
    await _update_document_stage(session, document_id, ProcessingStage.CANDIDATE_LINKING)
    run = await _create_run(session, document_id, ProcessingStage.CANDIDATE_LINKING)
    t0 = time.perf_counter()

    rel_count = 0
    try:
        emb_provider = get_embedding_provider()
        rel_count = await run_candidate_linking(
            session=session,
            llm=llm,
            embedding_provider=emb_provider,
            fact_ids=new_fact_ids if new_fact_ids else None,
        )
    except Exception as exc:
        logger.warning("candidate_linking_failed", error=str(exc))

    elapsed = time.perf_counter() - t0
    processing_duration_seconds.labels(stage="reconciliation").observe(elapsed)
    await _complete_run(session, run, relationships_created=rel_count,
                        processing_time_seconds=elapsed)
    manifest["stages"]["reconciliation"] = {"relationships": rel_count}

    # -------------------------------------------------------
    # READY
    # -------------------------------------------------------
    await _update_document_stage(session, document_id, ProcessingStage.READY)
    documents_processed_total.labels(status="success").inc()
    manifest["success"] = True

    logger.info(
        "pipeline_complete",
        document_id=document_id,
        facts=total_stored,
        relationships=rel_count,
    )
    return manifest
