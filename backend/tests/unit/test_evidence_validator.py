"""Unit tests for evidence validator."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from app.extraction.evidence_validator import validate_fact_grounding
from app.extraction.llm_provider import ExtractedFactRaw


def _make_raw_fact(
    subject="Test Corp",
    predicate="revenue",
    object_text="$1.2 billion",
    evidence_span="Test Corp reported revenue of $1.2 billion in FY2024.",
    confidence=0.95,
) -> ExtractedFactRaw:
    return ExtractedFactRaw(
        subject=subject,
        predicate=predicate,
        object_text=object_text,
        object_type="MONETARY",
        numeric_value=1.2e9,
        confidence=confidence,
        uncertainty_reasons=[],
        evidence_span=evidence_span,
    )


def test_valid_grounding() -> None:
    fact = _make_raw_fact()
    chunk = "Test Corp reported revenue of $1.2 billion in FY2024, a significant milestone."
    result = validate_fact_grounding(fact, chunk)
    assert result.is_valid is True


def test_empty_span_rejected() -> None:
    fact = _make_raw_fact(evidence_span="")
    chunk = "Some chunk text here for testing purposes."
    result = validate_fact_grounding(fact, chunk)
    assert result.is_valid is False
    assert "empty" in result.failure_reason.lower()


def test_short_span_rejected() -> None:
    fact = _make_raw_fact(evidence_span="ok")
    chunk = "ok, this is a test chunk"
    result = validate_fact_grounding(fact, chunk)
    assert result.is_valid is False


def test_low_chunk_coverage_rejected() -> None:
    # Span has words not in chunk (hallucination scenario)
    fact = _make_raw_fact(
        evidence_span="completely fabricated revenue figure for non-existent company"
    )
    chunk = "The GDP growth rate was 6.5% in the current fiscal year."
    result = validate_fact_grounding(fact, chunk)
    assert result.is_valid is False
