from __future__ import annotations

from typing import Literal, TypedDict


class TradeState(TypedDict, total=False):
    # --- inputs (set by the caller before invoke) ---
    clerk_user_id: str
    ticker: str
    query: str                       # analyst question driving retrieval; build_diff_bundle
                                     # falls back to DEFAULT_QUERY when absent
    execution_enabled: bool          # the tier gate: Owner=True, Public=False
    decision_id: str                 # idempotency key; also the LangGraph thread_id

    # --- filled by research_node ---
    evidence: dict                   # signals block

    # --- filled by hypothesis_node ---
    hypothesis: dict | None          # structured trade proposal 

    # --- filled by critic_node ---
    critic_verdict: dict | None      # {verdict, reasons, unsupported_citations}

    # --- filled by guardrail_node ---
    guardrail: dict | None           # {passed, results}

    # --- filled by the human-approval interrupt ---
    human_decision: Literal["approved", "rejected", "pending"]

    # --- filled by execute_node  ---
    order: dict | None               # broker response / rejection record