"""
PDF inspection CLI tool.

Usage:
    python -m app.cli.inspect_pdfs [--dir PATH]

Prints:
  - Discovered PDFs
  - Page counts
  - Extractable text stats
  - Sparse (image-based) pages
  - Tables detected (block-level heuristic)
  - Extraction timings
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def run(data_dir: str) -> None:
    from app.ingestion.pdf_discovery import discover_pdfs
    from app.ingestion.pdf_extractor import extract_document

    root = Path(data_dir)
    print(f"\n{'='*60}")
    print(f"  FactLens PDF Inspector")
    print(f"  Scanning: {root.resolve()}")
    print(f"{'='*60}\n")

    pdfs = discover_pdfs(root)
    if not pdfs:
        print("  No PDFs found.")
        return

    for i, pdf in enumerate(pdfs, 1):
        print(f"[{i}/{len(pdfs)}] {pdf.filename}")
        print(f"  Dataset  : {pdf.dataset}")
        print(f"  Size     : {pdf.file_size_bytes / 1024:.1f} KB")
        print(f"  Hash     : {pdf.file_hash[:16]}...")

        t0 = time.perf_counter()
        try:
            doc_ext = extract_document(pdf.path)
        except Exception as exc:
            print(f"  ERROR    : {exc}")
            print()
            continue
        elapsed = (time.perf_counter() - t0) * 1000

        sparse_pages = [p.page_number for p in doc_ext.pages if p.is_sparse]
        total_blocks = sum(len(p.blocks) for p in doc_ext.pages)
        # Table heuristic: blocks with pipe characters or many short lines
        table_pages = []
        for p in doc_ext.pages:
            for b in p.blocks:
                if b.block_type == 0 and ("|" in b.text or b.text.count("\n") > 5):
                    table_pages.append(p.page_number)
                    break

        print(f"  Pages    : {doc_ext.page_count}")
        print(f"  Chars    : {doc_ext.total_chars:,}")
        print(f"  Blocks   : {total_blocks}")
        print(f"  Sparse   : {doc_ext.sparse_page_count} pages {sparse_pages[:5]}")
        print(f"  Tables~  : {len(set(table_pages))} pages (heuristic)")
        print(f"  Time     : {elapsed:.0f} ms")
        print()

    print(f"{'='*60}")
    print(f"  Total PDFs: {len(pdfs)}")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="FactLens PDF Inspector")
    parser.add_argument(
        "--dir",
        default="../../starter-datasets",
        help="Root directory to scan for PDFs",
    )
    args = parser.parse_args()
    run(args.dir)


if __name__ == "__main__":
    main()
