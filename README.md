# FactLens

Cross-document fact reconciliation engine. Give it multiple PDFs — it extracts claims, grounds each one back to the source text, and tells you when two documents agree, contradict, or are just talking about different time periods.

## What it actually does

Most document intelligence tools stop at extraction. FactLens goes further:

1. **Ingest** — layout-aware PDF parsing (PyMuPDF), adaptive chunking
2. **Extract** — schema-constrained LLM extracts typed facts (subject, predicate, value, temporal scope, geographic scope)
3. **Ground** — every fact must trace back to an exact text span before it's persisted. Hallucinated facts are caught here
4. **Normalize** — numeric values, currencies, time periods, and units are all reduced to comparable forms (e.g. `$4.2B` → `4200000000 USD`)
5. **Reconcile** — deterministic comparison engine checks temporal scope, geographic scope, and unit compatibility before any LLM is called
6. **Expose** — a typed API with hybrid vector + full-text retrieval

The reasoning trace for every reconciliation is stored as 10 discrete steps so you can see exactly why two facts were classified as contradicting vs. temporally distinct.

## Stack

| Layer | Technology |
|-------|-----------|
| PDF parsing | PyMuPDF |
| Extraction LLM | Gemini (default) · OpenAI · Mock |
| Embeddings | all-MiniLM-L6-v2 (local, no API cost) |
| Vector store | PostgreSQL + pgvector |
| Backend | FastAPI + SQLAlchemy async |
| Frontend | React 18 + TypeScript + Vite |

## Running it

### With Docker (recommended)

```bash
cp .env.example .env
# Add your GEMINI_API_KEY to .env
docker compose up --build -d
```

- UI → http://localhost:5173  
- API docs → http://localhost:8000/docs  
- Postgres available on host port 5433

### Local development

```bash
# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# Frontend
cd frontend
npm install && npm run dev
```

## Configuration

Copy `.env.example` → `.env` and fill in:

```
LLM_PROVIDER=gemini          # gemini | openai | mock
GEMINI_API_KEY=...
DATABASE_URL=postgresql://factlens:factlens@localhost:5432/factlens
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

Only the key for the selected provider is required.

## Testing

```bash
cd backend
pytest tests/ -v
```

36 tests covering normalization, temporal parsing, the contradiction engine, and evidence grounding validation.

## Design notes

**Why deterministic reconciliation first?**  
LLMs are non-deterministic and expensive. Scope mismatches (wrong year, different region) can be detected with zero inference cost. LLM is invoked only when the deterministic checks genuinely can't decide.

**Why evidence grounding validation?**  
Without it, LLMs hallucinate evidence spans. Every fact stored in FactLens has a character-overlap check against the original chunk text. Failed groundings go to the Uncertainty Register, not the trash — they're inspectable.

**Why local embeddings?**  
`all-MiniLM-L6-v2` runs CPU-only, costs nothing per query, and is abstracted behind an interface — swappable without touching any pipeline code.

## Project layout

```
factlens/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routes
│   │   ├── core/         # Config, logging
│   │   ├── db/           # SQLAlchemy models, session
│   │   ├── extraction/   # LLM provider abstraction
│   │   ├── normalization/# Numeric, temporal, unit parsers
│   │   ├── reconciliation/# Contradiction engine + trace
│   │   └── retrieval/    # Hybrid vector + FTS search
│   └── tests/
└── frontend/
    └── src/
        ├── pages/        # 8 views
        └── api/          # Typed API client
```

## CI

GitHub Actions runs on every push: type-check, lint (ruff), and the full test suite.
