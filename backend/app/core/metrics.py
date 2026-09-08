"""Prometheus metrics registry for FactLens."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

# Counters
documents_processed_total = Counter(
    "factlens_documents_processed_total",
    "Total documents successfully processed",
    ["status"],
)
pages_processed_total = Counter(
    "factlens_pages_processed_total",
    "Total PDF pages processed",
)
facts_extracted_total = Counter(
    "factlens_facts_extracted_total",
    "Total facts extracted from documents",
    ["status"],
)
facts_linked_total = Counter(
    "factlens_facts_linked_total",
    "Total fact pairs linked for comparison",
)
contradictions_detected_total = Counter(
    "factlens_contradictions_detected_total",
    "Total genuine contradictions detected",
)
relationships_created_total = Counter(
    "factlens_relationships_created_total",
    "Total relationships created",
    ["relationship_type"],
)

# Histograms
processing_duration_seconds = Histogram(
    "factlens_processing_duration_seconds",
    "Processing duration per stage",
    ["stage"],
    buckets=(0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)
llm_request_duration_seconds = Histogram(
    "factlens_llm_request_duration_seconds",
    "LLM API request duration",
    ["provider", "operation"],
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
)
embedding_duration_seconds = Histogram(
    "factlens_embedding_duration_seconds",
    "Embedding generation duration",
    ["batch_size"],
    buckets=(0.05, 0.1, 0.5, 1.0, 5.0, 10.0),
)

# Gauges
documents_total = Gauge("factlens_documents_total", "Total documents in system")
facts_total = Gauge("factlens_facts_total", "Total facts in knowledge layer")
grounded_facts_total = Gauge(
    "factlens_grounded_facts_total", "Facts with valid evidence grounding"
)
