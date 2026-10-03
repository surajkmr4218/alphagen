"""Retrieval-quality ratchets: the golden set scored through the PRODUCTION retriever.

Every ranking here comes from `app.rag.retrieve` over the full pool of the pinned filing
(~130 chunks), via `app.eval.ablation`. Needs Postgres + pgvector with the pinned filings
ingested (`uv run python -m scripts.ingest_golden`). Skips cleanly when no database is
reachable (CI has none); fails loudly if any golden label does not resolve.

Floors are ratchets: set slightly below the last honest run and raised as retrieval improves.
Last run: app/eval/results/latest.json.
"""

from __future__ import annotations

import pytest

from app.eval import ablation
from app.eval.golden import load
from app.eval.metrics import precision_at_k

GOLD = load()

# Populated once per test session by `rankings`; conftest prints RESULTS after the suite.
RESULTS: dict[str, dict] = {}
_RANKINGS: dict[str, list[ablation.Ranking]] = {}


@pytest.fixture(scope="module")
def rankings() -> dict[str, list[ablation.Ranking]]:
    from app.db import SessionLocal, db_available

    if not db_available():
        pytest.skip("no database reachable — DB-backed retrieval eval skipped")
    if not _RANKINGS:
        with SessionLocal() as db:
            _RANKINGS.update(ablation.rank_all(db, GOLD))  # raises if labels don't resolve
        RESULTS.update({name: ablation.score_rankings(r) for name, r in _RANKINGS.items()})
    return _RANKINGS


# RATCHET: raise these as retrieval improves. Observed 2026-09-11 (post-judgment labels):
#   hybrid  R-prec 0.695  recall@10 0.782  MRR 1.000
#   dense   R-prec 0.600  recall@10 0.596  MRR 0.913
FLOORS: dict[str, dict[str, float]] = {
    "hybrid": {"r_precision": 0.65, "recall_at_k": 0.72, "mrr": 0.95},  # production path
    "dense": {"r_precision": 0.55, "recall_at_k": 0.55, "mrr": 0.85},   # first stage alone
}
# RATCHET: weakest hybrid query (NVDA foundries) scores 0.2; 0.15 leaves headroom for float
# noise while still failing if that query's one top-5 hit is lost (p@5 is a multiple of 0.2).
PER_QUERY_P5_FLOOR = 0.15


@pytest.mark.parametrize(
    "strategy,metric", [(s, m) for s in FLOORS for m in FLOORS[s]], ids=lambda v: v
)
def test_mean_metric_floor(rankings, strategy: str, metric: str) -> None:
    got = RESULTS[strategy][metric]
    floor = FLOORS[strategy][metric]
    assert got >= floor, f"{strategy} {metric} {got:.3f} < floor {floor}"


@pytest.mark.parametrize("i", range(len(GOLD)), ids=[c["query"][:40] for c in GOLD])
def test_hybrid_precision_at_5_per_query(rankings, i: int) -> None:
    ranked, relevant, _ = rankings["hybrid"][i]
    p = precision_at_k(ranked, relevant, k=5)
    assert p >= PER_QUERY_P5_FLOOR, (
        f"hybrid precision@5 {p:.2f} < {PER_QUERY_P5_FLOOR} for: {GOLD[i]['query']}"
    )


def test_hybrid_beats_every_single_stage_on_r_precision(rankings) -> None:
    """The reranker must earn its keep — otherwise production should not pay for it."""
    best_single = max(RESULTS[s]["r_precision"] for s in ("dense", "bm25"))
    assert RESULTS["hybrid"]["r_precision"] > best_single
