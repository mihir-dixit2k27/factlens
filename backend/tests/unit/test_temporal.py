"""Unit tests for temporal scope parsing."""
from __future__ import annotations

import pytest
from app.normalization.temporal import parse_temporal_scope, temporal_scopes_differ


@pytest.mark.parametrize("text, expected_type, expected_fy", [
    ("FY2024", "fiscal_year", 2024),
    ("FY24", "fiscal_year", 2024),
    ("2024-25", "fiscal_year", 2024),
    ("fiscal year 2023", "fiscal_year", 2023),
    ("Q4 FY24", "quarter", 2024),
    ("Q1 FY2025", "quarter", 2025),
    ("in 2023", "calendar_year", 2023),
])
def test_parse_temporal_scope(text: str, expected_type: str, expected_fy: int) -> None:
    result = parse_temporal_scope(text)
    assert result is not None, f"Expected temporal scope from {text!r}"
    assert result.type == expected_type
    assert result.fiscal_year == expected_fy


def test_as_of_date() -> None:
    result = parse_temporal_scope("as of March 31, 2025")
    assert result is not None
    assert result.type == "point"
    assert "2025" in result.start


def test_no_temporal_scope() -> None:
    result = parse_temporal_scope("The company has many employees")
    assert result is None


def test_temporal_scopes_differ() -> None:
    from app.normalization.temporal import TemporalScope
    a = TemporalScope(type="fiscal_year", fiscal_year=2023, start="2023")
    b = TemporalScope(type="fiscal_year", fiscal_year=2024, start="2024")
    assert temporal_scopes_differ(a, b) is True


def test_temporal_scopes_same() -> None:
    from app.normalization.temporal import TemporalScope
    a = TemporalScope(type="fiscal_year", fiscal_year=2024, start="2024")
    b = TemporalScope(type="fiscal_year", fiscal_year=2024, start="2024")
    assert temporal_scopes_differ(a, b) is False
