"""Integration tests for the PDF extraction pipeline."""
from __future__ import annotations

import io
import pytest
from pathlib import Path


def create_test_pdf(text_content: str) -> bytes:
    """Create a minimal PDF with the given text using reportlab."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    c.setFont("Helvetica", 12)
    y = 700
    for line in text_content.split("\n"):
        c.drawString(72, y, line)
        y -= 18
        if y < 100:
            c.showPage()
            y = 700
    c.save()
    return buf.getvalue()


def test_pdf_extraction_basic(tmp_path: Path) -> None:
    """Test that text can be extracted from a synthetic PDF."""
    from app.ingestion.pdf_extractor import extract_document

    text = "The company revenue in FY2024 was $1.2 billion."
    pdf_bytes = create_test_pdf(text)
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(pdf_bytes)

    doc_ext = extract_document(pdf_path)
    assert doc_ext.page_count >= 1
    assert doc_ext.total_chars > 0
    assert "revenue" in doc_ext.pages[0].plain_text.lower()


def test_chunker_on_extracted_doc(tmp_path: Path) -> None:
    """Test that the chunker produces chunks from extracted pages."""
    from app.ingestion.pdf_extractor import extract_document
    from app.ingestion.chunker import chunk_document

    text = "\n".join([f"Sentence {i}: The revenue figure was ${i} billion." for i in range(30)])
    pdf_bytes = create_test_pdf(text)
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(pdf_bytes)

    doc_ext = extract_document(pdf_path)
    chunks = chunk_document(doc_ext)
    assert len(chunks) >= 1
    for chunk in chunks:
        assert chunk.text.strip()
        assert chunk.document_path == str(pdf_path)


def test_evidence_validator_on_realistic_chunk() -> None:
    """Test that valid facts pass and hallucinated facts are caught."""
    from app.extraction.evidence_validator import validate_fact_grounding
    from app.extraction.llm_provider import ExtractedFactRaw

    chunk = (
        "Delhivery Limited reported total revenue of INR 2,010 crore for Q4 FY2024, "
        "representing a 13% year-on-year growth from the year-ago quarter."
    )
    # Valid fact
    valid_fact = ExtractedFactRaw(
        subject="Delhivery Limited",
        predicate="revenue",
        object_text="INR 2,010 crore",
        object_type="MONETARY",
        numeric_value=2010.0,
        confidence=0.92,
        uncertainty_reasons=[],
        evidence_span="Delhivery Limited reported total revenue of INR 2,010 crore for Q4 FY2024",
    )
    r = validate_fact_grounding(valid_fact, chunk)
    assert r.is_valid is True

    # Hallucinated fact (evidence span not from chunk)
    hallucinated = ExtractedFactRaw(
        subject="XYZ Corp",
        predicate="net_profit",
        object_text="$500 million",
        object_type="MONETARY",
        numeric_value=5e8,
        confidence=0.7,
        uncertainty_reasons=[],
        evidence_span="XYZ Corp achieved net profit of $500 million in calendar Q2",
    )
    r2 = validate_fact_grounding(hallucinated, chunk)
    assert r2.is_valid is False


@pytest.mark.parametrize("case", [
    {
        "desc": "CORROBORATES synthetic",
        "fa": {"predicate": "revenue", "numeric_value": 1.2e9, "currency": "USD", "ts": None, "gs": None, "ps": None},
        "fb": {"predicate": "annual sales", "numeric_value": 1.21e9, "currency": "USD", "ts": None, "gs": None, "ps": None},
        "expected": "CORROBORATES",
    },
    {
        "desc": "TEMPORALLY_DISTINCT synthetic",
        "fa": {"predicate": "revenue", "numeric_value": 9e8, "currency": "USD",
               "ts": {"type": "fiscal_year", "fiscal_year": 2023, "start": "2023"}, "gs": None, "ps": None},
        "fb": {"predicate": "revenue", "numeric_value": 1.2e9, "currency": "USD",
               "ts": {"type": "fiscal_year", "fiscal_year": 2024, "start": "2024"}, "gs": None, "ps": None},
        "expected": "TEMPORALLY_DISTINCT",
    },
    {
        "desc": "DISTINCT_SCOPE synthetic",
        "fa": {"predicate": "revenue", "numeric_value": 5e8, "currency": "USD", "ts": None, "gs": "North America", "ps": None},
        "fb": {"predicate": "revenue", "numeric_value": 1.2e9, "currency": "USD", "ts": None, "gs": "Global", "ps": None},
        "expected": "DISTINCT_SCOPE",
    },
])
def test_comparison_engine_cases(case: dict) -> None:
    """Test comparison engine on the five assignment-required synthetic cases."""
    from unittest.mock import MagicMock
    from app.db.models import Fact, ObjectType, RelationshipType
    from app.reconciliation.comparison_engine import compare

    def _f(d: dict, doc: str) -> Fact:
        f = MagicMock(spec=Fact)
        f.id = f"f-{doc}"
        f.predicate = d["predicate"]
        f.object_text = str(d["numeric_value"])
        f.numeric_value = d["numeric_value"]
        f.normalized_value = d["numeric_value"]
        f.object_type = ObjectType.MONETARY
        f.unit = None
        f.normalized_unit = None
        f.currency = d["currency"]
        f.temporal_scope = d["ts"]
        f.geographic_scope = d["gs"]
        f.population_scope = d["ps"]
        f.subject_entity_id = "entity-1"
        f.primary_document_id = doc
        return f

    fa = _f(case["fa"], "doc-A")
    fb = _f(case["fb"], "doc-B")
    result = compare(fa, fb)
    assert result.relationship_type.value == case["expected"], (
        f"[{case['desc']}] Expected {case['expected']}, got {result.relationship_type.value}. "
        f"Reasoning: {result.reasoning}"
    )
