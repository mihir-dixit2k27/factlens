import { useEffect, useState, useRef } from 'react';
import { listDocuments, uploadDocument, triggerProcessing } from '../api/client';
import type { Document } from '../types';

const STAGE_ORDER = ['READY', 'EXTRACTING', 'CHUNKING', 'EXTRACTING_FACTS', 'NORMALIZING', 'EMBEDDING', 'RECONCILING', 'COMPLETE', 'FAILED'];
const STAGE_LABEL: Record<string, string> = {
    READY: 'Ready', PENDING: 'Pending', EXTRACTING: 'Ingest', CHUNKING: 'Segment',
    EXTRACTING_FACTS: 'Fact Discovery', NORMALIZING: 'Normalize',
    EMBEDDING: 'Embed', RECONCILING: 'Reconcile',
    COMPLETE: 'Complete', FAILED: 'Failed',
};

function PipelineBar({ doc }: { doc: Document }) {
    const stages = STAGE_ORDER.slice(0, -1);
    const doneIdx = STAGE_ORDER.indexOf(doc.processing_stage);
    return (
        <div style={{ display: 'flex', gap: 1, height: 3 }}>
            {stages.map((s, i) => (
                <div key={s} style={{
                    flex: 1, height: '100%',
                    background:
                        doc.processing_stage === 'FAILED' && i <= doneIdx ? 'var(--red)' :
                            i < doneIdx ? 'var(--green)' :
                                i === doneIdx ? 'var(--accent)' : 'var(--rule)',
                }} />
            ))}
        </div>
    );
}

const isUnprocessed = (stage: string) => stage === 'READY' || stage === 'PENDING' || stage === 'UPLOADED';

export default function Documents() {
    const [docs, setDocs] = useState<Document[]>([]);
    const [total, setTotal] = useState(0);
    const [uploading, setUploading] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [processing, setProcessing] = useState<string | null>(null);
    const fileRef = useRef<HTMLInputElement>(null);

    const load = () =>
        listDocuments(0, 50).then(r => {
            setDocs(r.data.items);
            setTotal(r.data.total);
        });

    useEffect(() => {
        load();
        const iv = setInterval(load, 5000);
        return () => clearInterval(iv);
    }, []);

    const upload = async (files: FileList | null) => {
        if (!files) return;
        setUploading(true);
        for (const f of Array.from(files)) {
            try { await uploadDocument(f); } catch { /* continue */ }
        }
        setUploading(false);
        load();
    };

    const process = async (id: string) => {
        setProcessing(id);
        try { await triggerProcessing(id); } catch { /* */ }
        setProcessing(null);
        setTimeout(load, 2000);
    };

    return (
        <div className="page">
            <div style={{ padding: 'var(--s6)', borderBottom: '1px solid var(--rule)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
                    <div>
                        <h1 className="page-heading">Documents</h1>
                        <p className="page-subheading">{total} archival object{total !== 1 ? 's' : ''} in corpus</p>
                    </div>
                    <button className="btn btn-ghost" onClick={() => fileRef.current?.click()}>
                        {uploading ? 'Uploading…' : 'Upload PDF'}
                    </button>
                </div>
            </div>

            <div className="page-body">
                <div
                    className={`upload-zone${dragOver ? ' active' : ''}`}
                    onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={e => { e.preventDefault(); setDragOver(false); upload(e.dataTransfer.files); }}
                    onClick={() => fileRef.current?.click()}
                >
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--ink-3)', letterSpacing: '0.04em' }}>
                        Drop PDF files here, or click to browse
                    </div>
                    <div className="uz-label">Max 100 MB per file · Multiple files accepted</div>
                </div>
                <input ref={fileRef} type="file" accept=".pdf" multiple hidden onChange={e => upload(e.target.files)} />

                <div style={{ marginTop: 'var(--s6)' }}>
                    {docs.length === 0 ? (
                        <div className="empty-state">
                            <div className="empty-state-title">No documents in corpus</div>
                            <div className="empty-state-body">Upload one or more PDF files to begin extraction and reconciliation.</div>
                        </div>
                    ) : (
                        <div className="data-table-wrap">
                            <table className="data-table">
                                <thead>
                                    <tr>
                                        <th>Document</th>
                                        <th>Pages</th>
                                        <th>Size</th>
                                        <th>Stage</th>
                                        <th>Progress</th>
                                        <th>Actions</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {docs.map(d => (
                                        <tr key={d.id}>
                                            <td className="cell-primary" style={{ maxWidth: 280 }}>
                                                <div className="truncate">{d.filename}</div>
                                                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.62rem', color: 'var(--ink-4)', marginTop: 1 }}>
                                                    {d.id.slice(0, 8)}
                                                </div>
                                            </td>
                                            <td className="cell-mono">{d.page_count ?? '—'}</td>
                                            <td className="cell-mono" style={{ fontSize: '0.68rem', color: 'var(--ink-4)' }}>
                                                {d.file_size_bytes ? `${(d.file_size_bytes / 1024).toFixed(0)} KB` : '—'}
                                            </td>
                                            <td>
                                                <span className={`tag ${d.processing_stage === 'COMPLETE' ? 'tag-ready' :
                                                        d.processing_stage === 'FAILED' ? 'tag-failed' :
                                                            isUnprocessed(d.processing_stage) ? 'tag-uncertain' :
                                                                'tag-processing'
                                                    }`}>
                                                    {STAGE_LABEL[d.processing_stage] || d.processing_stage}
                                                </span>
                                            </td>
                                            <td style={{ width: 120 }}>
                                                <div style={{ marginBottom: 3 }}><PipelineBar doc={d} /></div>
                                                <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.6rem', color: 'var(--ink-4)' }}>
                                                    {d.processing_stage === 'COMPLETE' ? '100%' : d.processing_stage === 'FAILED' ? 'failed' : isUnprocessed(d.processing_stage) ? 'queued' : '…'}
                                                </div>
                                            </td>
                                            <td>
                                                {isUnprocessed(d.processing_stage) && (
                                                    <button className="btn btn-ghost" style={{ fontSize: '0.72rem', padding: '3px 10px' }}
                                                        onClick={() => process(d.id)} disabled={processing === d.id}>
                                                        {processing === d.id ? 'Processing…' : 'Process'}
                                                    </button>
                                                )}
                                                {d.processing_stage === 'FAILED' && (
                                                    <button className="btn btn-ghost" style={{ fontSize: '0.72rem', padding: '3px 10px', color: 'var(--red)' }}
                                                        onClick={() => process(d.id)} disabled={processing === d.id}>
                                                        Retry
                                                    </button>
                                                )}
                                                {d.processing_stage === 'COMPLETE' && (
                                                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--green)' }}>✓</span>
                                                )}
                                                {!isUnprocessed(d.processing_stage) && d.processing_stage !== 'FAILED' && d.processing_stage !== 'COMPLETE' && (
                                                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.65rem', color: 'var(--accent)' }}>running</span>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
