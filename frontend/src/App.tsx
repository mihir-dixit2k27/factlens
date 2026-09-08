import { BrowserRouter, Routes, Route, NavLink, useLocation, useNavigate } from 'react-router-dom';
import { useState, useEffect, useCallback } from 'react';
import { getMetrics } from './api/client';

import Dashboard from './pages/Dashboard';
import Documents from './pages/Documents';
import FactsExplorer from './pages/FactsExplorer';
import Reconciliation from './pages/Reconciliation';
import EvidenceViewer from './pages/EvidenceViewer';
import Failures from './pages/Failures';
import Health from './pages/Health';
import QueryPage from './pages/QueryPage';

/* ────────────────────────────────────────────────────────────
   Command Palette
   ──────────────────────────────────────────────────────────── */
const COMMANDS = [
    { label: 'Overview', href: '/', group: 'Navigation' },
    { label: 'Documents', href: '/documents', group: 'Navigation' },
    { label: 'Facts Explorer', href: '/facts', group: 'Navigation' },
    { label: 'Reconciliation', href: '/reconciliation', group: 'Navigation' },
    { label: 'Evidence Viewer', href: '/evidence', group: 'Navigation' },
    { label: 'Semantic Query', href: '/query', group: 'Navigation' },
    { label: 'Uncertainty Register', href: '/failures', group: 'Navigation' },
    { label: 'System Health', href: '/health', group: 'Navigation' },
    { label: 'Show contradictions', href: '/reconciliation?type=CONTRADICTS', group: 'Filter' },
    { label: 'Show corroborations', href: '/reconciliation?type=CORROBORATES', group: 'Filter' },
    { label: 'Show uncertain facts', href: '/failures', group: 'Filter' },
    { label: 'Search facts…', href: '/query', group: 'Actions' },
];

function CommandPalette({ onClose }: { onClose: () => void }) {
    const [query, setQuery] = useState('');
    const [idx, setIdx] = useState(0);
    const navigate = useNavigate();

    const filtered = query
        ? COMMANDS.filter(c => c.label.toLowerCase().includes(query.toLowerCase()))
        : COMMANDS;

    const groups = [...new Set(filtered.map(c => c.group))];

    const go = useCallback((href: string) => {
        navigate(href);
        onClose();
    }, [navigate, onClose]);

    useEffect(() => {
        setIdx(0);
    }, [query]);

    useEffect(() => {
        const fn = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose();
            if (e.key === 'ArrowDown') setIdx(i => Math.min(i + 1, filtered.length - 1));
            if (e.key === 'ArrowUp') setIdx(i => Math.max(i - 1, 0));
            if (e.key === 'Enter' && filtered[idx]) go(filtered[idx].href);
        };
        window.addEventListener('keydown', fn);
        return () => window.removeEventListener('keydown', fn);
    }, [idx, filtered, go, onClose]);

    let globalIdx = 0;
    return (
        <div className="cmd-overlay" onClick={onClose}>
            <div className="cmd-palette" onClick={e => e.stopPropagation()}>
                <div className="cmd-input-row">
                    <span className="cmd-prompt">&gt;</span>
                    <input
                        className="cmd-input"
                        autoFocus
                        placeholder="Go to, filter, or act…"
                        value={query}
                        onChange={e => setQuery(e.target.value)}
                    />
                </div>
                <div className="cmd-results">
                    {groups.map(group => (
                        <div key={group}>
                            <div className="cmd-group-label">{group}</div>
                            {filtered.filter(c => c.group === group).map(cmd => {
                                const i = globalIdx++;
                                return (
                                    <button key={cmd.href} className={`cmd-item${i === idx ? ' highlighted' : ''}`}
                                        onClick={() => go(cmd.href)}
                                        onMouseEnter={() => setIdx(i)}>
                                        <span className="cmd-item-label">{cmd.label}</span>
                                        <span className="cmd-item-meta">{cmd.href}</span>
                                    </button>
                                );
                            })}
                        </div>
                    ))}
                    {filtered.length === 0 && (
                        <div className="empty-state" style={{ padding: '24px' }}>
                            <div className="empty-state-title">No results</div>
                        </div>
                    )}
                </div>
                <div className="cmd-footer">
                    <span><span className="cmd-kbd">↑↓</span> Navigate</span>
                    <span><span className="cmd-kbd">↵</span> Select</span>
                    <span><span className="cmd-kbd">Esc</span> Close</span>
                </div>
            </div>
        </div>
    );
}

/* ────────────────────────────────────────────────────────────
   Navigation Rail
   ──────────────────────────────────────────────────────────── */
function NavRail({ onCmd }: { onCmd: () => void }) {
    return (
        <nav className="nav-rail">
            <div className="nav-wordmark">
                <div className="name">FactLens</div>
                <span className="tagline">Evidence Intelligence</span>
            </div>

            <div className="nav-section">
                <span className="nav-section-label">Workspace</span>
                <NavLink to="/" end className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                    <span className="dot" /> Overview
                </NavLink>
                <NavLink to="/documents" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                    <span className="dot" /> Documents
                </NavLink>
                <NavLink to="/facts" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                    <span className="dot" /> Facts
                </NavLink>
                <NavLink to="/reconciliation" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                    <span className="dot" /> Reconciliation
                </NavLink>
                <NavLink to="/evidence" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                    <span className="dot" /> Evidence
                </NavLink>
            </div>

            <div className="nav-divider" />

            <div className="nav-section">
                <span className="nav-section-label">Inspect</span>
                <NavLink to="/query" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                    <span className="dot" /> Query
                </NavLink>
                <NavLink to="/failures" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                    <span className="dot" /> Uncertainty
                </NavLink>
            </div>

            <div className="nav-footer">
                <div className="nav-divider" style={{ margin: '0 0 8px 0' }} />
                <NavLink to="/health" className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
                    <span className="dot" /> System
                </NavLink>
                <button className="nav-search-btn" onClick={onCmd}>
                    Search
                    <span className="kbd">⌘K</span>
                </button>
            </div>
        </nav>
    );
}

/* ────────────────────────────────────────────────────────────
   Top Bar
   ──────────────────────────────────────────────────────────── */
const PAGE_TITLES: Record<string, string> = {
    '/': 'Overview',
    '/documents': 'Documents',
    '/facts': 'Facts',
    '/reconciliation': 'Reconciliation',
    '/evidence': 'Evidence',
    '/query': 'Query',
    '/failures': 'Uncertainty',
    '/health': 'System',
};

function TopBar({ onCmd }: { onCmd: () => void }) {
    const { pathname } = useLocation();
    const [meta, setMeta] = useState<{ docs: number; facts: number } | null>(null);

    useEffect(() => {
        getMetrics().then(r => setMeta({ docs: r.data.documents_total, facts: r.data.facts_total }))
            .catch(() => { });
    }, []);

    const title = PAGE_TITLES[pathname] || 'FactLens';

    return (
        <div className="topbar">
            <div className="topbar-title">{title}</div>
            <div className="topbar-meta">
                {meta && (
                    <>
                        <span>{meta.docs} DOCS</span>
                        <span>{meta.facts.toLocaleString()} FACTS</span>
                    </>
                )}
            </div>
            <div className="topbar-actions">
                <button className="btn btn-ghost" onClick={onCmd} style={{ fontSize: '0.7rem', gap: '6px' }}>
                    Search <span className="cmd-kbd">⌘K</span>
                </button>
            </div>
        </div>
    );
}

/* ────────────────────────────────────────────────────────────
   Root App
   ──────────────────────────────────────────────────────────── */
function AppInner() {
    const [cmdOpen, setCmdOpen] = useState(false);

    useEffect(() => {
        const fn = (e: KeyboardEvent) => {
            if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
                e.preventDefault();
                setCmdOpen(o => !o);
            }
        };
        window.addEventListener('keydown', fn);
        return () => window.removeEventListener('keydown', fn);
    }, []);

    return (
        <div className="app">
            <NavRail onCmd={() => setCmdOpen(true)} />
            <div className="content-area">
                <TopBar onCmd={() => setCmdOpen(true)} />
                <Routes>
                    <Route path="/" element={<Dashboard />} />
                    <Route path="/documents" element={<Documents />} />
                    <Route path="/facts" element={<FactsExplorer />} />
                    <Route path="/reconciliation" element={<Reconciliation />} />
                    <Route path="/evidence" element={<EvidenceViewer />} />
                    <Route path="/evidence/:factId" element={<EvidenceViewer />} />
                    <Route path="/query" element={<QueryPage />} />
                    <Route path="/failures" element={<Failures />} />
                    <Route path="/health" element={<Health />} />
                </Routes>
            </div>
            {cmdOpen && <CommandPalette onClose={() => setCmdOpen(false)} />}
        </div>
    );
}

export default function App() {
    return (
        <BrowserRouter>
            <AppInner />
        </BrowserRouter>
    );
}
