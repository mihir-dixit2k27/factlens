import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { getFact, getFactEvidence } from '../api/client';
import type { Evidence, Fact } from '../types';

function norm(f: Fact) {
    if (!f.normalized_value && !f.object_text) return null;
    return [
        ['Raw', f.object_text],
        ['Normalized', f.normalized_value != null ? f.normalized_value.toLocaleString() : null],
        ['Currency', f.currency],
        ['Period', f.temporal_scope?.label],
        ['Scope', f.geographic_scope],
        ['Subject', f.subject_name],
    ].filter(([, v]) => v) as [string, string][];
}

export default function EvidenceViewer() {
    const { factId } = useParams();
    const [inputId, setInputId] = useState(factId || '');
    const [fact, setFact] = useState<Fact | null>(null);
    const [evidence, setEvidence] = useState<Evidence[]>([]);
    const [activeEv, setActiveEv] = useState(0);
    const [loading, setLoading] = useState(false);

    const load = (id: string) => {
        if (!id.trim()) return;
        setLoading(true);
        setActiveEv(0);
        Promise.all([getFact(id), getFactEvidence(id)])
            .then(([fr, er]) => { setFact(fr.data); setEvidence(er.data); })
            .catch(() => { setFact(null); setEvidence([]); })
            .finally(() => setLoading(false));
    };

    useEffect(() => { if (factId) load(factId); }, [factId]);

    const ev = evidence[activeEv];
    const normRows = fact ? norm(fact) : null;

    return (
        <div className="page" style={{ height: 'calc(100vh - 44px)', display: 'flex', flexDirection: 'column' }}>
            {/* Lookup bar */}
            <div style={{ padding: 'var(--s4) var(--s6)', borderBottom: '1px solid var(--rule)', display: 'flex', gap: 'var(--s3)', alignItems: 'center' }}>
                <span style={{ fontSize: '0.68rem', fontFamily: 'var(--font-mono)', color: 'var(--ink-4)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
                    Fact ID
                </span>
                <input value={inputId} onChange={e => setInputId(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && load(inputId)}
                    placeholder="Enter fact UUID or navigate from Facts Explorer…"
                    style={{ maxWidth: 360, fontFamily: 'var(--font-mono)', fontSize: '0.78rem' }} />
                <button className="btn btn-ghost" onClick={() => load(inputId)} disabled={loading}>
                    {loading ? 'Loading…' : 'Inspect'}
                </button>
                {evidence.length > 1 && (
                    <div style={{ marginLeft: 'auto', display: 'flex', gap: 'var(--s2)', alignItems: 'center' }}>
                        <span style={{ fontSize: '0.68rem', color: 'var(--ink-4)', fontFamily: 'var(--font-mono)' }}>
                            Evidence {activeEv + 1}/{evidence.length}
                        </span>
                        <button className="btn btn-ghost" disabled={activeEv === 0} onClick={() => setActiveEv(i => i - 1)} style={{ padding: '4px 8px' }}>←</button>
                        <button className="btn btn-ghost" disabled={activeEv === evidence.length - 1} onClick={() => setActiveEv(i => i + 1)} style={{ padding: '4px 8px' }}>→</button>
                    </div>
                )}
            </div>

            {!fact ? (
                <div className="empty-state" style={{ margin: 'auto' }}>
                    <div className="empty-state-title">No fact loaded</div>
                    <div className="empty-state-body">
                        Enter a Fact ID above, or click "Inspect →" from the Facts table<br />
                        to open the grounding evidence for any extracted claim.
                    </div>
                </div>
            ) : (
                <div className="workspace-split">
                    {/* Left: Document page */}
                    <div className="workspace-doc">
                        {ev ? (
                            <div className="doc-page">
                                {/* Page header */}
                                <div style={{ borderBottom: '1px solid var(--rule)', paddingBottom: 'var(--s4)', marginBottom: 'var(--s5)', display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
                                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--ink-4)', letterSpacing: '0.06em' }}>
                                        DOC {ev.chunk_id?.slice(0, 6) || '—'} · PAGE {ev.page_number} · EVIDENCE SPAN {activeEv + 1}
                                    </div>
                                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--ink-4)' }}>
                                        {ev.extraction_method}
                                    </div>
                                </div>

                                {/* Document body text with highlighted span */}
                                <div style={{ lineHeight: 1.85, color: 'var(--ink-2)' }}>
                                    {ev.exact_text ? (
                                        <span className="doc-text-highlighted">{ev.exact_text}</span>
                                    ) : (
                                        <span style={{ color: 'var(--ink-4)', fontStyle: 'italic' }}>No text span available</span>
                                    )}
                                </div>

                                {/* BBox */}
                                {ev.bbox && (
                                    <div style={{ marginTop: 'var(--s5)', paddingTop: 'var(--s4)', borderTop: '1px dashed var(--rule)', fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--ink-4)', letterSpacing: '0.04em' }}>
                                        BBOX [{ev.bbox.map(n => n.toFixed(1)).join(', ')}]
                                    </div>
                                )}

                                <div className="doc-page-num">{ev.page_number}</div>
                            </div>
                        ) : (
                            <div className="empty-state" style={{ margin: 'var(--s7) auto' }}>
                                <div className="empty-state-title">No evidence records</div>
                                <div className="empty-state-body">This fact has no grounded evidence spans.</div>
                            </div>
                        )}
                    </div>

                    {/* Right: Fact panel */}
                    <div className="workspace-fact">
                        {/* Fact header */}
                        <div style={{ padding: 'var(--s5) var(--s4)', borderBottom: '1px solid var(--rule)' }}>
                            <div className="detail-section-label">Fact</div>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.1rem', fontWeight: 700, color: 'var(--ink)', marginTop: 'var(--s2)', lineHeight: 1.2 }}>
                                {fact.object_text || '—'}
                            </div>
                            <div style={{ fontSize: '0.75rem', color: 'var(--ink-3)', marginTop: 'var(--s2)' }}>
                                {fact.predicate}
                            </div>
                        </div>

                        {/* Evidence confidence */}
                        {ev && (
                            <div className="detail-section">
                                <div className="detail-section-label">Source Evidence</div>
                                <div className="evidence-quote" style={{ marginBottom: 'var(--s3)' }}>
                                    "{ev.exact_text || '(no text span)'}"
                                </div>
                                <div className="info-grid">
                                    <div className="info-row">
                                        <span className="info-key">Page</span>
                                        <span className="info-val">{ev.page_number}</span>
                                    </div>
                                    <div className="info-row">
                                        <span className="info-key">Confidence</span>
                                        <span className="info-val">{(ev.extraction_confidence * 100).toFixed(1)}%</span>
                                    </div>
                                    <div className="info-row">
                                        <span className="info-key">Method</span>
                                        <span className="info-val">{ev.extraction_method}</span>
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Normalization */}
                        {normRows && normRows.length > 0 && (
                            <div className="detail-section">
                                <div className="detail-section-label">Normalization</div>
                                <div className="info-grid">
                                    {normRows.map(([k, v]) => (
                                        <div key={k} className="info-row">
                                            <span className="info-key">{k}</span>
                                            <span className="info-val">{v}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}

                        {/* Reasoning checks */}
                        <div className="detail-section">
                            <div className="detail-section-label">Grounding Checks</div>
                            <div className="info-grid">
                                {[
                                    ['Entity match', fact.subject_entity_id ? '✓' : '—'],
                                    ['Predicate', fact.predicate ? '✓' : '—'],
                                    ['Temporal scope', fact.temporal_scope ? '✓' : 'not found'],
                                    ['Geographic scope', fact.geographic_scope || '—'],
                                    ['Evidence spans', `${evidence.length}`],
                                    ['Overall confidence', `${(fact.confidence * 100).toFixed(1)}%`],
                                ].map(([k, v]) => (
                                    <div key={k} className="info-row">
                                        <span className="info-key">{k}</span>
                                        <span className="info-val" style={{ color: v === '—' || v === 'not found' ? 'var(--ink-4)' : undefined }}>{v}</span>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Status */}
                        <div className="detail-section">
                            <div className="detail-section-label">Reconciliation Status</div>
                            <div style={{ marginTop: 'var(--s2)' }}>
                                <span className={`tag ${fact.extraction_status === 'TRUSTED' ? 'tag-trusted' : fact.extraction_status === 'UNCERTAIN' ? 'tag-uncertain' : fact.extraction_status === 'FAILED_EXTRACTION' ? 'tag-failed' : 'tag-ready'}`}>
                                    {fact.extraction_status?.replace(/_/g, ' ') || '—'}
                                </span>
                            </div>
                            {fact.uncertainty_reasons && fact.uncertainty_reasons.length > 0 && (
                                <div style={{ marginTop: 'var(--s3)' }}>
                                    {fact.uncertainty_reasons.map((r, i) => (
                                        <div key={i} style={{ fontSize: '0.72rem', color: 'var(--amber)', marginBottom: 'var(--s1)', lineHeight: 1.5 }}>
                                            · {r}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
