"""
PDF text extraction using PyMuPDF.

Extracts text at three granularities:
  - blocks  (page.get_text("blocks", sort=True))
  - words   (page.get_text("words",  sort=True))
  - plain   (page.get_text("text",   sort=True))

Preserves document_id, page_number, block_id, bounding box, text, reading order.
Detects sparse pages and flags them for fallback handling.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

# Minimum character density (chars per page area in pts²) to consider a page
# as having usable extractable text.
SPARSE_CHAR_PER_AREA_THRESHOLD = 0.0002


@dataclass
class WordToken:
    text: str
    bbox: list[float]  # [x0, y0, x1, y1]
    block_no: int
    line_no: int
    word_no: int


@dataclass
class Block:
    block_no: int
    block_type: int  # 0=text, 1=image
    bbox: list[float]
    text: str
    lines: list[str] = field(default_factory=list)


@dataclass
class PageExtraction:
    page_number: int  # 0-indexed internally, stored as 1-indexed
    width: float
    height: float
    plain_text: str
    blocks: list[Block]
    words: list[WordToken]
    char_count: int
    is_sparse: bool
    extraction_method: str = "pymupdf"
    extraction_time_ms: float = 0.0


@dataclass
class DocumentExtraction:
    path: str
    page_count: int
    pages: list[PageExtraction]
    sparse_page_count: int
    total_chars: int
    extraction_time_ms: float


def _is_sparse(page_text: str, width: float, height: float) -> bool:
    """Return True if this page appears to have insufficient extractable text."""
    if width <= 0 or height <= 0:
        return True
    area = width * height
    density = len(page_text.strip()) / area
    return density < SPARSE_CHAR_PER_AREA_THRESHOLD


def extract_page(fitz_page: fitz.Page, page_number: int) -> PageExtraction:
    """Extract all text data from a single PyMuPDF page."""
    t0 = time.perf_counter()

    # 1. Plain text (reading order)
    plain_text: str = fitz_page.get_text("text", sort=True)

    # 2. Blocks
    raw_blocks = fitz_page.get_text("blocks", sort=True)
    blocks: list[Block] = []
    for b in raw_blocks:
        # b = (x0, y0, x1, y1, text, block_no, block_type)
        if len(b) >= 7:
            x0, y0, x1, y1, txt, bno, btype = b[:7]
            lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
            blocks.append(
                Block(
                    block_no=bno,
                    block_type=btype,
                    bbox=[x0, y0, x1, y1],
                    text=txt.strip(),
                    lines=lines,
                )
            )

    # 3. Words (for fine-grained span location)
    raw_words = fitz_page.get_text("words", sort=True)
    words: list[WordToken] = []
    for w in raw_words:
        # w = (x0, y0, x1, y1, word, block_no, line_no, word_no)
        if len(w) >= 8:
            x0, y0, x1, y1, word_text, bno, lno, wno = w[:8]
            words.append(
                WordToken(
                    text=word_text,
                    bbox=[x0, y0, x1, y1],
                    block_no=bno,
                    line_no=lno,
                    word_no=wno,
                )
            )

    rect = fitz_page.rect
    width, height = rect.width, rect.height
    is_sparse = _is_sparse(plain_text, width, height)
    elapsed = (time.perf_counter() - t0) * 1000

    return PageExtraction(
        page_number=page_number + 1,  # 1-indexed for storage
        width=width,
        height=height,
        plain_text=plain_text,
        blocks=blocks,
        words=words,
        char_count=len(plain_text),
        is_sparse=is_sparse,
        extraction_time_ms=elapsed,
    )


def extract_document(path: Path | str) -> DocumentExtraction:
    """
    Extract all pages from a PDF.
    Processes page-by-page to avoid loading the entire PDF into memory.
    """
    path = Path(path)
    t0 = time.perf_counter()
    logger.info("pdf_extraction_start", path=str(path))

    pages: list[PageExtraction] = []
    sparse_count = 0
    total_chars = 0

    try:
        doc = fitz.open(str(path))
        page_count = doc.page_count

        for i in range(page_count):
            try:
                fitz_page = doc.load_page(i)
                page_ext = extract_page(fitz_page, i)
                pages.append(page_ext)
                total_chars += page_ext.char_count
                if page_ext.is_sparse:
                    sparse_count += 1
                    logger.warning(
                        "sparse_page_detected",
                        path=path.name,
                        page=page_ext.page_number,
                        char_count=page_ext.char_count,
                    )
                fitz_page = None  # release memory
            except Exception as exc:
                logger.error("page_extraction_error", page=i, error=str(exc))

        doc.close()
    except Exception as exc:
        logger.error("document_open_error", path=str(path), error=str(exc))
        raise

    elapsed = (time.perf_counter() - t0) * 1000
    logger.info(
        "pdf_extraction_complete",
        path=path.name,
        pages=len(pages),
        sparse=sparse_count,
        chars=total_chars,
        elapsed_ms=round(elapsed, 1),
    )

    return DocumentExtraction(
        path=str(path),
        page_count=page_count,
        pages=pages,
        sparse_page_count=sparse_count,
        total_chars=total_chars,
        extraction_time_ms=elapsed,
    )


def find_text_bbox(
    page_ext: PageExtraction, target_text: str, max_results: int = 5
) -> list[list[float]]:
    """
    Locate bounding boxes for a target substring using word-level data.
    Returns a list of [x0, y0, x1, y1] bounding boxes.
    """
    target_lower = target_text.lower().strip()
    target_words = target_lower.split()
    if not target_words:
        return []

    # Build a flat list of words for sliding window
    word_tokens = [(w.text.lower(), w.bbox) for w in page_ext.words]
    results: list[list[float]] = []

    for start in range(len(word_tokens) - len(target_words) + 1):
        window = word_tokens[start : start + len(target_words)]
        window_text = " ".join(w[0] for w in window)
        if target_lower in window_text or all(tw in window_text for tw in target_words[:3]):
            # Merge bboxes
            bboxes = [w[1] for w in window]
            x0 = min(b[0] for b in bboxes)
            y0 = min(b[1] for b in bboxes)
            x1 = max(b[2] for b in bboxes)
            y1 = max(b[3] for b in bboxes)
            results.append([x0, y0, x1, y1])
            if len(results) >= max_results:
                break

    return results
