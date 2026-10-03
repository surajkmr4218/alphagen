"""Verify the hand-labeled golden retrieval set against chunks in database.

Provenance: golden.json was labeled on 2026-06-22 against a frozen snapshot of
the latest-10-K chunks for AAPL, META, MSFT, NVDA and TSLA (Item 1A + Item 7),
ingested via scripts/ingest_golden.py. Each case's corpus_ids/corpus_texts are
that snapshot's real Chunk.id values; relevance was judged by reading every
passage. Each case is pinned to the filing `accession` it was labeled against and
labels resolve by content hash (see resolve_gold_ids), so re-ingesting cannot
silently invalidate them.

Judgments pass (2026-09-11): the original labels came from an 8-9 chunk shortlist
per query. After scoring against the full ~130-chunk pool, every unlabeled chunk in
any strategy's top-10 (237 candidates) was reviewed and 74 were added. That pass was
judged by Claude (Fable 5.1) in-session, NOT by the original human labeler — it is an
LLM-judge step. Every added id and its justification is in
app/eval/results/judgments-2026-09.md.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Chunk, Filing
from app.rag.chunk import text_sha

GOLDEN_PATH = Path(__file__).parent / "golden.json"


def candidate_pool(ticker: str, limit: int = 12) -> list[dict]:
    """Pull a candidate pool of chunks for one ticker, to hand-label into a golden case.

    Print these, read them, and copy the ids that answer your query into relevant_chunk_ids.
    """
    with SessionLocal() as db:
        rows = db.execute(
            select(Chunk.id, Chunk.section, Chunk.text)
            .where(Chunk.meta["ticker"].as_string() == ticker)
            .limit(limit)
        ).all()
    return [{"id": r.id, "section": r.section, "text": r.text[:240]} for r in rows]


def load() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text()) if GOLDEN_PATH.exists() else []


REQUIRED_KEYS = ("query", "ticker", "accession", "relevant_chunk_ids", "corpus_texts", "corpus_ids")


def validate(gold: list[dict]) -> list[str]:
    """Honesty checks: relevant ids must be a subset of the corpus; nothing empty."""
    problems: list[str] = []
    for i, case in enumerate(gold):
        corpus = set(case.get("corpus_ids", []))
        for key in REQUIRED_KEYS:
            if not case.get(key):
                problems.append(f"case {i}: missing/empty '{key}'")
        if len(case.get("corpus_texts", [])) != len(case.get("corpus_ids", [])):
            problems.append(f"case {i}: corpus_texts/corpus_ids length mismatch")
        rel = case.get("relevant_chunk_ids", [])
        stray = set(rel) - corpus
        if stray:
            problems.append(f"case {i}: relevant ids {stray} not in corpus_ids")
        if len(set(rel)) != len(rel):
            problems.append(f"case {i}: duplicate relevant ids")
        # Labels resolve by content hash: two labeled chunks with identical text would
        # collapse into one and resolve_gold_ids could not tell.
        by_id = dict(zip(case.get("corpus_ids", []), case.get("corpus_texts", [])))
        texts = [by_id.get(r) for r in rel]
        if len(set(texts)) != len(texts):
            problems.append(f"case {i}: two labeled chunks have identical text")
    return problems


def gold_texts(case: dict) -> dict[int, str]:
    """{labeled id -> chunk text} using the case's corpus_ids/corpus_texts alignment."""
    by_id = dict(zip(case["corpus_ids"], case["corpus_texts"]))
    return {rid: by_id[rid] for rid in case["relevant_chunk_ids"]}


def resolve_gold_ids(db: Session, case: dict) -> set[int]:
    """Map a case's labeled chunks to live Chunk.ids by content hash, scoped to the pinned filing.

    Labels are stored as text, so re-ingesting (which renumbers rows) cannot silently break
    them. Raises ValueError naming the query if any label is missing or ambiguous — the eval
    must never report a green number against unresolved labels.
    """
    wanted = {text_sha(t): rid for rid, t in gold_texts(case).items()}
    rows = db.execute(
        select(Chunk.id, Chunk.text_sha)
        .join(Filing, Chunk.filing_id == Filing.id)
        .where(Filing.accession == case["accession"], Chunk.text_sha.in_(list(wanted)))
    ).all()
    found: dict[str, list[int]] = {}
    for cid, sha in rows:
        found.setdefault(sha, []).append(cid)
    missing = [wanted[sha] for sha in wanted if sha not in found]
    ambiguous = {wanted[sha]: ids for sha, ids in found.items() if len(ids) > 1}
    if missing or ambiguous:
        raise ValueError(
            f"golden labels do not resolve for {case['query']!r} "
            f"(accession {case['accession']}): missing={missing} ambiguous={ambiguous}. "
            "Re-ingest the pinned filing with scripts/ingest_golden.py or re-label; "
            "do not trust metrics until this passes."
        )
    return {ids[0] for ids in found.values()}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:  # inspect a candidate pool: python -m app.eval.golden AAPL
        for c in candidate_pool(sys.argv[1]):
            print(f"[{c['id']}] ({c['section']}) {c['text']}")
    else:  # validate the labeled file
        issues = validate(load())
        print("golden.json OK" if not issues else "\n".join(issues))
