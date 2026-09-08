"""
LLM Provider abstraction for FactLens.

Defines a Protocol-based interface so the extraction and reconciliation
pipeline is fully decoupled from the underlying LLM API.

Providers:
  - GeminiProvider  (default)
  - OpenAIProvider
  - MockProvider    (schema-valid fixtures for tests)

A local/open-weight model can be added by implementing the LLMProvider protocol.
"""
from __future__ import annotations

import json
import time
from typing import Any, Optional, Protocol, Union, runtime_checkable

from pydantic import BaseModel, Field, field_validator

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.metrics import llm_request_duration_seconds

logger = get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Output schemas used for structured extraction
# ---------------------------------------------------------------------------


class ExtractedFactRaw(BaseModel):
    """Raw structured output from LLM fact extraction."""
    subject: str = Field(..., description="The entity or subject this fact is about")
    predicate: str = Field(..., description="The attribute, metric, or relationship being stated")
    object_text: str = Field(..., description="The raw value or claim as stated in the text")
    object_type: str = Field(
        ...,
        description="One of: NUMERIC, PERCENTAGE, MONETARY, COUNT, RATIO, DATE, TEXT, BOOLEAN, RANGE",
    )
    numeric_value: Optional[float] = Field(None, description="Parsed numeric value if applicable")
    unit: Optional[str] = Field(None, description="Unit of measurement (e.g. USD, %, km, employees)")
    currency: Optional[str] = Field(None, description="Currency code if monetary (e.g. INR, USD)")
    temporal_scope: Optional[str] = Field(
        None,
        description="Time period (e.g. 'FY2024', 'Q4 FY24', '2024-25', 'as of March 2025')",
    )
    geographic_scope: Optional[str] = Field(None, description="Geographic scope (e.g. India, Global, North America)")
    population_scope: Optional[str] = Field(None, description="Population described (e.g. 'direct employees', 'MSME customers')")
    methodology: Optional[str] = Field(None, description="Methodology note if any (e.g. 'CAGR', 'audited', 'estimated')")
    modality: Optional[str] = Field(
        None,
        description="One of: stated, estimated, approximately, projected, audited, unaudited, reported",
    )
    qualifiers: Optional[Any] = Field(None, description="Any other qualifiers as key-value pairs")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence 0-1")
    uncertainty_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons confidence is below 1.0",
    )
    evidence_span: str = Field(
        ...,
        description="The exact sentence or phrase from the input text that supports this fact",
    )

    @field_validator("qualifiers", mode="before")
    @classmethod
    def coerce_qualifiers(cls, v: Any) -> Any:
        """Accept dict or None; coerce strings/lists/other types to None."""
        if v is None or isinstance(v, dict):
            return v
        return None

    @field_validator("uncertainty_reasons", mode="before")
    @classmethod
    def coerce_uncertainty_reasons(cls, v: Any) -> Any:
        """Ensure this is always a list."""
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, list):
            return v
        return []


class ExtractionResponse(BaseModel):
    facts: list[ExtractedFactRaw]
    extraction_notes: str = ""


class RelationshipClassificationRaw(BaseModel):
    relationship_type: str = Field(
        ...,
        description=(
            "One of: CORROBORATES, CONTRADICTS, APPARENT_CONTRADICTION, DISTINCT_SCOPE, "
            "TEMPORALLY_DISTINCT, UNIT_MISMATCH, DEFINITION_MISMATCH, "
            "METHODOLOGY_DIFFERENCE, RELATED, UNCERTAIN"
        ),
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., description="Step-by-step reasoning for this classification")
    context_explanation: str = Field(
        ...,
        description="Plain-language explanation of context factors that affect interpretation",
    )
    context_factors: list[str] = Field(
        default_factory=list,
        description="e.g. ['temporal_scope', 'geographic_scope', 'definition']",
    )


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMProvider(Protocol):
    """
    Protocol for LLM-backed operations.
    Any class implementing these three async methods is a valid provider.
    """

    async def extract_facts(
        self, chunk_text: str, document_context: str = ""
    ) -> ExtractionResponse:
        """Extract structured facts from a text chunk."""
        ...

    async def classify_relationship(
        self,
        fact_a_text: str,
        fact_b_text: str,
        evidence_a: str,
        evidence_b: str,
        deterministic_hint: Optional[str] = None,
    ) -> RelationshipClassificationRaw:
        """Classify the relationship between two facts."""
        ...

    async def explain_relationship(
        self,
        fact_a_text: str,
        fact_b_text: str,
        relationship_type: str,
        context: str = "",
    ) -> str:
        """Generate a natural-language explanation of a relationship."""
        ...


# ---------------------------------------------------------------------------
# Extraction prompt builder
# ---------------------------------------------------------------------------

EXTRACTION_SYSTEM_PROMPT = """\
You are a precise information extraction engine. Your task is to extract atomic factual claims from the provided document text.

Rules:
1. Use ONLY the supplied text. Do NOT invent facts or use external knowledge.
2. Extract only meaningful, specific facts — not generic statements.
3. Every fact must have a verbatim evidence_span from the input text.
4. If you are not confident about a numeric value, set confidence < 0.6 and list uncertainty_reasons.
5. Return ONLY facts that are clearly grounded in the text.
6. Capture temporal, geographic, and population scope whenever stated.
7. Do NOT extract the same fact twice.
8. If a sentence is ambiguous or unparseable, skip it rather than guess.
"""

RELATIONSHIP_SYSTEM_PROMPT = """\
You are an expert at analyzing whether two factual claims agree, disagree, or differ for contextual reasons.

Instructions:
1. Use ONLY the supplied facts and their evidence texts.
2. Consider: time period, geographic scope, population scope, unit, currency, methodology, and definition.
3. Do NOT treat facts from different time periods as contradictions — classify as TEMPORALLY_DISTINCT.
4. Do NOT treat facts about different scopes as contradictions — classify as DISTINCT_SCOPE.
5. Classify as CONTRADICTS only if both facts refer to the same proposition, same time, same scope, and the values materially disagree.
6. Express uncertainty via UNCERTAIN rather than forcing a wrong classification.
7. Be precise and traceable in your reasoning.
"""


# ---------------------------------------------------------------------------
# Gemini Provider
# ---------------------------------------------------------------------------


class GeminiProvider:
    """Google Gemini with structured JSON output via response_schema."""

    def __init__(self) -> None:
        import google.generativeai as genai  # type: ignore

        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set. Set it in .env or environment.")
        genai.configure(api_key=settings.gemini_api_key)
        self._genai = genai
        self._model_name = "gemini-3.6-flash"
        logger.info("gemini_provider_initialized", model=self._model_name)

    def _make_model(self, temperature: float = 0.1) -> Any:
        return self._genai.GenerativeModel(
            model_name=self._model_name,
            generation_config=self._genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=temperature,
                max_output_tokens=8192,
            ),
        )

    async def extract_facts(
        self, chunk_text: str, document_context: str = ""
    ) -> ExtractionResponse:
        import asyncio

        t0 = time.perf_counter()
        prompt = (
            f"{EXTRACTION_SYSTEM_PROMPT}\n\n"
            f"Document context: {document_context}\n\n"
            f"Text to extract from:\n---\n{chunk_text}\n---\n\n"
            "Return ONLY valid JSON with this exact structure:\n"
            '{"facts": [{"subject": "", "predicate": "", "object_text": "", '
            '"object_type": "NUMERIC|PERCENTAGE|MONETARY|COUNT|DATE|TEXT", '
            '"numeric_value": null, "unit": null, "currency": null, '
            '"temporal_scope": null, "geographic_scope": null, '
            '"population_scope": null, "methodology": null, "modality": null, '
            '"qualifiers": null, "confidence": 0.9, "uncertainty_reasons": [], '
            '"evidence_span": "exact quote from text"}], '
            '"extraction_notes": ""}'
        )
        try:
            model = self._make_model(temperature=0.1)
            response = await asyncio.to_thread(model.generate_content, prompt)
            elapsed = time.perf_counter() - t0
            llm_request_duration_seconds.labels(
                provider="gemini", operation="extract_facts"
            ).observe(elapsed)
            text = response.text.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            raw = json.loads(text)
            if "facts" not in raw:
                raw = {"facts": [], "extraction_notes": "No facts key in response"}
            return ExtractionResponse(**raw)
        except Exception as exc:
            logger.error("gemini_extract_facts_error", error=str(exc))
            elapsed = time.perf_counter() - t0
            llm_request_duration_seconds.labels(
                provider="gemini", operation="extract_facts"
            ).observe(elapsed)
            return ExtractionResponse(facts=[], extraction_notes=f"Error: {exc}")

    async def classify_relationship(
        self,
        fact_a_text: str,
        fact_b_text: str,
        evidence_a: str,
        evidence_b: str,
        deterministic_hint: Optional[str] = None,
    ) -> RelationshipClassificationRaw:
        import asyncio

        t0 = time.perf_counter()
        hint_str = f"\nDeterministic pre-check result: {deterministic_hint}" if deterministic_hint else ""
        prompt = (
            f"{RELATIONSHIP_SYSTEM_PROMPT}\n\n"
            f"Fact A: {fact_a_text}\nEvidence A: {evidence_a}\n\n"
            f"Fact B: {fact_b_text}\nEvidence B: {evidence_b}\n{hint_str}\n\n"
            "Return ONLY valid JSON with this exact structure:\n"
            '{"relationship_type": "CORROBORATES|CONTRADICTS|APPARENT_CONTRADICTION|'
            'DISTINCT_SCOPE|TEMPORALLY_DISTINCT|UNIT_MISMATCH|UNCERTAIN", '
            '"confidence": 0.9, "reasoning": "step-by-step reasoning", '
            '"context_explanation": "plain language explanation", '
            '"context_factors": []}'
        )
        try:
            model = self._make_model(temperature=0.1)
            response = await asyncio.to_thread(model.generate_content, prompt)
            elapsed = time.perf_counter() - t0
            llm_request_duration_seconds.labels(
                provider="gemini", operation="classify_relationship"
            ).observe(elapsed)
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
            raw = json.loads(text)
            return RelationshipClassificationRaw(**raw)
        except Exception as exc:
            logger.error("gemini_classify_relationship_error", error=str(exc))
            elapsed = time.perf_counter() - t0
            llm_request_duration_seconds.labels(
                provider="gemini", operation="classify_relationship"
            ).observe(elapsed)
            return RelationshipClassificationRaw(
                relationship_type="UNCERTAIN",
                confidence=0.3,
                reasoning=f"LLM error: {exc}",
                context_explanation="Could not classify due to LLM error.",
                context_factors=[],
            )

    async def explain_relationship(
        self,
        fact_a_text: str,
        fact_b_text: str,
        relationship_type: str,
        context: str = "",
    ) -> str:
        import asyncio

        prompt = (
            f"Explain in 2-3 sentences why the following two facts have the "
            f"relationship '{relationship_type}':\n\n"
            f"Fact A: {fact_a_text}\nFact B: {fact_b_text}\n"
            f"Context: {context}\n\n"
            "Be precise and reference specific contextual factors."
        )
        try:
            model = self._genai.GenerativeModel(
                model_name=self._model_name,
                generation_config=self._genai.GenerationConfig(temperature=0.2, max_output_tokens=512),
            )
            response = await asyncio.to_thread(model.generate_content, prompt)
            return response.text.strip()
        except Exception as exc:
            logger.error("gemini_explain_error", error=str(exc))
            return f"Explanation unavailable ({exc})"


# ---------------------------------------------------------------------------
# OpenAI Provider
# ---------------------------------------------------------------------------


class OpenAIProvider:
    """OpenAI with JSON mode for structured extraction."""

    def __init__(self) -> None:
        from openai import AsyncOpenAI  # type: ignore

        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set.")
        self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        self._model = "gpt-4o-mini"
        logger.info("openai_provider_initialized", model=self._model)

    async def extract_facts(
        self, chunk_text: str, document_context: str = ""
    ) -> ExtractionResponse:
        t0 = time.perf_counter()
        prompt = (
            f"{EXTRACTION_SYSTEM_PROMPT}\n\nDocument context: {document_context}\n\n"
            f"Text:\n---\n{chunk_text}\n---"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            elapsed = time.perf_counter() - t0
            llm_request_duration_seconds.labels(
                provider="openai", operation="extract_facts"
            ).observe(elapsed)
            raw = json.loads(response.choices[0].message.content or "{}")
            if "facts" not in raw:
                raw = {"facts": [], "extraction_notes": "No facts key in response"}
            return ExtractionResponse(**raw)
        except Exception as exc:
            logger.error("openai_extract_facts_error", error=str(exc))
            return ExtractionResponse(facts=[], extraction_notes=f"Error: {exc}")

    async def classify_relationship(
        self,
        fact_a_text: str,
        fact_b_text: str,
        evidence_a: str,
        evidence_b: str,
        deterministic_hint: Optional[str] = None,
    ) -> RelationshipClassificationRaw:
        hint_str = f"\nDeterministic hint: {deterministic_hint}" if deterministic_hint else ""
        prompt = (
            f"{RELATIONSHIP_SYSTEM_PROMPT}\n\n"
            f"Fact A: {fact_a_text}\nEvidence A: {evidence_a}\n\n"
            f"Fact B: {fact_b_text}\nEvidence B: {evidence_b}{hint_str}"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            raw = json.loads(response.choices[0].message.content or "{}")
            return RelationshipClassificationRaw(**raw)
        except Exception as exc:
            logger.error("openai_classify_error", error=str(exc))
            return RelationshipClassificationRaw(
                relationship_type="UNCERTAIN",
                confidence=0.3,
                reasoning=f"LLM error: {exc}",
                context_explanation="Could not classify.",
                context_factors=[],
            )

    async def explain_relationship(
        self, fact_a_text: str, fact_b_text: str, relationship_type: str, context: str = ""
    ) -> str:
        prompt = (
            f"Explain (2-3 sentences) why Fact A and Fact B have relationship '{relationship_type}':\n"
            f"Fact A: {fact_a_text}\nFact B: {fact_b_text}\nContext: {context}"
        )
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=256,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:
            return f"Explanation unavailable ({exc})"


# ---------------------------------------------------------------------------
# Mock Provider (for tests — no API keys needed)
# ---------------------------------------------------------------------------


class MockProvider:
    """
    Schema-valid mock LLM provider for unit/integration tests.
    Returns empty/generic fixtures. Does NOT contain any starter-document facts.
    """

    async def extract_facts(
        self, chunk_text: str, document_context: str = ""
    ) -> ExtractionResponse:
        # Return one generic fact to exercise the pipeline schema
        if len(chunk_text.strip()) < 20:
            return ExtractionResponse(facts=[], extraction_notes="Mock: chunk too short")
        return ExtractionResponse(
            facts=[
                ExtractedFactRaw(
                    subject="Test Entity",
                    predicate="test_metric",
                    object_text="100 units",
                    object_type="NUMERIC",
                    numeric_value=100.0,
                    unit="units",
                    confidence=0.9,
                    uncertainty_reasons=[],
                    evidence_span=chunk_text[:120].strip(),
                )
            ],
            extraction_notes="Mock extraction",
        )

    async def classify_relationship(
        self,
        fact_a_text: str,
        fact_b_text: str,
        evidence_a: str,
        evidence_b: str,
        deterministic_hint: Optional[str] = None,
    ) -> RelationshipClassificationRaw:
        return RelationshipClassificationRaw(
            relationship_type=deterministic_hint or "UNCERTAIN",
            confidence=0.7,
            reasoning="Mock classification",
            context_explanation="Mock explanation",
            context_factors=[],
        )

    async def explain_relationship(
        self, fact_a_text: str, fact_b_text: str, relationship_type: str, context: str = ""
    ) -> str:
        return f"[Mock] Relationship '{relationship_type}' between the two facts."


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_llm_provider() -> LLMProvider:
    """Instantiate the configured LLM provider."""
    provider_name = settings.llm_provider.lower()
    if provider_name == "gemini":
        return GeminiProvider()
    elif provider_name == "openai":
        return OpenAIProvider()
    elif provider_name == "mock":
        return MockProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name!r}. Choose gemini|openai|mock.")
