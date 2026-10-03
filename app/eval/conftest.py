from __future__ import annotations

import pytest


@pytest.fixture(scope="session", autouse=True)
def _print_eval_metrics():
    yield  # run after the suite
    from app.eval.ablation import RESULTS_PATH, markdown_table
    from app.eval.test_rag import GOLD, RESULTS

    print("\n================ RAG EVAL METRICS ================")
    if RESULTS:
        n_labels = sum(len(c["relevant_chunk_ids"]) for c in GOLD)
        print(markdown_table(RESULTS))
        print(
            f"  {len(GOLD)} queries, {n_labels} labels, k=10 — scored via production "
            "retrieve() over the pinned-filing pool"
        )
    else:
        print(f"  DB-backed eval skipped (no database). Last committed run: {RESULTS_PATH}")
    print("==================================================")
