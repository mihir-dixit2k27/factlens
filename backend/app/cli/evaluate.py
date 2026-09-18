"""
evaluate.py - RAG pipeline evaluation CLI.

Generates questions from TRUSTED facts in the DB, runs them through
the RAG Q&A chain, and measures:
  - Retrieval recall@5: was the source fact in the top-5 retrieved?
  - Answer faithfulness: does the answer contain the expected value?
  - Unsupported-answer rate: did the LLM answer with something the
    retrieved context does not support?

Usage:
    python -m app.cli.evaluate
    python -m app.cli.evaluate --limit 20 --output results.json
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class EvalCase:
    fact_id: str
    predicate: str
    expected_value: str
    question: str
    subject: Optional[str] = None


@dataclass
class EvalResult:
    fact_id: str
    question: str
    expected_value: str
    answer: str
    retrieved_fact_ids: list[str] = field(default_factory=list)
    retrieval_hit: bool = False
    answer_faithful: bool = False
    unsupported: bool = False


def _make_question(predicate: str, subject: Optional[str]) -> str:
    """Turn a fact predicate into a natural language question."""
    pred = predicate.strip().lower()
    if subject:
        return f"What is the {pred} for {subject}?"
    return f"What is the reported {pred}?"


def _check_faithfulness(expected: str, answer: str) -> bool:
    """Check if the expected value (or a close variant) appears in the answer."""
    exp = expected.lower().strip()
    ans = answer.lower()

    # Direct substring match
    if exp in ans:
        return True

    # Strip common units/symbols and try again
    cleaned = re.sub(r"[,$%bmkt]", "", exp).strip()
    if cleaned and cleaned in re.sub(r"[,$%bmkt]", "", ans):
        return True

    # Numeric extraction - check if the leading number matches
    nums_expected = re.findall(r"\d+\.?\d*", exp)
    nums_answer = re.findall(r"\d+\.?\d*", ans)
    if nums_expected and any(n in nums_answer for n in nums_expected):
        return True

    return False


def _check_unsupported(context: str, answer: str) -> bool:
    """
    Heuristic: answer is unsupported if it contains numeric values not in context.
    This catches cases where the LLM hallucinated a number not in the retrieved facts.
    """
    if "do not contain" in answer.lower() or "not enough information" in answer.lower():
        return False  # LLM correctly said it cannot answer

    answer_nums = set(re.findall(r"\d+\.?\d*", answer))
    context_nums = set(re.findall(r"\d+\.?\d*", context))
    hallucinated = answer_nums - context_nums
    # Allow minor differences (percentages, small helpers like "1", "2")
    significant = {n for n in hallucinated if float(n) > 10}
    return len(significant) > 0


async def _run_evaluation(limit: int) -> list[EvalResult]:
    # Lazy imports so this can be run standalone without polluting startup
    from sqlalchemy import select
    from app.db.session import AsyncSessionLocal
    from app.db.models import Fact, ExtractionStatus, Entity
    from app.embeddings.provider import SentenceTransformerProvider
    from app.retrieval.hybrid import hybrid_fact_search
    from app.core.config import get_settings
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.output_parsers import StrOutputParser

    cfg = get_settings()

    print(f"Connecting to DB: {cfg.database_url[:40]}...")

    RAG_PROMPT = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a fact analysis assistant. Answer using ONLY the numbered facts below.\n"
            "If the facts do not contain the answer, say: "
            "'The retrieved facts do not contain sufficient information to answer this question.'\n\n"
            "Facts:\n{context}"
        )),
        ("human", "{query}"),
    ])

    llm = ChatGoogleGenerativeAI(
        model="gemini-3.6-flash",
        temperature=0.1,
        google_api_key=cfg.gemini_api_key,
    )
    rag_chain = RAG_PROMPT | llm | StrOutputParser()

    emb_provider = SentenceTransformerProvider()

    results: list[EvalResult] = []

    async with AsyncSessionLocal() as session:
        # Pull TRUSTED facts with a non-null predicate and object_text
        stmt = (
            select(Fact)
            .where(Fact.extraction_status == ExtractionStatus.TRUSTED)
            .where(Fact.predicate.isnot(None))
            .where(Fact.object_text.isnot(None))
            .limit(limit)
        )
        rows = list((await session.execute(stmt)).scalars())
        if not rows:
            print("No TRUSTED facts in DB. Process documents first.")
            return []

        print(f"Evaluating {len(rows)} facts...\n")

        for i, fact in enumerate(rows, 1):
            # Resolve subject name
            subject_name: Optional[str] = None
            if fact.subject_entity_id:
                ent = (await session.execute(
                    select(Entity).where(Entity.id == fact.subject_entity_id)
                )).scalar_one_or_none()
                if ent:
                    subject_name = ent.canonical_name

            question = _make_question(fact.predicate, subject_name)
            expected = fact.object_text.strip()

            # Retrieval
            ranked = await hybrid_fact_search(
                session=session,
                provider=emb_provider,
                query=question,
                limit=5,
            )
            retrieved_ids = [str(r.fact.id) for r in ranked]
            retrieval_hit = str(fact.id) in retrieved_ids

            # Format context
            context_lines = []
            for j, r in enumerate(ranked, 1):
                f = r.fact
                line = f"[{j}] {f.predicate}: {f.object_text}"
                if f.temporal_scope and f.temporal_scope.get("label"):
                    line += f" ({f.temporal_scope['label']})"
                context_lines.append(line)
            context = "\n".join(context_lines)

            # LLM answer
            try:
                answer = await rag_chain.ainvoke({"context": context, "query": question})
            except Exception as exc:
                answer = f"[LLM error: {exc}]"

            faithful = _check_faithfulness(expected, answer)
            unsupported = _check_unsupported(context, answer)

            result = EvalResult(
                fact_id=str(fact.id),
                question=question,
                expected_value=expected,
                answer=answer[:300],
                retrieved_fact_ids=retrieved_ids,
                retrieval_hit=retrieval_hit,
                answer_faithful=faithful,
                unsupported=unsupported,
            )
            results.append(result)

            status = (
                "HIT" if retrieval_hit else "MISS",
                "FAITHFUL" if faithful else "WRONG",
                "HALLUCINATION" if unsupported else "ok",
            )
            print(f"[{i:02d}/{len(rows)}] {question[:60]}")
            print(f"       expected={expected[:40]}  retrieval={status[0]}  "
                  f"faithfulness={status[1]}  unsupported={status[2]}\n")

    return results


def _print_summary(results: list[EvalResult]) -> None:
    n = len(results)
    if n == 0:
        return
    recall = sum(r.retrieval_hit for r in results) / n
    faithfulness = sum(r.answer_faithful for r in results) / n
    unsupported_rate = sum(r.unsupported for r in results) / n

    print("=" * 50)
    print("Evaluation Results")
    print("=" * 50)
    print(f"Facts evaluated:        {n}")
    print(f"Retrieval recall@5:     {recall:.2f}")
    print(f"Answer faithfulness:    {faithfulness:.2f}")
    print(f"Unsupported answers:    {unsupported_rate:.2f}")
    print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(description="FactLens RAG evaluation")
    parser.add_argument("--limit", type=int, default=30, help="Max facts to evaluate (default: 30)")
    parser.add_argument("--output", type=str, default=None, help="Save JSON results to file")
    args = parser.parse_args()

    results = asyncio.run(_run_evaluation(limit=args.limit))
    _print_summary(results)

    if args.output:
        with open(args.output, "w") as f:
            json.dump([asdict(r) for r in results], f, indent=2)
        print(f"\nDetailed results written to {args.output}")


if __name__ == "__main__":
    main()
