"""PDF discovery utility - recursively finds all PDF files."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class DiscoveredPDF:
    path: Path
    filename: str
    file_size_bytes: int
    file_hash: str
    dataset: str  # parent directory name, e.g. "delhivery"
    relative_path: str


def compute_sha256(path: Path, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hash of a file without loading it entirely into memory."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def discover_pdfs(root_dir: Path | str) -> list[DiscoveredPDF]:
    """
    Recursively discover all PDF files under root_dir.
    Returns metadata for each discovered PDF.
    """
    root = Path(root_dir).resolve()
    if not root.exists():
        logger.warning("discovery_root_not_found", path=str(root))
        return []

    discovered: list[DiscoveredPDF] = []
    for pdf_path in sorted(root.rglob("*.pdf")):
        try:
            stat = pdf_path.stat()
            file_hash = compute_sha256(pdf_path)
            # Use parent directory name as dataset label
            dataset = pdf_path.parent.name if pdf_path.parent != root else "default"
            rel_path = str(pdf_path.relative_to(root))
            discovered.append(
                DiscoveredPDF(
                    path=pdf_path,
                    filename=pdf_path.name,
                    file_size_bytes=stat.st_size,
                    file_hash=file_hash,
                    dataset=dataset,
                    relative_path=rel_path,
                )
            )
            logger.info(
                "pdf_discovered",
                filename=pdf_path.name,
                size_bytes=stat.st_size,
                dataset=dataset,
            )
        except Exception as exc:
            logger.warning("pdf_discovery_error", path=str(pdf_path), error=str(exc))

    logger.info("pdf_discovery_complete", count=len(discovered), root=str(root))
    return discovered
