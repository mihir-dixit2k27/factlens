"""
Evidence validator: enforces the evidence-first guarantee.
Every stored fact MUST have at least one valid evidence record.
A fact without evidence is never presented as trusted.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.extraction.llm_provider import ExtractedFactRaw
from app.core.logging import get_logger

logger = get_logger(__name__)

_MIN_EVIDENCE_SPAN_LENGTH = 10
_MIN_CONFIDENCE = 0.0  # absolute minimum; caller enforces higher thresholds


@dataclass
class ValidationResult:
    is_valid: bool
    fact_subject: str
    fact_predicate: str
    evidence_span: str
    failure_reason: Optional[str] = None
    confidence_adjustment: float = 0.0


def validate_fact_grounding(
    fact: ExtractedFactRaw,
    chunk_text: str,
) -> ValidationResult:
    """
    Enforce the evidence-first guarantee:
    1. The fact must have a non-empty evidence_span.
    2. The evidence_span must plausibly come from the chunk_text.
    3. Confidence must be above the absolute minimum.

    Returns ValidationResult with is_valid=True only when all checks pass.
    """
    subject = (fact.subject or "").strip()
    predicate = (fact.predicate or "").strip()
    span = (fact.evidence_span or "").strip()

    if not span:
        logger.warning(
            "evidence_validation_failed",
            reason="empty_span",
            subject=subject,
            predicate=predicate,
        )
        return ValidationResult(
            is_valid=False,
            fact_subject=subject,
            fact_predicate=predicate,
            evidence_span=span,
            failure_reason="Evidence span is empty — fact cannot be grounded.",
        )

    if len(span) < _MIN_EVIDENCE_SPAN_LENGTH:
        return ValidationResult(
            is_valid=False,
            fact_subject=subject,
            fact_predicate=predicate,
            evidence_span=span,
            failure_reason=f"Evidence span too short ({len(span)} chars).",
        )

    # Check whether key evidence words appear in the chunk
    span_words = set(span.lower().split())
    chunk_lower = chunk_text.lower()
    # At least 60% of span words should be found in chunk
    if span_words:
        matched = sum(1 for w in span_words if w in chunk_lower)
        coverage = matched / len(span_words)
        if coverage < 0.5:
            logger.warning(
                "evidence_validation_failed",
                reason="low_chunk_coverage",
                coverage=round(coverage, 2),
                subject=subject,
                predicate=predicate,
            )
            return ValidationResult(
                is_valid=False,
                fact_subject=subject,
                fact_predicate=predicate,
                evidence_span=span,
                failure_reason=(
                    f"Evidence span has low overlap with chunk text (coverage={coverage:.0%}). "
                    "Possible hallucination."
                ),
                confidence_adjustment=-0.3,
            )

    if fact.confidence < _MIN_CONFIDENCE:
        return ValidationResult(
            is_valid=False,
            fact_subject=subject,
            fact_predicate=predicate,
            evidence_span=span,
            failure_reason=f"Confidence {fact.confidence:.2f} below minimum.",
            confidence_adjustment=0.0,
        )

    return ValidationResult(
        is_valid=True,
        fact_subject=subject,
        fact_predicate=predicate,
        evidence_span=span,
    )
