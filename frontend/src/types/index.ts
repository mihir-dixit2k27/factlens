// TypeScript types for FactLens API responses

export interface Document {
    id: string;
    filename: string;
    filepath: string;
    file_size_bytes: number;
    page_count: number | null;
    dataset: string | null;
    title: string | null;
    processing_stage: string;
    processing_error: string | null;
    created_at: string;
    updated_at: string;
}

export interface Evidence {
    id: string;
    document_id: string;
    page_number: number;
    block_id: string | null;
    chunk_id: string | null;
    exact_text: string;
    bbox: number[] | null;
    extraction_method: string;
    extraction_confidence: number;
}

export interface TemporalScope {
    type: string;
    start?: string;
    end?: string;
    label?: string;
    fiscal_year?: number;
    quarter?: number;
}

export interface Fact {
    id: string;
    subject_entity_id: string | null;
    subject_name: string | null;
    predicate: string;
    object_type: string;
    object_text: string;
    numeric_value: number | null;
    normalized_value: number | null;
    unit: string | null;
    normalized_unit: string | null;
    currency: string | null;
    temporal_scope: TemporalScope | null;
    geographic_scope: string | null;
    population_scope: string | null;
    methodology: string | null;
    qualifiers: Record<string, unknown> | null;
    modality: string | null;
    confidence: number;
    extraction_status: string;
    uncertainty_reasons: string[];
    primary_document_id: string | null;
    evidence_count: number;
    relationship_count: number;
    created_at: string;
}

export interface ReasoningTrace {
    step_1_candidates?: string;
    step_2_semantic_similarity?: number;
    step_3_entity_match?: boolean;
    step_4_predicate_match?: number;
    step_5_time_comparison?: string;
    step_6_scope_comparison?: string;
    step_7_unit_comparison?: string;
    step_8_numeric_comparison?: string;
    step_9_final_relationship?: string;
    step_10_confidence?: number;
}

export interface Relationship {
    id: string;
    fact_a_id: string;
    fact_b_id: string;
    fact_a?: Fact;
    fact_b?: Fact;
    relationship_type: string;
    confidence: number;
    reasoning: string | null;
    context_explanation: string | null;
    context_factors: string[];
    reasoning_trace: ReasoningTrace | null;
    numeric_delta: number | null;
    numeric_delta_pct: number | null;
    llm_assisted: boolean;
    created_at: string;
}

export interface ProcessingRun {
    id: string;
    document_id: string;
    stage: string;
    status: string;
    pages_processed: number;
    chunks_created: number;
    facts_created: number;
    embeddings_created: number;
    relationships_created: number;
    processing_time_seconds: number | null;
    error_message: string | null;
    started_at: string;
    completed_at: string | null;
}

export interface RequiredCase {
    case_number: number;
    label: string;
    title: string;
    description: string;
    relationship_id: string | null;
    fact_a_id: string | null;
    fact_b_id: string | null;
    failure_detail: Record<string, unknown> | null;
    // Enriched fields populated by /api/cases
    case_type?: string;
    fact_a?: Partial<Fact>;
    fact_b?: Partial<Fact>;
    reasoning?: string;
}

export interface SystemMetrics {
    documents_total: number;
    pages_total: number;
    facts_total: number;
    grounded_facts_total: number;
    facts_trusted: number;
    facts_probable: number;
    facts_uncertain: number;
    facts_failed: number;
    relationships_total: number;
    corroborations: number;
    contradictions: number;
    apparent_contradictions: number;
    distinct_scope: number;
    temporally_distinct: number;
    uncertain_relationships: number;
    fact_grounding_rate: number;
    extraction_failure_rate: number;
    average_confidence: number;
    generated_at: string;
}
