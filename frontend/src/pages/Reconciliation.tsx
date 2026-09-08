import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { listRelationships, getRelationship } from '../api/client';
import type { Relationship } from '../types';

const REL_TAG: Record<string, string> = {
    CORROBORATES: 'tag-corroborates',
    CONTRADICTS: 'tag-contradicts',
    APPARENT_CONTRADICTION: 'tag-apparent',
    TEMPORALLY_DISTINCT: 'tag-temporal',
    DISTINCT_SCOPE: 'tag-scope',
    UNIT_MISMATCH: 'tag-uncertain',
    UNCERTAIN: 'tag-uncertain',
};

const REL_LABEL: Record<string, string> = {
    CORROBORATES: 'Corroborates',
    CONTRADICTS: 'Contradicts',
    APPARENT_CONTRADICTION: 'Apparent Contradiction',
    TEMPORALLY_DISTINCT: 'Temporally Distinct',
    DISTINCT_SCOPE: 'Distinct Scope',
    UNIT_MISMATCH: 'Unit Mismatch',
    UNCERTAIN: 'Uncertain',
};

function ConfBar({ v }: { v: number }) {
    const color = v >= 0.8 ? 'var(--green)' : v >= 0.5 ? 'var(--ink-3)' : 'var(--amber)';
    return (
        <div className="conf-strip">
            <div className="conf-bar"><div className="conf-bar-fill" style={{ width: `${v * 100}%`, background: color }} /></div>
            <span className="conf-val">{(v * 100).toFixed(0)}%</span>
        </div>
    );
}

function TracePanel({ rel }: { rel: Relationship }) {
    const trace = rel.reasoning_trace;
    const steps = [
        { label: 'Candidate Retrieval', value: trace?.step_1_candidates, key: '01' },
        { label: 'Semantic Similarity', value: trace?.step_2_semantic_similarity?.toFixed(3), key: '02' },
        { label: 'Entity Match', value: trace?.step_3_entity_match?.toString(), key: '03' },
        { label: 'Predicate Alignment', value: trace?.step_4_predicate_match?.toFixed(2), key: '04' },
        { label: 'Temporal Context', value: trace?.step_5_time_comparison, key: '05' },
        { label: 'Scope Comparison', value: trace?.step_6_scope_comparison, key: '06' },
        { label: 'Unit Comparison', value: trace?.step_7_unit_comparison, key: '07' },
        { label: 'Numeric Comparison', value: trace?.step_8_numeric_comparison, key: '08' },
        { label: 'Reconciliation Decision', value: trace?.step_9_final_relationship, key: '09' },
        { label: 'Confidence Score', value: trace?.step_10_confidence != null ? `${(trace.step_10_confidence * 100).toFixed(1)}%` : undefined, key: '10' },
    ].filter(s => s.value != null);

    if (!steps.length) return <div style={{ fontSize: '0.75rem', color: 'var(--ink-4)', padding: 'var(--s4)' }}>No trace available</div>;
    const verdict = trace?.step_9_final_relationship;
    return (
        <div className="trace">
            {steps.map((s, i) => (
                <div key={s.key} className={`trace-step${i === steps.length - 1 ? ' resolved' : ''}`}>
                    <div className="trace-step-num">{s.key}</div>
                    <div className="trace-step-body">
                        <div className="trace-step-label">{s.label}</div>
                        <div className="trace-step-value">{s.value}</div>
                        {s.label === 'Reconciliation Decision' && verdict && (
                            <div className="trace-step-verdict">
                                <span className={`tag ${REL_TAG[verdict] || 'tag-uncertain'}`}>{REL_LABEL[verdict] || verdict}</span>
                            </div>
                        )}
                    </div>
                </div>
            ))}
        </div>
    );
}

function FactCompare({ rel }: { rel: Relationship }) {
    if (!rel.fact_a || !rel.fact_b) return null;
    const a = rel.fact_a;
    const b = rel.fact_b;

    const rows: Array<[string, string | undefined, string | undefined]> = [
        ['predicate', a.predicate, b.predicate],
        ['value', a.object_text || undefined, b.object_text || undefined],
        ['period', a.temporal_scope?.label, b.temporal_scope?.label],
        ['scope', a.geographic_scope || undefined, b.geographic_scope || undefined],
        ['subject', a.subject_name || undefined, b.subject_name || undefined],
    ];

    return (
        <div>
            {rows.filter(([, av, bv]) => av || bv).map(([label, av, bv]) => {
                const same = av === bv;
                return (
                    <div key={label} className="diff-row">
                        <div className="diff-label">{label}</div>
                        <div className="diff-a">{av || '—'}</div>
                        <div className="diff-arrow">→</div>
                        <div className={`diff-b ${same ? 'same' : 'changed'}`}>{bv || '—'}</div>
                    </div>
                );
            })}
            {rel.numeric_delta_pct != null && (
                <div className="diff-row">
                    <div className="diff-label">delta</div>
                    <div className="diff-a" />
                    <div className="diff-arrow" />
                    <div className="diff-delta">{rel.numeric_delta_pct > 0 ? '+' : ''}{rel.numeric_delta_pct.toFixed(2)}%</div>
                </div>
            )}
        </div>
    );
}

export default function Reconciliation() {
    const [searchParams] = useSearchParams();
    const highlightId = searchParams.get('rel');
    const typeParam = searchParams.get('type') || '';

    const [rels, setRels] = useState<Relationship[]>([]);
    const [total, setTotal] = useState(0);
    const [filterType, setFilterType] = useState(typeParam);
    const [selected, setSelected] = useState<Relationship | null>(null);
    const [page, setPage] = useState(0);
    const [tab, setTab] = useState<'compare' | 'trace'>('compare');
    const limit = 40;

    const load = () =>
        listRelationships({ skip: page * limit, limit, type: filterType || undefined }).then(r => {
            setRels(r.data.items);
            setTotal(r.data.total);
        });

    useEffect(() => { load(); }, [page, filterType]);

    useEffect(() => {
        if (highlightId) {
            getRelationship(highlightId).then(r => setSelected(r.data)).catch(() => { });
        }
    }, [highlightId]);

    return (
        <div className="page" style={{ height: 'calc(100vh - 44px)', display: 'flex', flexDirection: 'column' }}>
            {/* Header */}
            <div style={{ padding: 'var(--s5) var(--s6)', borderBottom: '1px solid var(--rule)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 'var(--s4)' }}>
                    <div>
                        <h1 className="page-heading">Reconciliation</h1>
                        <p className="page-subheading">{total.toLocaleString()} cross-document relationships · deterministic engine + optional LLM refinement</p>
                    </div>
                </div>
                <div style={{ display: 'flex', gap: 'var(--s3)', alignItems: 'center' }}>
                    <select value={filterType} onChange={e => { setFilterType(e.target.value); setPage(0); }} style={{ maxWidth: 200 }}>
                        <option value="">All types</option>
                        <option value="CORROBORATES">Corroborates</option>
                        <option value="CONTRADICTS">Contradicts</option>
                        <option value="APPARENT_CONTRADICTION">Apparent Contradiction</option>
                        <option value="TEMPORALLY_DISTINCT">Temporally Distinct</option>
                        <option value="DISTINCT_SCOPE">Distinct Scope</option>
                        <option value="UNIT_MISMATCH">Unit Mismatch</option>
                        <option value="UNCERTAIN">Uncertain</option>
                    </select>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--ink-4)', marginLeft: 'auto' }}>
                        {page * limit + 1}–{Math.min((page + 1) * limit, total)} of {total.toLocaleString()}
                    </span>
                </div>
            </div>

            {/* Content */}
            <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
                {/* Table */}
                <div style={{ flex: 1, overflow: 'auto' }}>
                    <table className="data-table">
                        <thead>
                            <tr>
                                <th style={{ width: 220 }}>Claim A</th>
                                <th style={{ width: 220 }}>Claim B</th>
                                <th style={{ width: 140 }}>Relationship</th>
                                <th style={{ width: 80 }}>Delta</th>
                                <th style={{ width: 90 }}>Confidence</th>
                                <th style={{ width: 60 }}>Method</th>
                            </tr>
                        </thead>
                        <tbody>
                            {rels.map(r => (
                                <tr key={r.id}
                                    className={selected?.id === r.id ? 'selected' : ''}
                                    onClick={() => setSelected(r === selected ? null : r)}>
                                    <td style={{ maxWidth: 220 }}>
                                        <div className="truncate" style={{ fontSize: '0.78rem', color: 'var(--ink-2)' }}>
                                            {r.fact_a ? r.fact_a.predicate : r.fact_a_id.slice(0, 10)}
                                        </div>
                                        {r.fact_a?.object_text && (
                                            <div className="truncate" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--ink)', fontWeight: 600, marginTop: 1 }}>
                                                {r.fact_a.object_text}
                                            </div>
                                        )}
                                        {r.fact_a?.temporal_scope?.label && (
                                            <div style={{ fontSize: '0.65rem', color: 'var(--ink-4)', marginTop: 1 }}>{r.fact_a.temporal_scope.label}</div>
                                        )}
                                    </td>
                                    <td style={{ maxWidth: 220 }}>
                                        <div className="truncate" style={{ fontSize: '0.78rem', color: 'var(--ink-2)' }}>
                                            {r.fact_b ? r.fact_b.predicate : r.fact_b_id.slice(0, 10)}
                                        </div>
                                        {r.fact_b?.object_text && (
                                            <div className="truncate" style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--ink)', fontWeight: 600, marginTop: 1 }}>
                                                {r.fact_b.object_text}
                                            </div>
                                        )}
                                        {r.fact_b?.temporal_scope?.label && (
                                            <div style={{ fontSize: '0.65rem', color: 'var(--ink-4)', marginTop: 1 }}>{r.fact_b.temporal_scope.label}</div>
                                        )}
                                    </td>
                                    <td>
                                        <span className={`tag ${REL_TAG[r.relationship_type] || 'tag-uncertain'}`}>
                                            {REL_LABEL[r.relationship_type] || r.relationship_type.replace(/_/g, ' ')}
                                        </span>
                                    </td>
                                    <td className="cell-mono" style={{ fontSize: '0.75rem', color: 'var(--amber)' }}>
                                        {r.numeric_delta_pct != null ? `${r.numeric_delta_pct > 0 ? '+' : ''}${r.numeric_delta_pct.toFixed(1)}%` : '—'}
                                    </td>
                                    <td><ConfBar v={r.confidence} /></td>
                                    <td style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', color: 'var(--ink-4)' }}>
                                        {r.llm_assisted ? 'LLM' : 'det.'}
                                    </td>
                                </tr>
                            ))}
                            {rels.length === 0 && (
                                <tr><td colSpan={6}>
                                    <div className="empty-state">
                                        <div className="empty-state-title">No reconciliations</div>
                                        <div className="empty-state-body">Process at least two documents to generate cross-document relationships.</div>
                                    </div>
                                </td></tr>
                            )}
                        </tbody>
                    </table>
                </div>

                {/* Detail Panel */}
                {selected && (
                    <div className="detail-panel">
                        <div className="detail-panel-header">
                            <div>
                                <div className="detail-panel-title">
                                    <span className={`tag ${REL_TAG[selected.relationship_type] || 'tag-uncertain'}`}>
                                        {REL_LABEL[selected.relationship_type] || selected.relationship_type}
                                    </span>
                                </div>
                                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--ink-4)', marginTop: 4 }}>
                                    {selected.llm_assisted ? 'LLM-assisted' : 'Deterministic'} · conf {(selected.confidence * 100).toFixed(0)}%
                                </div>
                            </div>
                            <button className="detail-panel-close" onClick={() => setSelected(null)}>✕</button>
                        </div>

                        {/* Tab bar */}
                        <div style={{ display: 'flex', borderBottom: '1px solid var(--rule)' }}>
                            {(['compare', 'trace'] as const).map(t => (
                                <button key={t} onClick={() => setTab(t)} style={{
                                    flex: 1, padding: 'var(--s3) var(--s4)',
                                    background: 'none', border: 'none', cursor: 'pointer',
                                    fontSize: '0.7rem', fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase',
                                    color: tab === t ? 'var(--ink)' : 'var(--ink-4)',
                                    borderBottom: tab === t ? '2px solid var(--accent)' : '2px solid transparent',
                                    fontFamily: 'var(--font-sans)',
                                }}>
                                    {t === 'compare' ? 'Comparison' : 'Reasoning Trace'}
                                </button>
                            ))}
                        </div>

                        {tab === 'compare' && (
                            <div className="detail-section">
                                <FactCompare rel={selected} />
                                {selected.reasoning && (
                                    <div style={{ marginTop: 'var(--s4)', paddingTop: 'var(--s3)', borderTop: '1px solid var(--rule)' }}>
                                        <div className="detail-section-label">Reasoning</div>
                                        <div style={{ fontSize: '0.78rem', color: 'var(--ink-2)', lineHeight: 1.65 }}>{selected.reasoning}</div>
                                    </div>
                                )}
                                {selected.context_factors?.length > 0 && (
                                    <div style={{ marginTop: 'var(--s3)' }}>
                                        <div className="detail-section-label">Context Factors</div>
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 'var(--s2)' }}>
                                            {selected.context_factors.map((cf, i) => (
                                                <span key={i} className="tag tag-temporal">{cf}</span>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        )}

                        {tab === 'trace' && (
                            <div className="detail-section">
                                <TracePanel rel={selected} />
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Pagination */}
            <div style={{ borderTop: '1px solid var(--rule)', padding: 'var(--s3) var(--s6)', display: 'flex', gap: 'var(--s3)' }}>
                <button className="btn btn-ghost" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Previous</button>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--ink-4)', alignSelf: 'center' }}>
                    Page {page + 1} / {Math.max(1, Math.ceil(total / limit))}
                </span>
                <button className="btn btn-ghost" disabled={(page + 1) * limit >= total} onClick={() => setPage(p => p + 1)}>Next →</button>
            </div>
        </div>
    );
}
