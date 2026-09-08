"""Unit tests for numeric normalization."""
from __future__ import annotations

import pytest
from app.normalization.numeric import normalize_numeric


@pytest.mark.parametrize("raw, expected", [
    ("1,000,000", 1_000_000.0),
    ("1 million", 1_000_000.0),
    ("1M", 1_000_000.0),
    ("1.5 billion", 1_500_000_000.0),
    ("$4.2B", 4_200_000_000.0),
    ("₹3.0 trillion", 3_000_000_000_000.0),
    ("~20%", 20.0),
    ("approximately 5.5 lakh", 550_000.0),
    ("50K", 50_000.0),
])
def test_normalize_numeric_values(raw: str, expected: float) -> None:
    result = normalize_numeric(raw)
    assert result.normalized_value is not None, f"Expected numeric value from {raw!r}"
    assert abs(result.normalized_value - expected) < expected * 0.01, (
        f"normalize_numeric({raw!r}) = {result.normalized_value}, expected ~{expected}"
    )


def test_approximate_modality() -> None:
    result = normalize_numeric("approximately 1.2 billion")
    assert result.modality == "approximately"


def test_range_detection() -> None:
    result = normalize_numeric("$3B–$4B")
    assert result.is_range is True
    assert result.range_low is not None
    assert result.range_high is not None


def test_currency_detection() -> None:
    result = normalize_numeric("$5B")
    assert result.currency == "USD"


def test_rupee_currency() -> None:
    result = normalize_numeric("₹2.5 trillion")
    assert result.currency == "INR"


def test_empty_input() -> None:
    result = normalize_numeric("")
    assert result.normalized_value is None
    assert result.confidence == 0.0


def test_plain_number() -> None:
    result = normalize_numeric("42")
    assert result.normalized_value == 42.0
