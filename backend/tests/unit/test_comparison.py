"""
Unit tests for the comparison engine (contradiction detection).
Uses synthetic fact objects — no starter-PDF specifics.
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock
from app.db.models import Fact, ObjectType, RelationshipType
from app.reconciliation.comparison_engine import compare


def _make_fact(
    predicate: str,
    object_text: str,
    numeric_value=None,
    normalized_value=None,
    object_type=ObjectType.MONETARY,
    unit=None,
    currency=None,
    temporal_scope=None,
    geographic_scope=None,
    population_scope=None,
    entity_id=None,
    doc_id="doc-A",
) -> Fact:
    f = MagicMock(spec=Fact)
    f.id = f"fact-{predicate[:10]}-{doc_id}"
    f.predicate = predicate
    f.object_text = object_text
    f.numeric_value = numeric_value
    f.normalized_value = normalized_value
    f.object_type = object_type
    f.unit = unit
    f.normalized_unit = unit
    f.currency = currency
    f.temporal_scope = temporal_scope
    f.geographic_scope = geographic_scope
    f.population_scope = population_scope
    f.subject_entity_id = entity_id
    f.primary_document_id = doc_id
    return f


# CASE A: Values within tolerance -> CORROBORATES
def test_corroborates_within_tolerance() -> None:
    """'$1.2 billion' and '~$1.21B in FY2024' should CORROBORATE."""
    fa = _make_fact("revenue", "$1.2 billion", numeric_value=1.2e9, normalized_value=1.2e9,
                    currency="USD", doc_id="doc-A")
    fb = _make_fact("revenue", "$1.21B", numeric_value=1.21e9, normalized_value=1.21e9,
                    currency="USD", doc_id="doc-B")
    result = compare(fa, fb)
    assert result.relationship_type == RelationshipType.CORROBORATES


# CASE B: Different fiscal years -> TEMPORALLY_DISTINCT
def test_temporally_distinct() -> None:
    """FY2023 $900M vs FY2024 $1.2B — should be TEMPORALLY_DISTINCT."""
    fa = _make_fact("revenue", "$900M", numeric_value=9e8, normalized_value=9e8,
                    currency="USD", temporal_scope={"type": "fiscal_year", "fiscal_year": 2023, "start": "2023"},
                    doc_id="doc-A")
    fb = _make_fact("revenue", "$1.2B", numeric_value=1.2e9, normalized_value=1.2e9,
                    currency="USD", temporal_scope={"type": "fiscal_year", "fiscal_year": 2024, "start": "2024"},
                    doc_id="doc-B")
    result = compare(fa, fb)
    assert result.relationship_type == RelationshipType.TEMPORALLY_DISTINCT
    assert "temporal" in result.context_factors[0]


# CASE C: Different geographic scopes -> DISTINCT_SCOPE
def test_distinct_scope_geographic() -> None:
    """'European revenue $500M' vs 'Global revenue $1.2B' — DISTINCT_SCOPE."""
    fa = _make_fact("revenue", "$500M", numeric_value=5e8, normalized_value=5e8,
                    currency="USD", geographic_scope="Europe", doc_id="doc-A")
    fb = _make_fact("revenue", "$1.2B", numeric_value=1.2e9, normalized_value=1.2e9,
                    currency="USD", geographic_scope="Global", doc_id="doc-B")
    result = compare(fa, fb)
    assert result.relationship_type == RelationshipType.DISTINCT_SCOPE


# CASE D: Same time scope, material disagreement -> CONTRADICTS
def test_contradicts_material_difference() -> None:
    """Same FY, same scope, $5B vs $3B — should CONTRADICT."""
    scope = {"type": "fiscal_year", "fiscal_year": 2024, "start": "2024"}
    fa = _make_fact("revenue", "$5B", numeric_value=5e9, normalized_value=5e9,
                    currency="USD", temporal_scope=scope, doc_id="doc-A")
    fb = _make_fact("revenue", "$3B", numeric_value=3e9, normalized_value=3e9,
                    currency="USD", temporal_scope=scope, doc_id="doc-B")
    result = compare(fa, fb)
    assert result.relationship_type == RelationshipType.CONTRADICTS


# CASE E: Currency mismatch -> UNIT_MISMATCH
def test_currency_mismatch() -> None:
    fa = _make_fact("revenue", "$5B", numeric_value=5e9, currency="USD", doc_id="doc-A")
    fb = _make_fact("revenue", "€5B", numeric_value=5e9, currency="EUR", doc_id="doc-B")
    result = compare(fa, fb)
    assert result.relationship_type == RelationshipType.UNIT_MISMATCH
    assert "currency" in result.context_factors


# CASE F: No numeric values -> UNCERTAIN
def test_uncertain_without_numeric() -> None:
    fa = _make_fact("employee_satisfaction", "positive", object_type=ObjectType.TEXT, doc_id="doc-A")
    fb = _make_fact("employee_satisfaction", "high", object_type=ObjectType.TEXT, doc_id="doc-B")
    result = compare(fa, fb)
    assert result.relationship_type == RelationshipType.UNCERTAIN
    assert result.deterministic is False
