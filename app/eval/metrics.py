"""Pure retrieval metrics — no DB, no model. Shared by the eval tests and the ablation runner.

`retrieved` is a ranked list of chunk ids (best first); `relevant` is the gold set for the
query. Every function is bounded in [0, 1].
"""

from __future__ import annotations


def precision_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    """Fraction of the top-k slots holding a relevant id.

    The denominator is k, not the number returned: a ranker that returns fewer than k ids
    left those slots empty, and an empty slot is a miss. This matters for R-precision, where
    k = |relevant| can exceed the retrieval depth.
    """
    if k <= 0:
        return 0.0
    return sum(1 for cid in retrieved[:k] if cid in relevant) / k


def recall_at_k(retrieved: list[int], relevant: set[int], k: int) -> float:
    """Fraction of relevant ids found inside the top-k."""
    if not relevant:
        return 1.0
    top = set(retrieved[:k])
    return sum(1 for cid in relevant if cid in top) / len(relevant)


def r_precision(retrieved: list[int], relevant: set[int]) -> float:
    """Precision at R, where R is this query's gold-set size. A perfect ranker scores 1.0."""
    return precision_at_k(retrieved, relevant, k=len(relevant))


def mrr(retrieved: list[int], relevant: set[int]) -> float:
    """Reciprocal rank of the first relevant id (0.0 if none appear)."""
    for rank, cid in enumerate(retrieved, start=1):
        if cid in relevant:
            return 1.0 / rank
    return 0.0


def precision_ceiling(relevant_sizes: list[int], k: int) -> float:
    """Best achievable mean precision@k given each query's gold size: mean of min(R, k) / k."""
    if not relevant_sizes:
        return 0.0
    return sum(min(r, k) / k for r in relevant_sizes) / len(relevant_sizes)
