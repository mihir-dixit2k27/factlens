"""
Demo CLI — starts services, processes all PDFs, and prints a summary.

Usage:
    python -m app.cli.demo

Or via Makefile:
    make demo
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path


async def run_demo() -> None:
    print("\n" + "=" * 60)
    print("  FactLens — Demo Mode")
    print("=" * 60)

    # 1. Discover PDFs
    from app.ingestion.pdf_discovery import discover_pdfs

    data_root = Path(__file__).parent.parent.parent.parent.parent / "starter-datasets"
    if not data_root.exists():
        data_root = Path("../../starter-datasets")

    pdfs = discover_pdfs(data_root)
    if not pdfs:
        print(f"  No PDFs found at {data_root.resolve()}")
        print("  Place PDFs in starter-datasets/ and retry.")
        return

    print(f"\n  Found {len(pdfs)} PDFs:")
    for pdf in pdfs:
        print(f"    [{pdf.dataset}] {pdf.filename}")

    # 2. Initialize DB
    from app.db.session import init_db, get_db_context

    print("\n  Initializing database...")
    await init_db()
    print("  ✓ Database ready")

    # 3. Register + process each PDF
    from app.db.models import Document, ProcessingStage
    from app.ingestion.pdf_discovery import compute_sha256
    from app.ingestion.pipeline import process_document
    from sqlalchemy import select

    processed_count = 0
    for pdf in pdfs:
        async with get_db_context() as session:
            # Check if already registered
            existing = (
                await session.execute(select(Document).where(Document.file_hash == pdf.file_hash))
            ).scalar_one_or_none()

            if not existing:
                import uuid
                doc_id = str(uuid.uuid4())
                doc = Document(
                    id=doc_id,
                    filename=pdf.filename,
                    filepath=str(pdf.path.resolve()),
                    file_hash=pdf.file_hash,
                    file_size_bytes=pdf.file_size_bytes,
                    dataset=pdf.dataset,
                    processing_stage=ProcessingStage.INITIATED,
                )
                session.add(doc)
                await session.flush()
                print(f"\n  Processing [{pdf.dataset}] {pdf.filename}...")
                manifest = await process_document(session, doc_id)
                if manifest.get("success"):
                    stages = manifest.get("stages", {})
                    facts = stages.get("fact_extraction", {}).get("stored", 0)
                    rels = stages.get("reconciliation", {}).get("relationships", 0)
                    print(f"    ✓ Facts stored: {facts}, Relationships: {rels}")
                else:
                    print(f"    ✗ Processing failed")
                processed_count += 1
            else:
                print(f"  ↳ Already processed: {pdf.filename}")

    # 4. Print summary
    from app.db.models import Fact, Relationship, RelationshipType, ExtractionStatus, Page
    from sqlalchemy import func

    async with get_db_context() as session:
        total_docs = (await session.execute(select(func.count(Document.id)))).scalar_one()
        total_pages = (await session.execute(select(func.count(Page.id)))).scalar_one()
        total_facts = (await session.execute(select(func.count(Fact.id)))).scalar_one()
        grounded = (await session.execute(
            select(func.count(Fact.id)).where(Fact.extraction_status != ExtractionStatus.FAILED_EXTRACTION)
        )).scalar_one()
        corroborations = (await session.execute(
            select(func.count(Relationship.id)).where(Relationship.relationship_type == RelationshipType.CORROBORATES)
        )).scalar_one()
        contradictions = (await session.execute(
            select(func.count(Relationship.id)).where(Relationship.relationship_type == RelationshipType.CONTRADICTS)
        )).scalar_one()
        contextual = (await session.execute(
            select(func.count(Relationship.id)).where(
                Relationship.relationship_type.in_([
                    RelationshipType.TEMPORALLY_DISTINCT,
                    RelationshipType.DISTINCT_SCOPE,
                    RelationshipType.APPARENT_CONTRADICTION,
                ])
            )
        )).scalar_one()

    print("\n" + "=" * 60)
    print("  Knowledge Layer Summary")
    print("=" * 60)
    print(f"  Documents        : {total_docs}")
    print(f"  Pages            : {total_pages}")
    print(f"  Facts            : {total_facts}")
    print(f"  Grounded Facts   : {grounded}")
    print(f"  Corroborations   : {corroborations}")
    print(f"  Contradictions   : {contradictions}")
    print(f"  Contextual       : {contextual}")
    print("=" * 60)
    print("\n  Open http://localhost:5173 to explore the UI.")
    print("  API docs: http://localhost:8000/docs\n")


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
