"""
Unit normalization framework.
A small, general framework — NOT a hard-coded ontology.
Maps common aliases to canonical units. Preserves unknown units raw.
Does NOT convert currencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class UnitNormalization:
    raw_unit: str
    canonical_unit: Optional[str]  # None if unknown
    normalization_available: bool
    category: Optional[str]  # mass, distance, percentage, count, monetary, etc.


# Canonical unit -> list of known aliases (lowercase)
_UNIT_ALIASES: dict[str, list[str]] = {
    # Percentage
    "%": ["percent", "percentage", "pct", "per cent"],
    # Mass
    "kg": ["kilogram", "kilograms", "kgs"],
    "g": ["gram", "grams"],
    "tonne": ["metric ton", "metric tonne", "tonnes", "tons", "mt"],
    # Distance
    "km": ["kilometer", "kilometers", "kilometre", "kilometres"],
    "m": ["meter", "meters", "metre", "metres"],
    "mile": ["miles", "mi"],
    # Area
    "sqkm": ["sq km", "sq. km", "km²", "square kilometers", "square kilometres"],
    "sqm": ["sq m", "sq. m", "m²", "square meters", "square metres"],
    "hectare": ["hectares", "ha"],
    "acre": ["acres"],
    # Volume
    "liter": ["liters", "litre", "litres", "l"],
    "ml": ["milliliter", "milliliters", "millilitre", "millilitres"],
    # Time-period units
    "year": ["years", "yr", "yrs", "annual", "annually", "per year", "p.a."],
    "month": ["months", "monthly"],
    "day": ["days", "daily"],
    # Count / people
    "employees": [
        "staff", "workforce", "workers", "headcount", "people",
        "full-time employees", "fte", "ftes",
    ],
    "customers": ["customer", "users", "subscribers", "clients"],
    "shipments": ["shipment", "parcels", "parcel", "packages", "package"],
    # Speed
    "kmph": ["km/h", "km/hr", "kmh", "kph"],
    # Monetary (kept as-is, no conversion)
    "INR": ["rs", "rs.", "inr", "rupee", "rupees", "₹"],
    "USD": ["usd", "us$", "$", "dollar", "dollars"],
    "EUR": ["eur", "€", "euro", "euros"],
    "GBP": ["gbp", "£", "pound", "pounds"],
}

# Reverse map: alias -> canonical
_ALIAS_MAP: dict[str, str] = {}
for canonical, aliases in _UNIT_ALIASES.items():
    for alias in aliases:
        _ALIAS_MAP[alias.lower()] = canonical
    _ALIAS_MAP[canonical.lower()] = canonical

_UNIT_CATEGORIES: dict[str, str] = {
    "%": "percentage",
    "kg": "mass", "g": "mass", "tonne": "mass",
    "km": "distance", "m": "distance", "mile": "distance",
    "sqkm": "area", "sqm": "area", "hectare": "area", "acre": "area",
    "liter": "volume", "ml": "volume",
    "year": "time", "month": "time", "day": "time",
    "employees": "count", "customers": "count", "shipments": "count",
    "kmph": "speed",
    "INR": "monetary", "USD": "monetary", "EUR": "monetary", "GBP": "monetary",
}


def normalize_unit(raw_unit: Optional[str]) -> UnitNormalization:
    """
    Normalize a raw unit string to its canonical form.
    Returns UnitNormalization with normalization_available=False for unknown units.
    """
    if not raw_unit or not raw_unit.strip():
        return UnitNormalization(
            raw_unit=raw_unit or "",
            canonical_unit=None,
            normalization_available=False,
            category=None,
        )

    key = raw_unit.strip().lower()
    canonical = _ALIAS_MAP.get(key)
    if canonical:
        return UnitNormalization(
            raw_unit=raw_unit,
            canonical_unit=canonical,
            normalization_available=True,
            category=_UNIT_CATEGORIES.get(canonical),
        )

    # Unknown unit — preserve raw, do not invent a conversion
    return UnitNormalization(
        raw_unit=raw_unit,
        canonical_unit=None,
        normalization_available=False,
        category=None,
    )


def units_compatible(unit_a: Optional[str], unit_b: Optional[str]) -> bool:
    """Return True if two units are in the same category and can be compared."""
    u_a = normalize_unit(unit_a)
    u_b = normalize_unit(unit_b)
    if u_a.canonical_unit and u_b.canonical_unit:
        if u_a.canonical_unit == u_b.canonical_unit:
            return True
        # Same category allows comparison (e.g. km vs miles)
        if u_a.category and u_b.category and u_a.category == u_b.category:
            return u_a.category != "monetary"  # monetary NEVER auto-converted
    return False
