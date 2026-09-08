import { useState } from 'react';
import { queryFacts } from '../api/client';
import type { Fact, Relationship } from '../types';

const EXAMPLES = [
    'revenue growth FY2024',
    'GDP forecast 2025',
    'employee headcount',
    'inflation CPI index',
    'market share percent',
];

const REL_LABEL: Record<string, string> = {
    CORROBORATES: 'Corroborates',
    CONTRADICTS: 'Contradicts',
    TEMPORALLY_DISTINCT: 'Temporal',
    APPARENT_CONTRADICTION: 'Apparent',
    DISTINCT_SCOPE: 'Scope diff',
    UNCERTAIN: 'Uncertain',
};
const REL_TAG: Record<string, string> = {
    CORROBORATES: 'tag-corroborates',
    CONTRADICTS: 'tag-contradicts',
    TEMPORALLY_DISTINCT: 'tag-temporal',
    APPARENT_CONTRADICTION: 'tag-apparent',
    DISTINCT_SCOPE: 'tag-scope',
    UNCERTAIN: 'tag-uncertain',
};

export default function QueryPage() {
    const [query, setQuery] = useState('');
    const [results, setResults] = useState<{
        answer: string;
        relevant_facts: Fact[];
        relevant_relationships: Relationship[];
        confidence: number;
    } | null>(null);
    const [loading, setLoading] = useState(false);

    const run = async (q: string) => {
        if (!q.trim()) return;
        setQuery(q);
        setLoading(true);
        setResults(null);
        try { setResults((await queryFacts(q)).data); } catch { /* */ }
        finally { setLoading(false); }
    };

    return (
        <div className="page">
            <div style={{ padding: 'var(--s6)', borderBottom: '1px solid var(--rule)' }}>
                <h1 className="page-heading">Query</h1>
                <p className="page-subheading">Semantic search over extracted facts · hybrid vector + full-text retrieval</p>
            </div>

            <div className="page-body" style={{ maxWidth: 800 }}>
                {/* Search */}
                <div style={{ display: 'flex', gap: 'var(--s3)' }}>
                    <input
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                        onKeyDown={e => e.key === 'Enter' && run(query)}
                        placeholder="Search facts across all documents…"
                        style={{ fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}
                        autoFocus
                    />
                    <button className="btn btn-primary" onClick={() => run(query)} disabled={loading}>
                        {loading ? 'Searching…' : 'Search'}
                    </button>
                </div>

                {/* Example queries */}
                <div style={{ display: 'flex', gap: 'var(--s2)', flexWrap: 'wrap', marginTop: 'var(--s3)' }}>
                    {EXAMPLES.map(ex => (
                        <button key={ex} onClick={() => run(ex)}
                            style={{
                                background: 'none', border: '1px solid var(--rule-heavy)', padding: '3px 10px',
                                fontSize: '0.72rem', cursor: 'pointer', color: 'var(--ink-3)', borderRadius: 2,
                                fontFamily: 'var(--font-sans)', transition: 'all 0.1s',
                            }}
                            onMouseOver={e => (e.currentTarget.style.borderColor = 'var(--accent-text)')}
                            onMouseOut={e => (e.currentTarget.style.borderColor = 'var(--rule-heavy)')}>
                            {ex}
                        </button>
                    ))}
                </div>

                {/* Results */}
                {results && (
                    <div style={{ marginTop: 'var(--s6)' }}>
                        {/* Answer */}
                        <div style={{ borderLeft: '2px solid var(--accent)', paddingLeft: 'var(--s4)', marginBottom: 'var(--s6)' }}>
                            <div style={{ fontSize: '0.62rem', letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-4)', marginBottom: 'var(--s2)' }}>
                                Synthesized Answer · {(results.confidence * 100).toFixed(0)}% retrieval confidence
                            </div>
                            <div style={{ fontSize: '0.9rem', color: 'var(--ink)', lineHeight: 1.7 }}>{results.answer}</div>
                        </div>

                        {/* Relevant facts */}
                        {results.relevant_facts.length > 0 && (
                            <div style={{ marginBottom: 'var(--s6)' }}>
                                <div className="section-label" style={{ marginBottom: 'var(--s4)' }}>
                                    {results.relevant_facts.length} relevant facts
                                </div>
                                <table className="data-table">
                                    <thead>
                                        <tr>
                                            <th>Predicate</th>
                                            <th>Value</th>
                                            <th>Period</th>
                                            <th>Confidence</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {results.relevant_facts.slice(0, 10).map(f => (
                                            <tr key={f.id}>
                                                <td className="cell-primary" style={{ maxWidth: 200 }}>
                                                    <div className="truncate">{f.predicate}</div>
                                                    {f.subject_name && <div style={{ fontSize: '0.65rem', color: 'var(--ink-4)' }}>{f.subject_name}</div>}
                                                </td>
                                                <td className="cell-mono">{f.object_text || '—'}</td>
                                                <td className="cell-muted">{f.temporal_scope?.label || '—'}</td>
                                                <td className="cell-mono" style={{ fontSize: '0.72rem', color: 'var(--ink-3)' }}>
                                                    {(f.confidence * 100).toFixed(0)}%
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        )}

                        {/* Related reconciliations */}
                        {results.relevant_relationships.length > 0 && (
                            <div>
                                <div className="section-label" style={{ marginBottom: 'var(--s4)' }}>
                                    {results.relevant_relationships.length} related reconciliations
                                </div>
                                {results.relevant_relationships.slice(0, 4).map(rel => (
                                    <div key={rel.id} style={{ borderBottom: '1px solid var(--rule)', padding: 'var(--s3) 0', display: 'flex', gap: 'var(--s4)', alignItems: 'baseline' }}>
                                        <span className={`tag ${REL_TAG[rel.relationship_type] || 'tag-uncertain'}`}>
                                            {REL_LABEL[rel.relationship_type] || rel.relationship_type}
                                        </span>
                                        <span style={{ fontSize: '0.78rem', color: 'var(--ink-3)', flex: 1 }}>
                                            {rel.reasoning?.slice(0, 140)}…
                                        </span>
                                        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.68rem', color: 'var(--ink-4)', flexShrink: 0 }}>
                                            {(rel.confidence * 100).toFixed(0)}%
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {!results && !loading && (
                    <div className="empty-state" style={{ paddingTop: 'var(--s7)' }}>
                        <div className="empty-state-title">Enter a query above</div>
                        <div className="empty-state-body">
                            Search over any claim in any document — revenue figures, forecasts,<br />
                            headcount, market share, or any other extracted fact.
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
