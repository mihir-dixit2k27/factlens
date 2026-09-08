"""
Semantic chunker: splits page blocks into overlapping chunks suitable for LLM extraction.
Preserves document_id, page_number, block_id, reading order, and an approximate bounding box
for the entire chunk.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import get_settings
from app.ingestion.pdf_extractor import DocumentExtraction, PageExtraction

settings = get_settings()

# Rough chars-per-token estimate for chunking without a full tokenizer
_CHARS_PER_TOKEN = 4


@dataclass
class TextChunk:
    document_path: str
    page_number: int
    chunk_index: int
    text: str
    token_estimate: int
    bbox: Optional[dict]  # {"x0": f, "y0": f, "x1": f, "y1": f}
    block_ids: list[int] = field(default_factory=list)
    extraction_method: str = "pymupdf"


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _merge_bboxes(bboxes: list[list[float]]) -> Optional[dict]:
    if not bboxes:
        return None
    x0 = min(b[0] for b in bboxes)
    y0 = min(b[1] for b in bboxes)
    x1 = max(b[2] for b in bboxes)
    y1 = max(b[3] for b in bboxes)
    return {"x0": x0, "y0": y0, "x1": x1, "y1": y1}


def chunk_page(page_ext: PageExtraction, doc_path: str, chunk_offset: int = 0) -> list[TextChunk]:
    """
    Chunk a single page's blocks into token-bounded chunks with overlap.
    Text blocks are the primary unit; we concatenate blocks until the token
    budget is reached, then emit a chunk and continue with overlap.
    """
    max_tokens = settings.chunk_max_tokens
    overlap_tokens = settings.chunk_overlap_tokens

    # Filter to text blocks only (block_type == 0)
    text_blocks = [b for b in page_ext.blocks if b.block_type == 0 and b.text.strip()]
    if not text_blocks:
        return []

    chunks: list[TextChunk] = []
    current_texts: list[str] = []
    current_block_ids: list[int] = []
    current_bboxes: list[list[float]] = []
    current_tokens = 0
    chunk_idx = chunk_offset

    def emit_chunk(texts: list[str], block_ids: list[int], bboxes: list[list[float]]) -> TextChunk:
        nonlocal chunk_idx
        combined = " ".join(texts).strip()
        c = TextChunk(
            document_path=doc_path,
            page_number=page_ext.page_number,
            chunk_index=chunk_idx,
            text=combined,
            token_estimate=_estimate_tokens(combined),
            bbox=_merge_bboxes(bboxes),
            block_ids=list(block_ids),
        )
        chunk_idx += 1
        return c

    for block in text_blocks:
        block_tokens = _estimate_tokens(block.text)
        if current_tokens + block_tokens > max_tokens and current_texts:
            chunks.append(emit_chunk(current_texts, current_block_ids, current_bboxes))
            # Overlap: keep last N tokens worth of text
            overlap_target = overlap_tokens * _CHARS_PER_TOKEN
            leftover = ""
            for t in reversed(current_texts):
                if len(leftover) < overlap_target:
                    leftover = t + " " + leftover
                else:
                    break
            current_texts = [leftover.strip()] if leftover.strip() else []
            current_block_ids = []
            current_bboxes = []
            current_tokens = _estimate_tokens(leftover)

        current_texts.append(block.text)
        current_block_ids.append(block.block_no)
        current_bboxes.append(block.bbox)
        current_tokens += block_tokens

    if current_texts:
        chunks.append(emit_chunk(current_texts, current_block_ids, current_bboxes))

    return chunks


def chunk_document(doc_ext: DocumentExtraction) -> list[TextChunk]:
    """Chunk all pages of a document."""
    all_chunks: list[TextChunk] = []
    chunk_offset = 0
    for page in doc_ext.pages:
        page_chunks = chunk_page(page, doc_ext.path, chunk_offset)
        all_chunks.extend(page_chunks)
        chunk_offset += len(page_chunks)
    return all_chunks
