from __future__ import annotations

from collections import defaultdict
from functools import lru_cache

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.rag.embed import embed

_RERANKER_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"


@lru_cache(maxsize=1)
def _reranker():
    # Lazy + cached: the model (and its first-use download) is paid once per process.
    from sentence_transformers import CrossEncoder

    return CrossEncoder(_RERANKER_NAME)


def dense(db: Session, query: str, k: int = 30, ticker: str | None = None) -> list[tuple[int, str]]:
    """Dense semantic retrieval via pgvector cosine distance.

    Embeds the query, then orders chunks by the `<=>` cosine-distance operator (smaller = closer).
    The metadata filter is applied IN SQL so we never pull non-matching rows: when `ticker` is None
    the predicate is a no-op, otherwise it restricts to chunks whose meta JSON ticker matches.
    """
    qv = embed([query])[0]  # 384-dim, already normalized (see embed.py)
    rows = db.execute(
        text(
            """
            SELECT id, text
            FROM chunks
            -- Cast :ticker to text: it appears first in `IS NULL`, where Postgres can't infer the
            -- param type from psycopg's binary protocol and errors without an explicit type.
            WHERE ((:ticker)::text IS NULL OR meta->>'ticker' = (:ticker)::text)
            -- Cast :qv to vector: psycopg sends str(qv) as `text`, and pgvector's `<=>` is only
            -- defined as vector<=>vector, so without the cast Postgres throws.
            ORDER BY embedding <=> (:qv)::vector
            LIMIT :k
            """
        ),
        {"ticker": ticker, "qv": str(qv), "k": k},
    ).fetchall()
    return [(r.id, r.text) for r in rows]


def _bm25_rank(
    query: str, corpus_texts: list[str], corpus_ids: list[int], k: int = 30
) -> list[int]:
    """Sparse lexical ranking over an in-memory corpus using BM25Okapi.

    NOTE: rank_bm25 rebuilds the index per call from the passed corpus. That's fine for the eval
    golden set and a single ticker's evidence bundle. In production this becomes a Postgres tsvector
    full-text query so we don't re-tokenize the whole corpus on every request.
    """
    from rank_bm25 import BM25Okapi

    tokenized = [t.lower().split() for t in corpus_texts]
    bm25 = BM25Okapi(tokenized)
    scores = bm25.get_scores(query.lower().split())
    ranked = sorted(zip(corpus_ids, scores), key=lambda kv: kv[1], reverse=True)
    return [doc_id for doc_id, _ in ranked[:k]]


def rrf(*rankings: list[int], k: int = 60) -> list[tuple[int, float]]:
    """Reciprocal Rank Fusion.

    Each argument is a ranked list of ids (best first). An id's fused score is the sum over the
    lists it appears in of 1 / (k + rank). `k` (the standard 60) damps the influence of any single
    list's top spot so one retriever can't dominate. Returns ids sorted by fused score, descending.
    We accept *rankings for flexibility (e.g. a third sparse signal); today it's dense + BM25.
    """
    scores: dict[int, float] = defaultdict(float)
    for ranking in rankings:
        for rank, doc_id in enumerate(ranking):
            scores[doc_id] += 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda kv: kv[1], reverse=True)


def hybrid(
    db: Session | None,
    query: str,
    corpus_texts: list[str],
    corpus_ids: list[int],
    k: int = 8,
    ticker: str | None = None,
    candidate_k: int = 30,
) -> list[tuple[int, float]]:
    """Full retrieval path: dense + BM25 -> RRF fuse -> cross-encoder rerank.

    `corpus_texts`/`corpus_ids` are the candidate pool (one ticker's chunks) for BM25 (and the 
    source of passage text for the reranker). `db` is the pgvector session for dense; pass None
    to run sparse-only (used by theeval harness when there is no live DB). Returns the top-`k` 
    (chunk_id, rerank_score) pairs.
    """
    id_to_text = dict(zip(corpus_ids, corpus_texts))

    # Stage 1 — two complementary candidate lists.
    dense_ids: list[int] = []
    if db is not None:
        dense_hits = dense(db, query, k=candidate_k, ticker=ticker)
        dense_ids = [cid for cid, _ in dense_hits]
        # Keep dense passages available to the reranker even if absent from the BM25 corpus.
        for cid, txt in dense_hits:
            id_to_text.setdefault(cid, txt)
    sparse_ids = _bm25_rank(query, corpus_texts, corpus_ids, k=candidate_k)

    # Stage 2 — fuse rankings (RRF). Scale-free, so dense distance vs BM25 score never clash.
    fused = rrf(dense_ids, sparse_ids)
    candidates = [cid for cid, _ in fused[:candidate_k]]
    if not candidates:
        return []

    # Stage 3 — cross-encoder rerank for precision on the short candidate list only.
    pairs = [(query, id_to_text.get(cid, "")) for cid in candidates]
    rerank_scores = _reranker().predict(pairs)
    reranked = sorted(zip(candidates, rerank_scores), key=lambda kv: kv[1], reverse=True)
    return [(cid, float(score)) for cid, score in reranked[:k]]