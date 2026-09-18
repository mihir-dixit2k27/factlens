# FactLens

Cross-document fact reconciliation engine. Upload multiple PDFs, it extracts structured claims from each, grounds every claim to the source text, and tells you how documents relate: corroborates, contradicts, temporally distinct, scope mismatch, or uncertain.

---

## Setup and Run Instructions

**Requirements:** Docker and Docker Compose.

```bash
git clone https://github.com/mihir-dixit2k27/factlens.git
cd factlens
cp .env.example .env
```

Edit `.env`:

```
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

```bash
docker compose up --build -d
```

- UI: http://localhost:5173
- API docs: http://localhost:8000/docs

Upload PDFs on the Documents page, click Process. Facts and reconciliation results appear once the pipeline finishes.

---

## Video Demo

https://www.loom.com/share/ab2d13051ea2416eb2d7af1f69730783

---

## Approach

The core problem is not extraction, it is comparison. Two documents can report different numbers for the same thing and the system needs to decide if that is a contradiction, a time difference, a scope difference, or genuine agreement despite different wording.

**Pipeline stages:**

1. **Ingest** -- PyMuPDF parses PDFs with layout awareness, adaptive chunking preserves paragraph boundaries
2. **Extract** -- LangChain orchestrates a `ChatPromptTemplate | ChatGoogleGenerativeAI | JsonOutputParser` chain; Gemini returns structured facts (subject, predicate, value, temporal scope, geographic scope, object type); Pydantic validates the schema and coerces loose types before any DB write
3. **Ground** -- character-overlap matching checks every fact against its source chunk; hallucinated spans are rejected here and logged to the Uncertainty Register with a rejection reason
4. **Normalize** -- numeric values, currencies, units, and time periods are reduced to comparable forms (`$4.2B` becomes `4200000000 USD`, `FY2024` becomes `{year: 2024}`)
5. **Embed** -- `all-MiniLM-L6-v2` runs locally via HuggingFace sentence-transformers, vectors stored in PostgreSQL via pgvector
6. **Reconcile** -- deterministic engine checks scope, unit, and numeric values first; LangChain + Gemini is only invoked when rules cannot decide; a 10-step reasoning trace is stored per result
7. **Q&A** -- `/api/query` runs hybrid retrieval (pgvector cosine + BM25 lexical), formats the top facts as grounded context, and feeds them to a LangChain RAG chain that synthesizes a cited answer

**Key design decisions:**

- Deterministic engine before LLM keeps latency predictable and results auditable
- Evidence grounding before DB write means zero hallucinated facts reach the output layer (they go to the Uncertainty Register instead)
- LangChain as the orchestration layer means the LLM provider is swappable without pipeline changes; the `LLMProvider` Protocol interface is implemented by `GeminiProvider`, `OpenAIProvider`, and `MockProvider`
- Local embeddings eliminate per-query API cost

**Tech stack:** Python, FastAPI, LangChain, Gemini (gemini-3.6-flash), HuggingFace (all-MiniLM-L6-v2), pgvector, PostgreSQL, Pydantic, PyMuPDF, React, Docker

---

## Evaluation

The pipeline ships with an evaluation CLI. It auto-generates questions from the extracted facts in the database, runs them through the full RAG pipeline, and measures:

- Retrieval recall@5 (was the source fact in the top-5 results?)
- Answer faithfulness (does the answer contain the expected value?)
- Unsupported-answer rate (did the model answer with numbers not in the retrieved context?)

```bash
docker compose exec api python3 -m app.cli.evaluate --limit 30
```

---

## Limitations and Next Steps

**What does not work yet:**

- Reconciliation compares facts within the same predicate group; cross-predicate relationships (e.g. linking revenue to market cap) are not detected
- Entity resolution uses token-overlap fuzzy matching, which can miss abbreviations or acronyms that do not share tokens
- Frontend does not support side-by-side PDF page viewing; evidence navigation goes to the fact panel, not the raw PDF
- Processing is single-threaded per document; large PDFs (50+ pages) will be slow

**Would build next:**

- Cross-predicate relationship linking using embedding similarity
- Named entity resolution using a dedicated model
- WebSocket-based real-time pipeline status in the UI
- Re-processing endpoint that does not require a DB stage reset

---

## Additional Notes

The project does not hard-code any domain, entity, or document structure. It works on any PDF.

The Uncertainty Register (Failures page in the UI) is intentional design, not a debug view. Every grounding failure is stored with its rejection reason and is inspectable. This makes the system's confidence calibration visible and auditable.

The `.env.example` file shows all required variables. No credentials are committed to the repository.
