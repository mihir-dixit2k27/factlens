"""
Contradiction / Comparison Engine — the deterministic heart of FactLens.

compare(fact_a, fact_b) applies a structured decision tree before any LLM call:
  1. Unrelated? -> RELATED
  2. Temporal scopes differ? -> TEMPORALLY_DISTINCT
  3. Geographic/population scopes differ? -> DISTINCT_SCOPE
  4. Units differ and can't be normalized? -> UNIT_MISMATCH
  5. Currency differs? -> UNIT_MISMATCH (no conversion)
  6. Values within tolerance? -> CORROBORATES
  7. Values materially different? -> CONTRADICTS
  8. Default: UNCERTAIN

Thresholds are fact-type dependent, not globally hard-coded.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from app.db.models import Fact, ObjectType, RelationshipType
from app.normalization.temporal import temporal_scopes_differ
from app.normalization.units import units_compatible


@dataclass
class ComparisonResult:
    relationship_type: RelationshipType
    confidence: float
    reasoning: str
    context_factors: list[str]
    numeric_delta: Optional[float] = None
    numeric_delta_pct: Optional[float] = None
    deterministic: bool = True  # True if result came from rule-based logic (not LLM)


# Tolerances by object type (relative % difference for CORROBORATES)
_CORROBORATION_TOLERANCES: dict[str, float] = {
    ObjectType.MONETARY: 0.05,    # 5% relative diff
    ObjectType.PERCENTAGE: 0.02,  # 2 percentage-point absolute diff
    ObjectType.COUNT: 0.10,       # 10% relative diff
    ObjectType.NUMERIC: 0.05,
    ObjectType.RATIO: 0.05,
    ObjectType.RANGE: 0.10,
}
_DEFAULT_TOLERANCE = 0.05


def _tolerance(fact: Fact) -> float:
    return _CORROBORATION_TOLERANCES.get(fact.object_type, _DEFAULT_TOLERANCE)


def _relative_diff(a: float, b: float) -> float:
    """Symmetric relative difference: |a-b| / max(|a|, |b|, 1)"""
    denom = max(abs(a), abs(b), 1.0)
    return abs(a - b) / denom


def _absolute_diff(a: float, b: float) -> float:
    return abs(a - b)


def _share_entity_or_predicate(fact_a: Fact, fact_b: Fact) -> bool:
    """Check if two facts share a subject entity or have similar predicates."""
    if fact_a.subject_entity_id and fact_b.subject_entity_id:
        if fact_a.subject_entity_id == fact_b.subject_entity_id:
            return True
    # Predicate similarity (word overlap)
    pred_a_words = set(fact_a.predicate.lower().split())
    pred_b_words = set(fact_b.predicate.lower().split())
    if pred_a_words and pred_b_words:
        overlap = len(pred_a_words & pred_b_words) / max(len(pred_a_words), len(pred_b_words))
        return overlap >= 0.4
    return False


def _scope_differs(scope_a: Optional[str], scope_b: Optional[str]) -> bool:
    """Return True if scopes are both non-null and clearly different."""
    if not scope_a or not scope_b:
        return False
    a = scope_a.lower().strip()
    b = scope_b.lower().strip()
    if a == b:
        return False
    # One contains the other -> one is a subset (DISTINCT_SCOPE)
    if a in b or b in a:
        return True
    # No overlap
    words_a = set(a.split())
    words_b = set(b.split())
    overlap = len(words_a & words_b) / max(len(words_a), len(words_b), 1)
    return overlap < 0.3


def compare(fact_a: Fact, fact_b: Fact) -> ComparisonResult:
    """
    Deterministic comparison of two facts.
    Returns a ComparisonResult with relationship type, confidence, and reasoning.
    """
    context_factors: list[str] = []

    # Step 0: Same fact?
    if fact_a.id == fact_b.id:
        return ComparisonResult(
            relationship_type=RelationshipType.RELATED,
            confidence=1.0,
            reasoning="Same fact — no comparison needed.",
            context_factors=[],
        )

    # Step 1: Do they share an entity or predicate?
    if not _share_entity_or_predicate(fact_a, fact_b):
        return ComparisonResult(
            relationship_type=RelationshipType.RELATED,
            confidence=0.7,
            reasoning="Facts do not share a subject entity or a related predicate.",
            context_factors=[],
        )

    # Step 2: Temporal scope comparison
    ts_a = fact_a.temporal_scope
    ts_b = fact_b.temporal_scope
    if ts_a and ts_b:
        # Convert to TemporalScope-like dicts
        from app.normalization.temporal import TemporalScope
        tsa = TemporalScope(**ts_a)
        tsb = TemporalScope(**ts_b)
        if temporal_scopes_differ(tsa, tsb):
            context_factors.append("temporal_scope")
            return ComparisonResult(
                relationship_type=RelationshipType.TEMPORALLY_DISTINCT,
                confidence=0.92,
                reasoning=(
                    f"The two facts refer to different time periods: "
                    f"'{ts_a.get('label', ts_a.get('start', 'unknown'))}' vs "
                    f"'{ts_b.get('label', ts_b.get('start', 'unknown'))}'. "
                    "This is not a contradiction."
                ),
                context_factors=context_factors,
            )

    # Step 3: Geographic/population scope
    if _scope_differs(fact_a.geographic_scope, fact_b.geographic_scope):
        context_factors.append("geographic_scope")
        return ComparisonResult(
            relationship_type=RelationshipType.DISTINCT_SCOPE,
            confidence=0.88,
            reasoning=(
                f"Facts have different geographic scopes: "
                f"'{fact_a.geographic_scope}' vs '{fact_b.geographic_scope}'. "
                "Different scopes are not contradictions."
            ),
            context_factors=context_factors,
        )
    if _scope_differs(fact_a.population_scope, fact_b.population_scope):
        context_factors.append("population_scope")
        return ComparisonResult(
            relationship_type=RelationshipType.DISTINCT_SCOPE,
            confidence=0.85,
            reasoning=(
                f"Facts describe different populations: "
                f"'{fact_a.population_scope}' vs '{fact_b.population_scope}'."
            ),
            context_factors=context_factors,
        )

    # Step 4: Currency mismatch (never auto-convert)
    if fact_a.currency and fact_b.currency and fact_a.currency != fact_b.currency:
        context_factors.append("currency")
        return ComparisonResult(
            relationship_type=RelationshipType.UNIT_MISMATCH,
            confidence=0.90,
            reasoning=(
                f"Facts use different currencies: {fact_a.currency} vs {fact_b.currency}. "
                "No currency conversion is performed — cannot assert equivalence."
            ),
            context_factors=context_factors,
        )

    # Step 5: Unit compatibility
    if fact_a.unit and fact_b.unit:
        if not units_compatible(fact_a.normalized_unit or fact_a.unit, fact_b.normalized_unit or fact_b.unit):
            context_factors.append("unit")
            return ComparisonResult(
                relationship_type=RelationshipType.UNIT_MISMATCH,
                confidence=0.87,
                reasoning=(
                    f"Facts use incompatible units: '{fact_a.unit}' vs '{fact_b.unit}'. "
                    "Cannot safely compare values across unit systems."
                ),
                context_factors=context_factors,
            )

    # Step 6 & 7: Numeric comparison
    val_a = fact_a.normalized_value if fact_a.normalized_value is not None else fact_a.numeric_value
    val_b = fact_b.normalized_value if fact_b.normalized_value is not None else fact_b.numeric_value

    if val_a is not None and val_b is not None:
        val_a = float(val_a)
        val_b = float(val_b)
        delta = abs(val_a - val_b)
        tol = _tolerance(fact_a)

        if fact_a.object_type == ObjectType.PERCENTAGE:
            # Use absolute diff for percentage points
            rel = _absolute_diff(val_a, val_b)
        else:
            rel = _relative_diff(val_a, val_b)

        if rel <= tol:
            return ComparisonResult(
                relationship_type=RelationshipType.CORROBORATES,
                confidence=max(0.7, 0.95 - rel * 5),
                reasoning=(
                    f"Values are within tolerance ({rel:.1%} difference, threshold {tol:.0%}). "
                    f"Fact A: {val_a:,.2f}, Fact B: {val_b:,.2f}."
                ),
                context_factors=context_factors,
                numeric_delta=delta,
                numeric_delta_pct=rel * 100,
            )
        else:
            # Material disagreement
            return ComparisonResult(
                relationship_type=RelationshipType.CONTRADICTS,
                confidence=min(0.90, 0.60 + rel * 0.5),
                reasoning=(
                    f"Values materially disagree ({rel:.1%} difference, threshold {tol:.0%}). "
                    f"Fact A: {val_a:,.2f}, Fact B: {val_b:,.2f}."
                ),
                context_factors=context_factors,
                numeric_delta=delta,
                numeric_delta_pct=rel * 100,
            )

    # Step 8: No numeric values — text/semantic comparison
    # Cannot determine numerically; send to LLM for classification
    return ComparisonResult(
        relationship_type=RelationshipType.UNCERTAIN,
        confidence=0.5,
        reasoning=(
            "Cannot determine relationship deterministically: "
            "one or both facts lack numeric values for comparison. "
            "LLM classification recommended."
        ),
        context_factors=context_factors,
        deterministic=False,
    )
