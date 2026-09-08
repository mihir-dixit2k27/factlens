"""Document upload and management routes."""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.models import Document, ProcessingRun, ProcessingStage
from app.db.session import get_db
from app.ingestion.pdf_discovery import compute_sha256
from app.ingestion.pipeline import process_document
from app.schemas.schemas import DocumentDetail, DocumentList, DocumentUploadResponse, ProcessingRunOut

router = APIRouter(prefix="/api/documents", tags=["documents"])
logger = get_logger(__name__)
settings = get_settings()


async def _run_pipeline(document_id: str) -> None:
    """Background task to run the processing pipeline."""
    from app.db.session import get_db_context
    async with get_db_context() as session:
        await process_document(session, document_id)


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> DocumentUploadResponse:
    """Upload a PDF document and queue it for processing."""
    # Validate
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are accepted.")

    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise HTTPException(413, f"File exceeds {settings.max_upload_size_mb}MB limit.")
    if len(content) < 100:
        raise HTTPException(400, "File is too small to be a valid PDF.")

    # Save to incoming
    settings.incoming_dir.mkdir(parents=True, exist_ok=True)
    doc_id = str(uuid.uuid4())
    dest_path = settings.incoming_dir / f"{doc_id}_{file.filename}"
    with open(dest_path, "wb") as f:
        f.write(content)

    # Compute hash to prevent duplicate processing
    file_hash = compute_sha256(dest_path)
    existing_stmt = select(Document).where(Document.file_hash == file_hash)
    existing = (await db.execute(existing_stmt)).scalar_one_or_none()
    if existing:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(409, f"Document already exists (id={existing.id}).")

    # Determine dataset from filename prefix pattern
    dataset_name = "uploaded"

    doc = Document(
        id=doc_id,
        filename=file.filename,
        filepath=str(dest_path.resolve()),
        file_hash=file_hash,
        file_size_bytes=len(content),
        dataset=dataset_name,
        processing_stage=ProcessingStage.INITIATED,
    )
    db.add(doc)
    await db.flush()

    # Queue background processing
    background_tasks.add_task(_run_pipeline, doc_id)

    logger.info("document_uploaded", id=doc_id, filename=file.filename, size=len(content))
    return DocumentUploadResponse(
        id=doc.id,
        filename=doc.filename,
        file_size_bytes=doc.file_size_bytes,
        processing_stage=doc.processing_stage,
        created_at=doc.created_at,
    )


@router.get("", response_model=DocumentList)
async def list_documents(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
) -> DocumentList:
    stmt = select(Document).offset(skip).limit(limit).order_by(Document.created_at.desc())
    result = await db.execute(stmt)
    docs = list(result.scalars().all())
    count_stmt = select(func.count(Document.id))
    total = (await db.execute(count_stmt)).scalar_one()
    return DocumentList(items=[DocumentDetail.model_validate(d) for d in docs], total=total)


@router.get("/{doc_id}", response_model=DocumentDetail)
async def get_document(doc_id: str, db: AsyncSession = Depends(get_db)) -> DocumentDetail:
    stmt = select(Document).where(Document.id == doc_id)
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found.")
    return DocumentDetail.model_validate(doc)


@router.post("/{doc_id}/process", status_code=202)
async def trigger_processing(
    doc_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
) -> dict:
    stmt = select(Document).where(Document.id == doc_id)
    doc = (await db.execute(stmt)).scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "Document not found.")
    background_tasks.add_task(_run_pipeline, doc_id)
    return {"message": "Processing queued.", "document_id": doc_id}


@router.get("/{doc_id}/runs", response_model=list[ProcessingRunOut])
async def get_processing_runs(doc_id: str, db: AsyncSession = Depends(get_db)) -> list[ProcessingRunOut]:
    stmt = (
        select(ProcessingRun)
        .where(ProcessingRun.document_id == doc_id)
        .order_by(ProcessingRun.started_at.desc())
    )
    result = await db.execute(stmt)
    runs = list(result.scalars().all())
    return [ProcessingRunOut.model_validate(r) for r in runs]
