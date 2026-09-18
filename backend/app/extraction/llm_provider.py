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
# Gemini Provider (LangChain)
# ---------------------------------------------------------------------------


class GeminiProvider:
    """Google Gemini via LangChain chains with structured Pydantic output."""

    def __init__(self) -> None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.prompts import ChatPromptTemplate

        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set. Set it in .env or environment.")

        self._model_name = "gemini-3.6-flash"
        self._llm = ChatGoogleGenerativeAI(
            model=self._model_name,
            temperature=0.1,
            google_api_key=settings.gemini_api_key,
            max_output_tokens=8192,
        )
        logger.info("gemini_provider_initialized", model=self._model_name, via="langchain")

    async def extract_facts(
        self, chunk_text: str, document_context: str = ""
    ) -> ExtractionResponse:
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import JsonOutputParser

        t0 = time.perf_counter()
        prompt = ChatPromptTemplate.from_messages([
            ("system", EXTRACTION_SYSTEM_PROMPT),
            ("human", (
                "Document context: {context}\n\n"
                "Text to extract from:\n---\n{text}\n---\n\n"
                "Return ONLY valid JSON with this exact structure:\n"
                '{{"facts": [{{"subject": "", "predicate": "", "object_text": "", '
                '"object_type": "NUMERIC|PERCENTAGE|MONETARY|COUNT|DATE|TEXT", '
                '"numeric_value": null, "unit": null, "currency": null, '
                '"temporal_scope": null, "geographic_scope": null, '
                '"population_scope": null, "methodology": null, "modality": null, '
                '"qualifiers": null, "confidence": 0.9, "uncertainty_reasons": [], '
                '"evidence_span": "exact quote from text"}}], '
                '"extraction_notes": ""}}'
            )),
        ])
        chain = prompt | self._llm | JsonOutputParser()
        try:
            raw = await chain.ainvoke({"context": document_context, "text": chunk_text})
            elapsed = time.perf_counter() - t0
            llm_request_duration_seconds.labels(
                provider="gemini", operation="extract_facts"
            ).observe(elapsed)
            if not isinstance(raw, dict) or "facts" not in raw:
                raw = {"facts": [], "extraction_notes": "Unexpected response shape"}
            return ExtractionResponse(**raw)
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            llm_request_duration_seconds.labels(
                provider="gemini", operation="extract_facts"
            ).observe(elapsed)
            logger.error("gemini_extract_facts_error", error=str(exc))
            return ExtractionResponse(facts=[], extraction_notes=f"Error: {exc}")

    async def classify_relationship(
        self,
        fact_a_text: str,
        fact_b_text: str,
        evidence_a: str,
        evidence_b: str,
        deterministic_hint: Optional[str] = None,
    ) -> RelationshipClassificationRaw:
        from langchain_core.prompts import ChatPromptTemplate

        t0 = time.perf_counter()
        hint_line = f"\nDeterministic pre-check: {deterministic_hint}" if deterministic_hint else ""
        prompt = ChatPromptTemplate.from_messages([
            ("system", RELATIONSHIP_SYSTEM_PROMPT),
            ("human", (
                "Fact A: {fact_a}\nEvidence A: {evidence_a}\n\n"
                "Fact B: {fact_b}\nEvidence B: {evidence_b}"
                "{hint}\n\n"
                "Return ONLY valid JSON:\n"
                '{{"relationship_type": "CORROBORATES|CONTRADICTS|APPARENT_CONTRADICTION|'
                'DISTINCT_SCOPE|TEMPORALLY_DISTINCT|UNIT_MISMATCH|UNCERTAIN", '
                '"confidence": 0.9, "reasoning": "step-by-step reasoning", '
                '"context_explanation": "plain language explanation", '
                '"context_factors": []}}'
            )),
        ])
        chain = prompt | self._llm.with_structured_output(RelationshipClassificationRaw)
        try:
            result = await chain.ainvoke({
                "fact_a": fact_a_text,
                "evidence_a": evidence_a,
                "fact_b": fact_b_text,
                "evidence_b": evidence_b,
                "hint": hint_line,
            })
            elapsed = time.perf_counter() - t0
            llm_request_duration_seconds.labels(
                provider="gemini", operation="classify_relationship"
            ).observe(elapsed)
            return result
        except Exception as exc:
            elapsed = time.perf_counter() - t0
            llm_request_duration_seconds.labels(
                provider="gemini", operation="classify_relationship"
            ).observe(elapsed)
            logger.error("gemini_classify_relationship_error", error=str(exc))
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
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        prompt = ChatPromptTemplate.from_messages([
            ("human", (
                "Explain in 2-3 sentences why the following two facts have the "
                "relationship '{rel_type}':\n\n"
                "Fact A: {fact_a}\nFact B: {fact_b}\n"
                "Context: {context}\n\n"
                "Be precise and reference specific contextual factors."
            )),
        ])
        llm_explain = self._llm.bind(temperature=0.2, max_output_tokens=512)
        chain = prompt | llm_explain | StrOutputParser()
        try:
            return await chain.ainvoke({
                "rel_type": relationship_type,
                "fact_a": fact_a_text,
                "fact_b": fact_b_text,
                "context": context,
            })
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
