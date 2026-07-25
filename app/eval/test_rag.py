from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.eval.ab_embeddings import _dense_rank  # reuse the DB-free dense ranker

GOLD = json.loads((Path(__file__).parent / "golden.json").read_text())
DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"

# --- pure metric functions (no DB, no model) --------------------------------------------------


def precision_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    """Fraction of the top-k retrieved ids that are relevant."""
    top = retrieved[:k]
    if not top:
        return 0.0
    return sum(1 for cid in top if cid in relevant) / len(top)


def recall(retrieved: list[int], relevant: set[int]) -> float:
    """Fraction of relevant ids that were retrieved (anywhere in the list)."""
    if not relevant:
        return 1.0
    return sum(1 for cid in relevant if cid in retrieved) / len(relevant)


def _rank_case(case: dict) -> list[int]:
    return _dense_rank(DEFAULT_MODEL, case["query"], case["corpus_texts"], case["corpus_ids"])


# --- retrieval quality ------------------------------------------------------------------------

PRECISION_AT_5_FLOOR = 0.4  # RATCHET: raise this as retrieval improves.


@pytest.mark.parametrize("case", GOLD, ids=[c["query"][:40] for c in GOLD])
def test_precision_at_5(case: dict) -> None:
    retrieved = _rank_case(case)
    p = precision_at_k(retrieved, set(case["relevant_chunk_ids"]), k=5)
    assert p >= PRECISION_AT_5_FLOOR, (
        f"precision@5 {p:.3f} < {PRECISION_AT_5_FLOOR} for: {case['query']}"
    )


def test_mean_recall() -> None:
    recalls = [recall(_rank_case(c), set(c["relevant_chunk_ids"])) for c in GOLD]
    mean_recall = sum(recalls) / len(recalls)
    assert mean_recall >= 0.5, f"mean recall {mean_recall:.3f} < 0.5"


# --- citation accuracy: every cited span must resolve to a real corpus chunk ------------------


def test_citations() -> None:
    """A citation is valid only if its chunk id exists in that case's corpus.

    Stand-in for the agent's behavior (Week 4): hypotheses cite chunk ids, and a cited span that
    doesn't resolve is a broken citation. Here we assert the labeled relevant ids themselves all
    resolve — the invariant the agent must also satisfy.
    """
    unresolved = 0
    total = 0
    for case in GOLD:
        corpus = set(case["corpus_ids"])
        for cid in case["relevant_chunk_ids"]:
            total += 1
            if cid not in corpus:
                unresolved += 1
    accuracy = 1.0 - (unresolved / total if total else 0.0)
    assert accuracy == 1.0, f"citation accuracy {accuracy:.3f}: {unresolved}/{total} unresolved"