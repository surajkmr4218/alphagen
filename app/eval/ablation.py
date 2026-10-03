"""Retrieval-stage ablation: score each stage of the production retriever on the golden set.

Every strategy below calls the real function from `app.rag.retrieve` over the FULL pool of the
pinned filing (~130 chunks: Item 1A + Item 7), so the numbers measure what production does,
not a re-implementation. Labels resolve by content hash (`golden.resolve_gold_ids`).

    uv run python -m app.eval.ablation             # score all strategies, write results JSON
    uv run python -m app.eval.ablation --unjudged  # list unlabeled top-k chunks for review
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.eval.golden import load, resolve_gold_ids
from app.eval.metrics import mrr, precision_at_k, precision_ceiling, r_precision, recall_at_k
from app.models import Chunk, Filing
from app.rag.retrieve import _RERANKER_NAME, _bm25_rank, dense, hybrid

RESULTS_PATH = Path(__file__).parent / "results" / "latest.json"
K = 10            # cutoff for recall@10 and precision@5
CANDIDATE_K = 30  # retrieval depth: must exceed the largest gold set so R-precision is exact

# strategy -> fn(db, query, corpus_ids, corpus_texts, accession, k) -> ranked chunk ids
Strategy = Callable[[Session, str, list[int], list[str], str, int], list[int]]


def _dense(db, q, ids, texts, acc, k):
    return [cid for cid, _ in dense(db, q, k=k, accession=acc)]


def _bm25(db, q, ids, texts, acc, k):
    return _bm25_rank(q, texts, ids, k=k)


def _rrf(db, q, ids, texts, acc, k):
    return [
        cid
        for cid, _ in hybrid(
            db, q, texts, ids, k=k, accession=acc, candidate_k=CANDIDATE_K, rerank=False
        )
    ]


def _hybrid(db, q, ids, texts, acc, k):
    return [
        cid 
        for cid, _ in hybrid(
            db, q, texts, ids, k=k, accession=acc, candidate_k=CANDIDATE_K, rerank=True
        )
    ]


STRATEGIES: dict[str, Strategy] = {
    "dense": _dense,    # pgvector cosine only
    "bm25": _bm25,      # sparse lexical only
    "rrf": _rrf,        # dense + bm25 fused by reciprocal rank fusion, no rerank
    "hybrid": _hybrid,  # rrf + cross-encoder rerank == production path
}


# --- pure scoring --------------------------------------------------------------------------

Ranking = tuple[list[int], set[int], str]  # (ranked ids, relevant ids, ticker)


def _score_group(rankings: list[Ranking], k: int) -> dict:
    n = len(rankings)
    return {
        "n_queries": n,
        "r_precision": sum(r_precision(r, rel) for r, rel, _ in rankings) / n,
        "recall_at_k": sum(recall_at_k(r, rel, k) for r, rel, _ in rankings) / n,
        "mrr": sum(mrr(r, rel) for r, rel, _ in rankings) / n,
        "precision_at_5": sum(precision_at_k(r, rel, 5) for r, rel, _ in rankings) / n,
        "precision_at_5_ceiling": precision_ceiling([len(rel) for _, rel, _ in rankings], 5),
    }


def score_rankings(rankings: list[Ranking], k: int = K) -> dict:
    """Aggregate metrics over all queries plus per-ticker slices (n=3 each: directional only)."""
    out = _score_group(rankings, k)
    tickers = sorted({t for _, _, t in rankings})
    out["per_ticker"] = {
        t: _score_group([r for r in rankings if r[2] == t], k) for t in tickers
    }
    return out


def unjudged_ids(by_strategy: dict[str, list[int]], relevant: set[int], k: int) -> set[int]:
    """Ids inside any strategy's top-k that carry no label — candidates for a judgment pass."""
    seen: set[int] = set()
    for ranked in by_strategy.values():
        seen |= set(ranked[:k])
    return seen - relevant


# --- DB-backed runner -----------------------------------------------------------------------


def load_corpus(db: Session, accession: str) -> tuple[list[int], list[str]]:
    """All chunks of one filing — the BM25 corpus and the reranker's passage source."""
    rows = db.execute(
        select(Chunk.id, Chunk.text)
        .join(Filing, Chunk.filing_id == Filing.id)
        .where(Filing.accession == accession)
        .order_by(Chunk.id)
    ).all()
    return [r.id for r in rows], [r.text for r in rows]


def rank_all(
    db: Session,
    gold: list[dict],
    strategies: dict[str, Strategy] | None = None,
    k: int = CANDIDATE_K,
) -> dict[str, list[Ranking]]:
    """{strategy -> [(ranked ids, relevant ids, ticker)] in golden order}.

    Ranks to depth `k` = CANDIDATE_K (30), deeper than the K=10 metric cutoff, so that
    R-precision sees at least R ids for every query (largest gold set is 18). Truncating at 10
    would silently turn precision-at-R into precision-at-10 for those queries.
    """
    strategies = strategies or STRATEGIES
    largest = max(len(c["relevant_chunk_ids"]) for c in gold)
    if k < largest:
        raise ValueError(f"retrieval depth {k} < largest gold set {largest}; R-precision inexact")
    out: dict[str, list[Ranking]] = {name: [] for name in strategies}
    corpora: dict[str, tuple[list[int], list[str]]] = {}
    for case in gold:
        acc = case["accession"]
        if acc not in corpora:
            corpora[acc] = load_corpus(db, acc)
        ids, texts = corpora[acc]
        relevant = resolve_gold_ids(db, case)
        for name, fn in strategies.items():
            out[name].append((fn(db, case["query"], ids, texts, acc, k), relevant, case["ticker"]))
    return out


def run_ablation(db: Session, gold: list[dict], k: int = K) -> dict[str, dict]:
    return {name: score_rankings(rs, k) for name, rs in rank_all(db, gold).items()}


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "unknown"


def markdown_table(results: dict[str, dict]) -> str:
    lines = [
        "| strategy | R-precision | recall@10 | MRR | precision@5 (ceiling) |",
        "|---|---|---|---|---|",
    ]
    for name, s in results.items():
        lines.append(
            f"| {name} | {s['r_precision']:.3f} | {s['recall_at_k']:.3f} | {s['mrr']:.3f} "
            f"| {s['precision_at_5']:.3f} ({s['precision_at_5_ceiling']:.2f}) |"
        )
    return "\n".join(lines)


def _print_unjudged(db: Session, gold: list[dict], k: int) -> None:
    ranked = rank_all(db, gold)
    for i, case in enumerate(gold):
        by_strategy = {name: ranked[name][i][0] for name in ranked}
        relevant = resolve_gold_ids(db, case)
        cands = sorted(unjudged_ids(by_strategy, relevant, k))
        print(f"\n=== case {i} [{case['ticker']}] {case['query']}")
        print(f"    labeled: {sorted(relevant)}  unjudged in any top-{k}: {cands}")
        rows = db.execute(
            select(Chunk.id, Chunk.section, Chunk.text).where(Chunk.id.in_(cands))
        ).all()
        for cid, section, text in sorted(rows):
            hits = [n for n, r in by_strategy.items() if cid in r[:k]]
            print(f"\n--- chunk {cid} ({section}) in: {','.join(hits)}\n{text}")


def main(argv: list[str]) -> None:
    from app.db import SessionLocal
    from app.rag.embed import MODEL_NAME

    gold = load()
    with SessionLocal() as db:
        if "--unjudged" in argv:
            _print_unjudged(db, gold, K)
            return
        results = run_ablation(db, gold, K)
    payload = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "embed_model": MODEL_NAME,
        "reranker": _RERANKER_NAME,
        "k": K,
        "candidate_k": CANDIDATE_K,
        "n_queries": len(gold),
        "results": results,
    }
    RESULTS_PATH.parent.mkdir(exist_ok=True)
    RESULTS_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(markdown_table(results))
    print(f"\nwrote {RESULTS_PATH}")


if __name__ == "__main__":
    main(sys.argv[1:])
