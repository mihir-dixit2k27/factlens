"""
Numeric normalization: converts textual numeric representations to floats.
Handles: 1M, 1 million, 1,000,000, $4.2B, ~20%, approximately 1.5 billion, ranges.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_MULTIPLIERS = {
    "trillion": 1e12,
    "billion": 1e9,
    "bn": 1e9,
    "b": 1e9,   # standalone B/b suffix e.g. "4.2B"
    "million": 1e6,
    "mn": 1e6,
    "m": 1e6,   # only when used as suffix, e.g., "4.2M"
    "lakh": 1e5,
    "thousand": 1e3,
    "k": 1e3,
}

_CURRENCY_SYMBOLS = {
    "$": "USD",
    "₹": "INR",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "Rs": "INR",
    "Rs.": "INR",
    "INR": "INR",
    "USD": "USD",
    "EUR": "EUR",
}

_APPROXIMATE_MODIFIERS = frozenset(
    ["approximately", "approx", "about", "~", "nearly", "roughly", "around", "circa", "c."]
)


@dataclass
class NormalizationResult:
    raw_text: str
    normalized_value: Optional[float]
    currency: Optional[str]
    modality: Optional[str]  # "approximately", "exact", etc.
    unit_suffix: Optional[str]  # "billion", "million", etc.
    is_range: bool
    range_low: Optional[float]
    range_high: Optional[float]
    confidence: float
    error: Optional[str] = None


def _strip_commas(text: str) -> str:
    return re.sub(r"(?<=\d),(?=\d{3})", "", text)


def _detect_currency(text: str) -> tuple[str, Optional[str]]:
    """Strip and return currency symbol; returns (cleaned_text, currency_code)."""
    for sym, code in sorted(_CURRENCY_SYMBOLS.items(), key=lambda x: -len(x[0])):
        if sym in text:
            return text.replace(sym, "").strip(), code
    return text, None


def _detect_modality(text: str) -> tuple[str, Optional[str]]:
    """Remove approximate modifier words; returns (cleaned_text, modality)."""
    text_lower = text.lower()
    for mod in _APPROXIMATE_MODIFIERS:
        if text_lower.startswith(mod):
            return text[len(mod):].strip(), "approximately"
    return text, None


def normalize_numeric(raw: str) -> NormalizationResult:
    """
    Main entry point: normalize a raw numeric string.
    Returns NormalizationResult with normalized float value and metadata.
    """
    if not raw or not raw.strip():
        return NormalizationResult(
            raw_text=raw, normalized_value=None, currency=None, modality=None,
            unit_suffix=None, is_range=False, range_low=None, range_high=None,
            confidence=0.0, error="Empty input",
        )

    text = raw.strip()

    # Detect range first (e.g., "$3B–$4B", "3-4 million")
    # Pattern captures full tokens: optional currency + number + optional suffix
    _tok = r"[₹$€£¥]?[\d.,]+(?:\s*(?:trillion|billion|bn|million|mn|lakh|thousand|[bBmMkK]))?"
    range_match = re.search(
        rf"({_tok})\s*[-–—to]+\s*({_tok})",
        text,
        re.IGNORECASE,
    )
    if range_match:
        low_str = range_match.group(1).strip()
        high_str = range_match.group(2).strip()
        # Try to normalize each side
        low_res = normalize_numeric(low_str)
        # Inherit currency/suffix from low side if high side lacks it
        # e.g. "$3B–$4B" or "3-4 million" — both sides get parsed independently
        high_res = normalize_numeric(high_str)
        mid = None
        if low_res.normalized_value is not None and high_res.normalized_value is not None:
            mid = (low_res.normalized_value + high_res.normalized_value) / 2
        return NormalizationResult(
            raw_text=raw,
            normalized_value=mid,
            currency=low_res.currency or high_res.currency,
            modality="range",
            unit_suffix=low_res.unit_suffix or high_res.unit_suffix,
            is_range=True,
            range_low=low_res.normalized_value,
            range_high=high_res.normalized_value,
            confidence=0.8,
        )

    # Detect modality
    text, modality = _detect_modality(text)

    # Detect currency
    text, currency = _detect_currency(text)

    # Strip % sign
    is_percentage = "%" in text
    text = text.replace("%", "").strip()

    # Strip commas from numbers
    text = _strip_commas(text)

    # Match: optional number then optional multiplier suffix
    pattern = re.compile(
        r"(?P<number>[\d]+\.?\d*)\s*(?P<suffix>trillion|billion|bn|million|mn|lakh|thousand|[bBmMkK])\b",
        re.IGNORECASE,
    )
    m = pattern.search(text)
    if m:
        try:
            number = float(m.group("number"))
            suffix = m.group("suffix").lower()
            multiplier = _MULTIPLIERS.get(suffix, 1)
            value = number * multiplier
            return NormalizationResult(
                raw_text=raw,
                normalized_value=value,
                currency=currency,
                modality=modality or ("approximately" if "%" not in raw else "exact"),
                unit_suffix=suffix,
                is_range=False,
                range_low=None,
                range_high=None,
                confidence=0.95,
            )
        except ValueError:
            pass

    # Plain number
    plain_match = re.search(r"[\d]+\.?\d*", text)
    if plain_match:
        try:
            value = float(plain_match.group())
            if is_percentage:
                value = value  # keep as-is; unit is "%"
            return NormalizationResult(
                raw_text=raw,
                normalized_value=value,
                currency=currency,
                modality=modality or "stated",
                unit_suffix="%" if is_percentage else None,
                is_range=False,
                range_low=None,
                range_high=None,
                confidence=0.9,
            )
        except ValueError:
            pass

    return NormalizationResult(
        raw_text=raw,
        normalized_value=None,
        currency=currency,
        modality=modality,
        unit_suffix=None,
        is_range=False,
        range_low=None,
        range_high=None,
        confidence=0.2,
        error="Could not parse numeric value",
    )
