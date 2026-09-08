"""
Temporal scope parser.
Parses time references from document text into structured TemporalScope objects.
Supports: fiscal years, quarters, calendar years, date ranges, "as of" dates,
reporting periods, and publication dates.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


@dataclass
class TemporalScope:
    type: str   # fiscal_year | quarter | calendar_year | date_range | point | reporting_period | unknown
    start: Optional[str] = None          # ISO date string or year string
    end: Optional[str] = None
    label: Optional[str] = None          # Original label, e.g. "FY2024", "Q4 FY24"
    fiscal_year: Optional[int] = None    # e.g. 2024
    quarter: Optional[int] = None        # 1-4
    confidence: float = 1.0


_FY_PATTERNS = [
    # "FY2024", "FY 2024", "FY24"
    re.compile(r"\bFY\s*(?P<year>\d{4})\b", re.IGNORECASE),
    re.compile(r"\bFY\s*(?P<year2>\d{2})\b", re.IGNORECASE),
    # "2024-25", "2023-24" (Indian fiscal year notation)
    re.compile(r"\b(?P<y1>\d{4})-(?P<y2>\d{2})\b"),
    # "fiscal year 2024", "financial year 2024"
    re.compile(r"\b(?:fiscal|financial)\s+year\s+(?P<fyear>\d{4})\b", re.IGNORECASE),
    # "FY2023-24"
    re.compile(r"\bFY\s*(?P<fy1>\d{4})-(?P<fy2>\d{2})\b", re.IGNORECASE),
]

_QUARTER_PATTERNS = [
    # "Q4 FY24", "Q1 FY2024"
    re.compile(r"\bQ(?P<q>[1-4])\s*FY\s*(?P<year>\d{4}|\d{2})\b", re.IGNORECASE),
    # "fourth quarter 2024"
    re.compile(
        r"\b(?P<qname>first|second|third|fourth)\s+quarter\s+(?:of\s+)?(?P<qyear>\d{4})\b",
        re.IGNORECASE,
    ),
]

_QUARTER_NAMES = {"first": 1, "second": 2, "third": 3, "fourth": 4}

_MONTH_NAMES = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04", "jun": "06",
    "jul": "07", "aug": "08", "sep": "09", "oct": "10", "nov": "11", "dec": "12",
}

_AS_OF_PATTERN = re.compile(
    r"\bas\s+of\s+(?P<month>\w+)\s+(?P<day>\d{1,2})?,?\s*(?P<year>\d{4})\b",
    re.IGNORECASE,
)
_CALENDAR_YEAR_PATTERN = re.compile(r"\b(?P<year>20\d{2})\b")


def _resolve_year(short_year: str) -> int:
    """Convert 2-digit year to 4-digit (e.g. '24' -> 2024). Assumes 2000s."""
    y = int(short_year)
    return y + 2000 if y < 100 else y


def parse_temporal_scope(text: str) -> Optional[TemporalScope]:
    """
    Extract the first temporal reference from text.
    Returns None if no temporal reference found.
    """
    if not text:
        return None

    # Quarters first (more specific)
    for pat in _QUARTER_PATTERNS:
        m = pat.search(text)
        if m:
            gd = m.groupdict()
            if "q" in gd and gd["q"]:
                quarter = int(gd["q"])
                year = _resolve_year(gd["year"])
            elif "qname" in gd and gd["qname"]:
                quarter = _QUARTER_NAMES.get(gd["qname"].lower(), 1)
                year = int(gd["qyear"])
            else:
                continue
            label = m.group(0)
            return TemporalScope(
                type="quarter",
                label=label,
                fiscal_year=year,
                quarter=quarter,
                start=f"{year}",
                confidence=0.95,
            )

    # Fiscal year patterns
    for pat in _FY_PATTERNS:
        m = pat.search(text)
        if m:
            gd = m.groupdict()
            label = m.group(0)
            if "year" in gd and gd.get("year"):
                year = _resolve_year(gd["year"])
            elif "year2" in gd and gd.get("year2"):
                year = _resolve_year(gd["year2"])
            elif "fyear" in gd and gd.get("fyear"):
                year = int(gd["fyear"])
            elif "y1" in gd and gd.get("y1"):
                year = int(gd["y1"])
                end_year = int(gd["y1"][:2] + gd["y2"])
                return TemporalScope(
                    type="fiscal_year",
                    label=label,
                    fiscal_year=year,
                    start=str(year),
                    end=str(end_year),
                    confidence=0.93,
                )
            elif "fy1" in gd and gd.get("fy1"):
                year = int(gd["fy1"])
            else:
                continue
            return TemporalScope(
                type="fiscal_year",
                label=label,
                fiscal_year=year,
                start=str(year),
                confidence=0.93,
            )

    # "as of" date
    m = _AS_OF_PATTERN.search(text)
    if m:
        month_str = m.group("month").lower()
        month_num = _MONTH_NAMES.get(month_str, "01")
        year = int(m.group("year"))
        day = m.group("day") or "01"
        date_str = f"{year}-{month_num}-{int(day):02d}"
        return TemporalScope(
            type="point",
            label=m.group(0),
            start=date_str,
            confidence=0.97,
        )

    # Calendar year
    m = _CALENDAR_YEAR_PATTERN.search(text)
    if m:
        year = int(m.group("year"))
        if 2000 <= year <= 2035:
            return TemporalScope(
                type="calendar_year",
                label=str(year),
                fiscal_year=year,
                start=str(year),
                confidence=0.80,
            )

    return None


def temporal_scopes_overlap(a: Optional[TemporalScope], b: Optional[TemporalScope]) -> bool:
    """Return True if two temporal scopes might refer to the same time period."""
    if a is None or b is None:
        return True  # Unknown scope — assume possible overlap

    # Same fiscal year
    if a.fiscal_year and b.fiscal_year:
        return abs(a.fiscal_year - b.fiscal_year) <= 0  # strict same year
    return True  # fallback: unknown overlap


def temporal_scopes_differ(a: Optional[TemporalScope], b: Optional[TemporalScope]) -> bool:
    """Return True if the two scopes can be confidently identified as different time periods."""
    if a is None or b is None:
        return False
    if a.fiscal_year and b.fiscal_year:
        return a.fiscal_year != b.fiscal_year
    if a.start and b.start:
        return a.start[:4] != b.start[:4]
    return False
