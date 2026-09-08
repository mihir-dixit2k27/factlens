import { useEffect, useState } from 'react';
import { getCases, getMetrics } from '../api/client';
import type { SystemMetrics, RequiredCase } from '../types';
import { useNavigate } from 'react-router-dom';

const now = new Date();
const dateStr = now.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' }).toUpperCase();

const TYPE_LABEL: Record<string, string> = {
    CORROBORATES: 'Corroboration',
    CONTRADICTS: 'Contradiction',
    TEMPORALLY_DISTINCT: 'Temporal Distinction',
    APPARENT_CONTRADICTION: 'Apparent Contradiction',
    DISTINCT_SCOPE: 'Scope Difference',
    UNIT_MISMATCH: 'Unit Mismatch',
    UNCERTAIN: 'Uncertain',
    FAILED_EXTRACTION: 'Extraction Failure',
};

const TYPE_CLASS: Record<string, string> = {
    CORROBORATES: 'tag-corroborates',
    CONTRADICTS: 'tag-contradicts',
    TEMPORALLY_DISTINCT: 'tag-temporal',
    APPARENT_CONTRADICTION: 'tag-apparent',
    DISTINCT_SCOPE: 'tag-scope',
    UNCERTAIN: 'tag-uncertain',
    UNIT_MISMATCH: 'tag-uncertain',
    FAILED_EXTRACTION: 'tag-failed',
};

export default function Dashboard() {
    const [metrics, setMetrics] = useState<SystemMetrics | null>(null);
    const [cases, setCases] = useState<RequiredCase[]>([]);
    const navigate = useNavigate();

    useEffect(() => {
        getMetrics().then(r => setMetrics(r.data)).catch(() => { });
        getCases().then(r => setCases(r.data.cases || [])).catch(() => { });
    }, []);

    return (
        <div className="page">
            {/* ── Header ── */}
            <div style={{ padding: 'var(--s6)', borderBottom: '1px solid var(--rule-heavy)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div>
                        <h1 className="page-heading">Cross-document knowledge intelligence</h1>
                        <p className="page-subheading">Evidence-first. Every conclusion traces back to its source.</p>
                    </div>
                    <div className="text-mono text-faint" style={{ fontSize: '0.65rem', textAlign: 'right', lineHeight: 1.8 }}>
                        {dateStr}
                    </div>
                </div>

                {/* Stats strip */}
                {metrics && (
                    <div className="stats-strip" style={{ marginTop: 'var(--s5)' }}>
                        <div className="stat-item">
                            <div className="stat-item-label">Documents</div>
                            <div className="stat-item-value">{metrics.documents_total}</div>
                        </div>
                        <div className="stat-item">
                            <div className="stat-item-label">Pages</div>
                            <div className="stat-item-value">{metrics.pages_total.toLocaleString()}</div>
                        </div>
                        <div className="stat-item">
                            <div className="stat-item-label">Facts</div>
                            <div className="stat-item-value">{metrics.facts_total.toLocaleString()}</div>
                        </div>
                        <div className="stat-item">
                            <div className="stat-item-label">Grounded</div>
                            <div className="stat-item-value">{metrics.grounded_facts_total.toLocaleString()}</div>
                            <div className="stat-item-sub">{(metrics.fact_grounding_rate * 100).toFixed(1)}% rate</div>
                        </div>
                        <div className="stat-item">
                            <div className="stat-item-label">Relationships</div>
                            <div className="stat-item-value">{metrics.relationships_total.toLocaleString()}</div>
                        </div>
                        <div className="stat-item">
                            <div className="stat-item-label">Contradictions</div>
                            <div className="stat-item-value" style={{ color: metrics.contradictions > 0 ? 'var(--red)' : 'var(--ink)' }}>{metrics.contradictions}</div>
                        </div>
                        <div className="stat-item">
                            <div className="stat-item-label">Avg Confidence</div>
                            <div className="stat-item-value">{(metrics.average_confidence * 100).toFixed(0)}<span style={{ fontSize: '0.7rem', color: 'var(--ink-3)' }}>%</span></div>
                        </div>
                    </div>
                )}
            </div>

            {/* ── Briefing ── */}
            <div className="page-body">
                <div style={{ maxWidth: 900 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 'var(--s4)' }}>
                        <div className="section-label">Required Cases · Reconciliation Findings</div>
                        <button className="btn-link" onClick={() => navigate('/reconciliation')}>
                            View all reconciliations →
                        </button>
                    </div>

                    {cases.length === 0 && !metrics && (
                        <div className="empty-state">
                            <div className="empty-state-title">No findings yet</div>
                            <div className="empty-state-body">
                                Upload documents to begin cross-document fact reconciliation.
                            </div>
                            <button className="btn btn-primary" style={{ marginTop: 'var(--s4)' }} onClick={() => navigate('/documents')}>
                                Upload documents
                            </button>
                        </div>
                    )}

                    {cases.map((c, i) => (
                        <div key={c.case_number}
                            className="briefing-item"
                            onClick={() => c.relationship_id
                                ? navigate(`/reconciliation?rel=${c.relationship_id}`)
                                : navigate('/reconciliation')
                            }>
                            <div className="briefing-num">0{i + 1}</div>
                            <div className="briefing-body">
                                <div className="briefing-type">
                                    <span className={`tag ${TYPE_CLASS[c.case_type ?? ''] || 'tag-uncertain'}`}>
                                        {TYPE_LABEL[c.case_type ?? ''] || (c.case_type ?? c.label).replace(/_/g, ' ')}
                                    </span>
                                </div>
                                <div className="briefing-title" style={{ marginTop: 'var(--s2)' }}>{c.title}</div>
                                <div className="briefing-desc">{c.description}</div>

                                {/* Fact comparison */}
                                {(c.fact_a || c.fact_b) && (
                                    <div style={{ display: 'flex', gap: 'var(--s6)', marginTop: 'var(--s4)' }}>
                                        {c.fact_a && (
                                            <div style={{ flex: 1 }}>
                                                <div className="text-faint" style={{ fontSize: '0.62rem', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 4 }}>
                                                    {c.fact_a.primary_document_id ? `Doc ${c.fact_a.primary_document_id.slice(0, 6)}` : 'Claim A'}
                                                </div>
                                                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 600, color: 'var(--ink)' }}>
                                                    {c.fact_a.object_text || '—'}
                                                </div>
                                                {c.fact_a.temporal_scope?.label && (
                                                    <div style={{ fontSize: '0.7rem', color: 'var(--ink-3)', marginTop: 2 }}>{c.fact_a.temporal_scope.label}</div>
                                                )}
                                            </div>
                                        )}

                                        {c.fact_a && c.fact_b && (
                                            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 4, paddingTop: 12 }}>
                                                <div style={{ width: 1, flex: 1, background: c.case_type === 'CONTRADICTS' ? 'var(--red)' : 'var(--rule-heavy)' }} />
                                                <div style={{ fontSize: '0.55rem', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-4)', transform: 'rotate(90deg)', whiteSpace: 'nowrap' }}>vs</div>
                                                <div style={{ width: 1, flex: 1, background: c.case_type === 'CONTRADICTS' ? 'var(--red)' : 'var(--rule-heavy)' }} />
                                            </div>
                                        )}

                                        {c.fact_b && (
                                            <div style={{ flex: 1 }}>
                                                <div className="text-faint" style={{ fontSize: '0.62rem', letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 4 }}>
                                                    {c.fact_b.primary_document_id ? `Doc ${c.fact_b.primary_document_id.slice(0, 6)}` : 'Claim B'}
                                                </div>
                                                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 600, color: 'var(--ink)' }}>
                                                    {c.fact_b.object_text || '—'}
                                                </div>
                                                {c.fact_b.temporal_scope?.label && (
                                                    <div style={{ fontSize: '0.7rem', color: 'var(--ink-3)', marginTop: 2 }}>{c.fact_b.temporal_scope.label}</div>
                                                )}
                                            </div>
                                        )}
                                    </div>
                                )}

                                {c.reasoning && (
                                    <div style={{ marginTop: 'var(--s3)', fontSize: '0.75rem', color: 'var(--ink-3)', lineHeight: 1.6, borderTop: '1px solid var(--rule)', paddingTop: 'var(--s3)' }}>
                                        {c.reasoning.slice(0, 180)}{(c.reasoning?.length ?? 0) > 180 ? '…' : ''}
                                    </div>
                                )}
                            </div>
                            <div className="briefing-arrow">→</div>
                        </div>
                    ))}

                    {/* Reconciliation summary */}
                    {metrics && metrics.relationships_total > 0 && (
                        <div style={{ marginTop: 'var(--s6)', paddingTop: 'var(--s5)', borderTop: '1px solid var(--rule)' }}>
                            <div className="section-label">Reconciliation Distribution</div>
                            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 'var(--s5)', marginTop: 'var(--s4)' }}>
                                {[
                                    ['Corroborations', metrics.corroborations, 'var(--green)'],
                                    ['Contradictions', metrics.contradictions, 'var(--red)'],
                                    ['Contextual', metrics.apparent_contradictions + metrics.temporally_distinct + metrics.distinct_scope, 'var(--amber)'],
                                    ['Uncertain', metrics.relationships_total - metrics.corroborations - metrics.contradictions - metrics.apparent_contradictions - metrics.temporally_distinct - metrics.distinct_scope, 'var(--ink-4)'],
                                ].map(([label, val]) => (
                                    <div key={label as string} style={{ paddingLeft: 'var(--s4)', borderLeft: '2px solid var(--rule-heavy)' }}>
                                        <div style={{ fontSize: '0.62rem', textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--ink-4)' }}>{label}</div>
                                        <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.5rem', fontWeight: 600, color: 'var(--ink)', marginTop: 2 }}>{Math.max(0, val as number)}</div>
                                        <div style={{ height: 2, background: 'var(--rule)', marginTop: 'var(--s3)' }}>
                                            <div style={{ height: '100%', background: val as string, width: `${Math.min(100, ((val as number) / metrics.relationships_total) * 100)}%`, transition: 'width 0.5s ease' }} />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
