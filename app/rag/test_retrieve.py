"""Retrieval stages: RRF (pure), fusion-only hybrid (pure), accession-scoped dense (DB)."""

from __future__ import annotations

import pytest

from app.rag.retrieve import hybrid, rrf


def test_rrf_ranks_ids_present_in_both_lists_first() -> None:
    fused = rrf([1, 2, 3], [3, 4, 5])
    assert fused[0][0] == 3
    assert {cid for cid, _ in fused} == {1, 2, 3, 4, 5}


def test_hybrid_without_rerank_returns_fused_slice_and_never_calls_reranker(monkeypatch) -> None:
    from app.rag import retrieve

    def _boom():
        raise AssertionError("reranker must not be loaded when rerank=False")

    monkeypatch.setattr(retrieve, "_reranker", _boom)
    texts = ["apple supplier concentration", "tesla ramp risk", "meta privacy regulation"]
    ids = [10, 20, 30]
    out = hybrid(None, "apple supplier", texts, ids, k=2, rerank=False)
    assert len(out) == 2
    assert out[0][0] == 10
    assert all(isinstance(s, float) for _, s in out)


def test_dense_accession_filter_scopes_pool() -> None:
    from sqlalchemy import select

    from app.db import SessionLocal, db_available
    from app.models import Chunk, Filing
    from app.rag.retrieve import dense

    if not db_available():
        pytest.skip("no database reachable")
    with SessionLocal() as db:
        acc = db.scalar(
            select(Filing.accession).join(Chunk, Chunk.filing_id == Filing.id).limit(1)
        )
        if acc is None:
            pytest.skip("no chunked filing in database")
        hits = dense(db, "risk factors", k=5, accession=acc)
        assert hits
        got = set(
            db.scalars(
                select(Filing.accession).join(Chunk, Chunk.filing_id == Filing.id)
                .where(Chunk.id.in_([cid for cid, _ in hits]))
            ).all()
        )
        assert got == {acc}
