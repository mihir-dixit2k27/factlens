import { useEffect, useState } from 'react';
import { listFacts, getFactEvidence } from '../api/client';
import type { Fact, Evidence } from '../types';

export default function Failures() {
    const [facts, setFacts] = useState<Fact[]>([]);
    const [total, setTotal] = useState(0);
    const [selected, setSelected] = useState<Fact | null>(null);
    const [evidence, setEvidence] = useState<Evidence[]>([]);

    useEffect(() => {
        listFacts({ status: 'FAILED_EXTRACTION', limit: 60 })
            .then(r => { setFacts(r.data.items); setTotal(r.data.total); })
            .catch(() => { });
    }, []);

    useEffect(() => {
        if (selected) getFactEvidence(selected.id).then(r => setEvidence(r.data)).catch(() => setEvidence([]));
        else setEvidence([]);
    }, [selected]);

    return (
        <div className="page" style={{ height: 'calc(100vh - 44px)', display: 'flex', flexDirection: 'column' }}>
            {/* Header */}
            <div style={{ padding: 'var(--s5) var(--s6)', borderBottom: '1px solid var(--rule)' }}>
                <h1 className="page-heading">Uncertainty Register</h1>
                <p className="page-subheading">
                    {total} claim{total !== 1 ? 's' : ''} requiring review · failed grounding validation or below confidence threshold
                </p>
                <div style={{ marginTop: 'var(--s4)', paddingTop: 'var(--s4)', borderTop: '1px solid var(--rule)', fontSize: '0.75rem', color: 'var(--ink-3)', lineHeight: 1.6, maxWidth: 640 }}>
                    <strong style={{ color: 'var(--ink-2)' }}>Design principle:</strong> Failures are first-class research objects. Every rejected claim is stored with its failure reason and made inspectable here — not silently discarded. This allows root-cause analysis, threshold tuning, and future evidence recovery.
                </div>
            </div>

            <div style={{ flex: 1, overflow: 'hidden', display: 'flex' }}>
                {/* Table */}
                <div style={{ flex: 1, overflow: 'auto' }}>
                    {facts.length === 0 ? (
                        <div className="empty-state">
                            <div className="empty-state-title">No failed extractions</div>
                            <div className="empty-state-body">All processed facts passed grounding validation.</div>
                        </div>
                    ) : (
                        <table className="data-table">
                            <thead>
                                <tr>
                                    <th style={{ width: 240 }}>Claim</th>
                                    <th style={{ width: 200 }}>Issue</th>
                                    <th style={{ width: 90 }}>Confidence</th>
                                    <th style={{ width: 100 }}>Source</th>
                                    <th style={{ width: 80 }}>Action</th>
                                </tr>
                            </thead>
                            <tbody>
                                {facts.map(f => (
                                    <tr key={f.id} className={selected?.id === f.id ? 'selected' : ''} onClick={() => setSelected(f === selected ? null : f)}>
                                        <td className="cell-primary" style={{ maxWidth: 240 }}>
                                            <div className="truncate">{f.predicate}</div>
                                            {f.object_text && (
                                                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--ink-3)', marginTop: 1 }} className="truncate">
                                                    {f.object_text}
                                                </div>
                                            )}
                                        </td>
                                        <td style={{ maxWidth: 200 }}>
                                            {(f.uncertainty_reasons || []).slice(0, 2).map((r, i) => (
                                                <div key={i} style={{ fontSize: '0.72rem', color: 'var(--amber)', lineHeight: 1.5 }} className="truncate">
                                                    {i === 0 ? '' : '+ '}{r}
                                                </div>
                                            ))}
                                            {!f.uncertainty_reasons?.length && (
                                                <span style={{ fontSize: '0.72rem', color: 'var(--ink-4)' }}>Unknown</span>
                                            )}
                                        </td>
                                        <td className="cell-mono" style={{ color: 'var(--amber)' }}>
                                            {(f.confidence * 100).toFixed(0)}%
                                        </td>
                                        <td className="cell-mono" style={{ fontSize: '0.68rem', color: 'var(--ink-4)' }}>
                                            {f.primary_document_id ? f.primary_document_id.slice(0, 8) : '—'}
                                        </td>
                                        <td>
                                            <button className="btn-link" onClick={e => { e.stopPropagation(); setSelected(f); }}>
                                                Inspect →
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>

                {/* Failure analysis panel */}
                {selected && (
                    <div className="detail-panel">
                        <div className="detail-panel-header">
                            <div className="detail-panel-title">Failure Analysis</div>
                            <button className="detail-panel-close" onClick={() => setSelected(null)}>✕</button>
                        </div>

                        <div className="detail-section">
                            <div className="detail-section-label">Claim</div>
                            <div style={{ fontSize: '0.82rem', color: 'var(--ink)', fontWeight: 600, marginBottom: 'var(--s2)' }}>{selected.predicate}</div>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--ink-2)' }}>
                                {selected.object_text || '(no value extracted)'}
                            </div>
                        </div>

                        <div className="detail-section">
                            <div className="detail-section-label">Failure Reasons</div>
                            {(selected.uncertainty_reasons || ['Unknown cause']).map((r, i) => (
                                <div key={i} style={{ padding: 'var(--s2) 0', borderBottom: '1px solid var(--rule)', fontSize: '0.78rem', color: 'var(--amber)', lineHeight: 1.5 }}>
                                    {i + 1}. {r}
                                </div>
                            ))}
                        </div>

                        <div className="detail-section">
                            <div className="detail-section-label">Confidence</div>
                            <div style={{ fontFamily: 'var(--font-mono)', fontSize: '1.2rem', fontWeight: 600, color: 'var(--amber)' }}>
                                {(selected.confidence * 100).toFixed(1)}%
                            </div>
                            <div style={{ fontSize: '0.72rem', color: 'var(--ink-4)', marginTop: 'var(--s1)' }}>
                                Below minimum threshold for persistence
                            </div>
                        </div>

                        <div className="detail-section">
                            <div className="detail-section-label">Root Cause</div>
                            <div style={{ fontSize: '0.78rem', color: 'var(--ink-2)', lineHeight: 1.65 }}>
                                <strong style={{ color: 'var(--ink)' }}>What was rejected:</strong><br />
                                Evidence grounding validation failed before DB persistence. The LLM-provided evidence span did not have sufficient character overlap with the original document chunk text.
                            </div>
                            <div style={{ marginTop: 'var(--s3)', fontSize: '0.78rem', color: 'var(--ink-2)', lineHeight: 1.65 }}>
                                <strong style={{ color: 'var(--ink)' }}>Detection method:</strong><br />
                                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--ink-3)' }}>evidence_validator.validate_fact_grounding()</span>
                            </div>
                            <div style={{ marginTop: 'var(--s3)', fontSize: '0.78rem', color: 'var(--ink-2)', lineHeight: 1.65 }}>
                                <strong style={{ color: 'var(--ink)' }}>Recovery paths:</strong><br />
                                Multi-span evidence linking · adaptive chunk boundaries · confidence threshold tuning · manual labeling
                            </div>
                        </div>

                        {evidence.length > 0 && (
                            <div className="detail-section">
                                <div className="detail-section-label">Submitted Evidence (Rejected)</div>
                                <div className="evidence-quote">{evidence[0].exact_text}</div>
                                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--ink-4)', marginTop: 'var(--s2)' }}>
                                    Page {evidence[0].page_number} · Conf {(evidence[0].extraction_confidence * 100).toFixed(0)}%
                                </div>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
    );
}
