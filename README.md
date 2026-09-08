# FactLens

Cross-document fact reconciliation engine. Give it multiple PDFs, it extracts structured claims from each one, grounds every claim back to the source text, and tells you how documents relate: corroborates, contradicts, temporally distinct, scope mismatch, or uncertain.

---

## Setup and Run Instructions

**Requirements:** Docker and Docker Compose installed.

```bash
git clone https://github.com/mihir-dixit2k27/factlens.git
cd factlens
cp .env.example .env
```

Open `.env` and set your Gemini API key:

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

Then start everything:

```bash
docker compose up --build -d
```

- UI: http://localhost:5173
- API docs: http://localhost:8000/docs
- Postgres: localhost:5433

To process documents: go to the Documents page, upload one or more PDFs, and click Process on each one. Facts and reconciliation results appear under the Facts and Reconciliation pages once the pipeline finishes.

---

## Video Demo

https://www.loom.com/share/ab2d13051ea2416eb2d7af1f69730783

The video covers: uploading PDFs, watching the processing pipeline, reviewing extracted facts with confidence scores, and walking through the reconciliation workspace including a contradiction and a temporal distinction case.

---

## Approach

The core problem is not extraction, it is comparison. Two documents can report different numbers for the same thing, and the system needs to say whether that is a contradiction, a time period difference, a scope difference, or something else entirely.

The pipeline works in stages:

1. **Ingest** -- layout-aware PDF parsing with PyMuPDF, adaptive chunking
2. **Extract** -- Gemini returns structured facts (subject, predicate, value, temporal scope, geographic scope, object type) as free-form JSON parsed against a Pydantic schema
3. **Ground** -- every fact must have a character-overlap match against the original chunk text before it is persisted; hallucinated spans are caught here and logged to the Uncertainty Register
4. **Normalize** -- numeric values, currencies, units, and time periods are reduced to comparable forms (`$4.2B` becomes `4200000000 USD`, `FY2024` becomes `{year: 2024}`)
5. **Reconcile** -- a deterministic engine runs scope, unit, and numeric checks first; LLM is only invoked when the rules cannot decide
6. **Store** -- a 10-step reasoning trace is saved per reconciliation result

Embeddings use `all-MiniLM-L6-v2` running locally (no API cost). Vectors are stored in PostgreSQL via pgvector. The LLM provider is behind a Protocol interface so Gemini, OpenAI, or a local model can be swapped without touching pipeline code.

Key trade-offs:
- Deterministic engine before LLM keeps latency low and results auditable
- Evidence grounding validation before DB write means zero hallucinated facts in the output (they go to Uncertainty instead)
- Local embeddings eliminate per-query cost at the price of cold-start time on first run

AI tools used: Gemini for structured fact extraction and relationship classification.

---

## Limitations and Next Steps

**What does not work yet:**

- The reconciliation engine compares facts within the same predicate group; cross-predicate relationships (e.g. linking revenue to market cap) are not detected
- Entity resolution uses token-overlap fuzzy matching, which can miss abbreviations or acronyms that do not share tokens
- The frontend does not yet support side-by-side document page viewing; evidence navigation goes to the fact panel but not the raw PDF page
- Processing is single-threaded per document; large PDFs (50+ pages) will be slow

**Would build next:**

- Cross-predicate relationship linking using embedding similarity
- Named entity resolution using a model instead of string matching
- Streaming pipeline status via WebSocket so the UI updates in real time
- A re-processing API endpoint that does not require a DB stage reset to force re-extraction

---

## Additional Notes

The project does not hard-code any domain, entity, or document structure. It generalizes to arbitrary PDFs.

The Uncertainty Register (Failures page in the UI) is intentional design, not a debug view. Every grounding failure is stored with its rejection reason and is inspectable. This is important for the evaluation use case because it makes the system's confidence calibration visible.

The `.env.example` file shows all required variables. No credentials are committed to the repository.
