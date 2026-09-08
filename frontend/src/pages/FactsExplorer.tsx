import { useEffect, useState } from 'react';
import { listFacts } from '../api/client';
import type { Fact } from '../types';
import { useNavigate } from 'react-router-dom';

const STATUS_TAG: Record<string, string> = {
    TRUSTED: 'tag-trusted',
    PROBABLE: 'tag-ready',
    UNCERTAIN: 'tag-uncertain',
    FAILED_EXTRACTION: 'tag-failed',
};

const STATUS_LABEL: Record<string, string> = {
    TRUSTED: 'Corroborated',
    PROBABLE: 'Probable',
    UNCERTAIN: 'Uncertain',
    FAILED_EXTRACTION: 'Failed',
};

function ConfBar({ v }: { v: number }) {
    const color = v >= 0.8 ? 'var(--green)' : v >= 0.5 ? 'var(--ink-3)' : 'var(--amber)';
    return (
        <div className="conf-strip">
            <div className="conf-bar">
                <div className="conf-bar-fill" style={{ width: `${v * 100}%`, background: color }} />
            </div>
            <span className="conf-val">{(v * 100).toFixed(0)}%</span>
        </div>
    );
}

export default function FactsExplorer() {
    const [facts, setFacts] = useState<Fact[]>([]);
    const [total, setTotal] = useState(0);
    const [search, setSearch] = useState('');
    const [statusFilter, setStatusFilter] = useState('');
    const [page, setPage] = useState(0);
    const limit = 40;
    const navigate = useNavigate();

    const load = () =>
        listFacts({
            skip: page * limit,
            limit,
            status: statusFilter || undefined,
            predicate: search || undefined,
        }).then(r => { setFacts(r.data.items); setTotal(r.data.total); });

    useEffect(() => { load(); }, [page, statusFilter, search]);

    return (
        <div className="page" style={{ height: 'calc(100vh - 44px)', display: 'flex', flexDirection: 'column' }}>
            {/* Header */}
            <div style={{ padding: 'var(--s5) var(--s6)', borderBottom: '1px solid var(--rule)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: 'var(--s4)' }}>
                    <div>
                        <h1 className="page-heading">Facts</h1>
                        <p className="page-subheading">{total.toLocaleString()} extracted claims · each grounded to source evidence</p>
                    </div>
                </div>

                {/* Filters */}
                <div style={{ display: 'flex', gap: 'var(--s3)', alignItems: 'center' }}>
                    <input
                        placeholder="Filter by predicate…"
                        value={search}
                        onChange={e => { setSearch(e.target.value); setPage(0); }}
                        style={{ maxWidth: 240 }}
                    />
                    <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(0); }} style={{ maxWidth: 160 }}>
                        <option value="">All states</option>
                        <option value="TRUSTED">Corroborated</option>
                        <option value="PROBABLE">Probable</option>
                        <option value="UNCERTAIN">Uncertain</option>
                        <option value="FAILED_EXTRACTION">Failed</option>
                    </select>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--ink-4)', marginLeft: 'auto' }}>
                        {page * limit + 1}–{Math.min((page + 1) * limit, total)} of {total.toLocaleString()}
                    </span>
                </div>
            </div>

            {/* Table */}
            <div style={{ flex: 1, overflow: 'auto' }}>
                <table className="data-table">
                    <thead>
                        <tr>
                            <th style={{ width: 260 }}>Predicate</th>
                            <th style={{ width: 180 }}>Value</th>
                            <th style={{ width: 100 }}>Period</th>
                            <th style={{ width: 80 }}>Scope</th>
                            <th style={{ width: 60 }}>Doc</th>
                            <th style={{ width: 90 }}>Confidence</th>
                            <th style={{ width: 110 }}>State</th>
                            <th style={{ width: 80 }}>Evidence</th>
                        </tr>
                    </thead>
                    <tbody>
                        {facts.map(f => (
                            <tr key={f.id} onClick={() => navigate(`/evidence/${f.id}`)}>
                                <td className="cell-primary" style={{ maxWidth: 260 }}>
                                    <div className="truncate" title={f.predicate}>{f.predicate}</div>
                                    {f.subject_name && (
                                        <div style={{ fontSize: '0.68rem', color: 'var(--ink-4)', marginTop: 1 }} className="truncate">
                                            {f.subject_name}
                                        </div>
                                    )}
                                </td>
                                <td className="cell-mono" style={{ maxWidth: 180 }}>
                                    <div className="truncate">{f.object_text || '—'}</div>
                                </td>
                                <td className="cell-mono" style={{ fontSize: '0.72rem', color: 'var(--ink-3)' }}>
                                    {f.temporal_scope?.label || '—'}
                                </td>
                                <td style={{ fontSize: '0.72rem', color: 'var(--ink-3)' }}>
                                    {f.geographic_scope || '—'}
                                </td>
                                <td className="cell-mono" style={{ fontSize: '0.68rem', color: 'var(--ink-4)' }}>
                                    {f.primary_document_id ? f.primary_document_id.slice(0, 6) : '—'}
                                </td>
                                <td>
                                    <ConfBar v={f.confidence} />
                                </td>
                                <td>
                                    <span className={`tag ${STATUS_TAG[f.extraction_status] || 'tag-uncertain'}`}>
                                        {STATUS_LABEL[f.extraction_status] || f.extraction_status}
                                    </span>
                                </td>
                                <td>
                                    <button className="btn-link" onClick={e => { e.stopPropagation(); navigate(`/evidence/${f.id}`); }}
                                        style={{ fontSize: '0.68rem' }}>
                                        Inspect →
                                    </button>
                                </td>
                            </tr>
                        ))}
                        {facts.length === 0 && (
                            <tr>
                                <td colSpan={8}>
                                    <div className="empty-state">
                                        <div className="empty-state-title">No facts match your filters</div>
                                        <div className="empty-state-body">Process documents to populate the fact register.</div>
                                    </div>
                                </td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>

            {/* Pagination */}
            <div style={{ borderTop: '1px solid var(--rule)', padding: 'var(--s3) var(--s6)', display: 'flex', gap: 'var(--s3)', alignItems: 'center' }}>
                <button className="btn btn-ghost" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Previous</button>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--ink-4)' }}>
                    Page {page + 1} of {Math.max(1, Math.ceil(total / limit))}
                </span>
                <button className="btn btn-ghost" disabled={(page + 1) * limit >= total} onClick={() => setPage(p => p + 1)}>Next →</button>
            </div>
        </div>
    );
}
