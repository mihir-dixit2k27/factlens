import { useEffect, useState } from 'react';
import { getHealth, getMetrics } from '../api/client';
import type { SystemMetrics } from '../types';

interface HealthData {
    status: string;
    database: string;
    llm_provider: string;
    embedding_model: string;
    version?: string;
}

function StatusDot({ ok }: { ok: boolean }) {
    return (
        <span style={{ display: 'inline-block', width: 7, height: 7, borderRadius: '50%', background: ok ? 'var(--green)' : 'var(--red)', marginRight: 6 }} />
    );
}

const METRIC_ROWS: Array<[string, (m: SystemMetrics) => string | number]> = [
    ['Documents total', m => m.documents_total],
    ['Pages processed', m => m.pages_total.toLocaleString()],
    ['Facts extracted', m => m.facts_total.toLocaleString()],
    ['Facts grounded', m => m.grounded_facts_total.toLocaleString()],
    ['Grounding rate', m => `${(m.fact_grounding_rate * 100).toFixed(1)}%`],
    ['Average confidence', m => `${(m.average_confidence * 100).toFixed(1)}%`],
    ['Relationships total', m => m.relationships_total.toLocaleString()],
    ['— Corroborations', m => m.corroborations.toLocaleString()],
    ['— Contradictions', m => m.contradictions.toLocaleString()],
    ['— Apparent contradict.', m => m.apparent_contradictions.toLocaleString()],
    ['— Temporally distinct', m => m.temporally_distinct.toLocaleString()],
    ['— Scope distinct', m => m.distinct_scope.toLocaleString()],
    ['Trusted facts', m => m.facts_trusted.toLocaleString()],
    ['Uncertain facts', m => m.facts_uncertain.toLocaleString()],
    ['Failed extractions', m => m.facts_failed.toLocaleString()],
];

export default function Health() {
    const [health, setHealth] = useState<HealthData | null>(null);
    const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
    const [loading, setLoading] = useState(true);
    const [ts, setTs] = useState('');

    const load = () => {
        setLoading(true);
        Promise.all([getHealth(), getMetrics()])
            .then(([h, m]) => { setHealth(h.data); setMetrics(m.data); setTs(new Date().toLocaleTimeString()); })
            .catch(() => { })
            .finally(() => setLoading(false));
    };

    useEffect(() => { load(); }, []);

    return (
        <div className="page">
            <div style={{ padding: 'var(--s6)', borderBottom: '1px solid var(--rule)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                    <div>
                        <h1 className="page-heading">System</h1>
                        <p className="page-subheading">Runtime status · configuration · processing metrics</p>
                    </div>
                    <div style={{ display: 'flex', gap: 'var(--s3)', alignItems: 'center' }}>
                        {ts && <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--ink-4)' }}>Checked {ts}</span>}
                        <button className="btn btn-ghost" onClick={load} disabled={loading}>Refresh</button>
                    </div>
                </div>
            </div>

            <div className="page-body">
                {loading ? (
                    <div className="loading-row">
                        <div className="loading-dot" />
                        <div className="loading-dot" />
                        <div className="loading-dot" />
                        Checking system status…
                    </div>
                ) : (
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--s8)', maxWidth: 900 }}>
                        {/* Status column */}
                        <div>
                            <div className="section-label" style={{ marginBottom: 'var(--s4)' }}>Service Status</div>

                            <div className="info-grid">
                                <div className="info-row">
                                    <span className="info-key"><StatusDot ok={health?.status === 'ok'} />API</span>
                                    <span className="info-val" style={{ color: health?.status === 'ok' ? 'var(--green)' : 'var(--red)' }}>
                                        {health?.status === 'ok' ? 'Operational' : 'Degraded'}
                                    </span>
                                </div>
                                <div className="info-row">
                                    <span className="info-key"><StatusDot ok={health?.database === 'ok'} />Database</span>
                                    <span className="info-val" style={{ color: health?.database === 'ok' ? 'var(--green)' : 'var(--red)' }}>
                                        {health?.database === 'ok' ? 'Connected' : 'Error'}
                                    </span>
                                </div>
                            </div>

                            <div className="section-label" style={{ marginTop: 'var(--s6)', marginBottom: 'var(--s4)' }}>Configuration</div>

                            <div className="info-grid">
                                <div className="info-row">
                                    <span className="info-key">LLM Provider</span>
                                    <span className="info-val">{health?.llm_provider || '—'}</span>
                                </div>
                                <div className="info-row">
                                    <span className="info-key">Embedding Model</span>
                                    <span className="info-val" style={{ fontSize: '0.72rem' }}>{health?.embedding_model || '—'}</span>
                                </div>
                                <div className="info-row">
                                    <span className="info-key">Version</span>
                                    <span className="info-val">{health?.version || '1.0.0'}</span>
                                </div>
                            </div>

                            <div className="section-label" style={{ marginTop: 'var(--s6)', marginBottom: 'var(--s4)' }}>Architecture</div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--ink-3)', lineHeight: 1.75 }}>
                                {[
                                    'PDF extraction via PyMuPDF',
                                    'Semantic chunking (512 token budget)',
                                    'Schema-constrained LLM fact extraction',
                                    'Evidence grounding validation',
                                    'Numeric + temporal normalization',
                                    'Fuzzy token-Jaccard entity resolution',
                                    'all-MiniLM-L6-v2 → pgvector embeddings',
                                    'Hybrid retrieval (vector + FTS + metadata)',
                                    'Deterministic contradiction engine',
                                    'LLM refinement for UNCERTAIN cases',
                                ].map((l, i) => (
                                    <div key={i} style={{ paddingLeft: 'var(--s4)', position: 'relative' }}>
                                        <span style={{ position: 'absolute', left: 0, color: 'var(--ink-4)' }}>·</span>
                                        {l}
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Metrics column */}
                        <div>
                            <div className="section-label" style={{ marginBottom: 'var(--s4)' }}>Processing Metrics</div>

                            {metrics ? (
                                <div className="info-grid">
                                    {METRIC_ROWS.map(([label, fn]) => (
                                        <div key={label} className="info-row" style={{ paddingLeft: label.startsWith('—') ? 'var(--s4)' : 0 }}>
                                            <span className="info-key">{label.replace('— ', '')}</span>
                                            <span className="info-val">{fn(metrics)}</span>
                                        </div>
                                    ))}
                                    <div className="info-row" style={{ paddingTop: 'var(--s2)' }}>
                                        <span className="info-key">Generated</span>
                                        <span className="info-val" style={{ fontSize: '0.7rem' }}>
                                            {new Date(metrics.generated_at).toLocaleString()}
                                        </span>
                                    </div>
                                </div>
                            ) : (
                                <div className="empty-state">
                                    <div className="empty-state-title">No metrics available</div>
                                    <div className="empty-state-body">Process documents to generate metrics.</div>
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
