# FactLens

Cross-document fact reconciliation engine. Feed it multiple PDFs, it extracts typed claims, grounds each one back to the source text, and classifies relationships between documents: corroborates, contradicts, temporally distinct, scope mismatch, or uncertain.

## Why it exists

Most document intelligence tools stop at extraction and search. The harder problem is: when two documents make different numerical claims about the same thing, which one is right? Are they actually contradicting each other, or are they just reporting different time periods?

FactLens answers that question with a deterministic pipeline. No magic, no vibes.

## How it works

```
PDF
 -> layout-aware chunking (PyMuPDF)
 -> schema-constrained LLM extraction (subject / predicate / value / temporal scope / geo scope)
 -> evidence grounding validation   <-- hallucinations caught here, before DB write
 -> numeric + temporal normalization ($4.2B -> 4,200,000,000 USD | FY2024 -> {year: 2024})
 -> deterministic comparison engine (scope check -> unit check -> numeric check)
 -> LLM refinement only for cases the deterministic engine can't decide
 -> 10-step reasoning trace stored per reconciliation
```

The grounding step is the one that matters most. Every extracted fact must have a character-overlap match against the original chunk text. If it fails, the fact goes to the Uncertainty Register, not the trash. You can inspect every rejection and understand why.

## Stack

| Layer | What |
|---|---|
| PDF parsing | PyMuPDF |
| Extraction | Gemini (default), OpenAI, or Mock |
| Embeddings | all-MiniLM-L6-v2, runs locally |
| Vector store | PostgreSQL + pgvector |
| Backend | FastAPI, SQLAlchemy async |
| Frontend | React 18, TypeScript, Vite |

No hosted embedding API. No per-query cost. The model is behind an interface, swap it with one line in `.env`.

## Running

```bash
cp .env.example .env
# set GEMINI_API_KEY in .env
docker compose up --build -d
```

UI at `localhost:5173`, API docs at `localhost:8000/docs`.

For local dev without Docker:

```bash
# backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload

# frontend (separate terminal)
cd frontend
npm install && npm run dev
```

## Config

```bash
LLM_PROVIDER=gemini        # gemini | openai | mock
GEMINI_API_KEY=...
DATABASE_URL=postgresql://factlens:factlens@localhost:5432/factlens
EMBEDDING_MODEL=all-MiniLM-L6-v2
```

Only the key for the active provider is required at startup.

## Tests

```bash
cd backend && pytest tests/ -v
```

36 tests: numeric normalization, temporal parsing, contradiction engine, evidence grounding validator.

## Project layout

```
factlens/
  backend/
    app/
      api/            route handlers
      core/           config, logging
      db/             models, session
      extraction/     LLM provider abstraction + evidence validator
      normalization/  numeric, temporal, unit parsers
      reconciliation/ deterministic engine + reasoning trace
      retrieval/      hybrid vector + FTS search
    tests/
  frontend/
    src/
      pages/          8 views
      api/            typed API client
```

## Design decisions

**Deterministic engine before LLM.** Scope mismatches (wrong year, different region, different unit) are detectable with zero inference cost. LLM gets invoked only when the rules genuinely can't decide.

**Evidence grounding before persistence.** The extraction LLM sometimes invents text spans. The validator runs a character-overlap check against the original chunk. Failed groundings are logged and inspectable, not silently dropped.

**Local embeddings.** `all-MiniLM-L6-v2` runs CPU-only, costs nothing, and is abstracted behind a protocol. Swapping it out does not touch any pipeline code.
