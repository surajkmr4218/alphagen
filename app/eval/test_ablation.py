"""Ablation scoring is pure once rankings exist — test it with hand-built rankings."""

from __future__ import annotations

import pytest

from app.eval.ablation import score_rankings, unjudged_ids

# (ranked ids, relevant ids, ticker) — two tickers, two queries each.
RANKINGS = [
    ([1, 2, 9, 8, 7], {1, 2, 3}, "AAPL"),      # r-prec 2/3, recall@5 2/3, mrr 1
    ([9, 3, 8, 7, 6], {3}, "AAPL"),            # r-prec 0,   recall@5 1,   mrr 1/2
    ([5, 4, 9, 8, 7], {4, 5}, "META"),         # r-prec 1,   recall@5 1,   mrr 1
    ([9, 8, 7, 6, 1], {2}, "META"),            # r-prec 0,   recall@5 0,   mrr 0
]


def test_score_rankings_aggregates_over_all_queries() -> None:
    s = score_rankings(RANKINGS, k=5)
    assert s["n_queries"] == 4
    assert s["r_precision"] == pytest.approx((2 / 3 + 0 + 1 + 0) / 4)
    assert s["recall_at_k"] == pytest.approx((2 / 3 + 1 + 1 + 0) / 4)
    assert s["mrr"] == pytest.approx((1 + 0.5 + 1 + 0) / 4)
    assert s["precision_at_5"] == pytest.approx((2 / 5 + 1 / 5 + 2 / 5 + 0) / 4)
    assert s["precision_at_5_ceiling"] == pytest.approx((3 / 5 + 1 / 5 + 2 / 5 + 1 / 5) / 4)


def test_score_rankings_slices_per_ticker() -> None:
    s = score_rankings(RANKINGS, k=5)
    assert set(s["per_ticker"]) == {"AAPL", "META"}
    assert s["per_ticker"]["META"]["r_precision"] == pytest.approx(0.5)
    assert s["per_ticker"]["META"]["n_queries"] == 2


def test_unjudged_ids_is_union_of_top_k_minus_relevant() -> None:
    by_strategy = {"dense": [1, 9, 8], "bm25": [7, 1, 2]}
    assert unjudged_ids(by_strategy, relevant={1, 2}, k=2) == {9, 7}
