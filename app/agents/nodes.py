from __future__ import annotations

import json
import re
from datetime import date

from app.agents.state import TradeState
from app.config import guardrail_cfg, settings
from app.guardrails.rules import validate

MODEL = "gemini-3.1-flash-lite"   # reasoning nodes; bump to gemini-3.5-flash/3.1-pro if weak
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


_GENAI_CLIENT = None


def _client():
    # Cache one Client for the process. A throwaway `genai.Client()` per call can be
    # garbage-collected mid-request (it closes its httpx connection on __del__), which
    # surfaces as "Cannot send a request, as the client has been closed" under LangGraph.
    # Keep one Client alive for whole process so httpx connection never closes.
    global _GENAI_CLIENT
    if _GENAI_CLIENT is None:
        from google import genai  # lazy: keeps `import app.agents.graph` fast
        _GENAI_CLIENT = genai.Client(api_key=settings.gemini_api_key)
    return _GENAI_CLIENT


def _json_call(prompt: str, system: str, max_tokens: int = 1500) -> dict:
    """Single-shot Gemini call that must return a JSON object. Tolerant of fences."""
    resp = _client().models.generate_content(
        model=MODEL,
        contents=prompt,
        config={
            "system_instruction": system,
            "max_output_tokens": max_tokens,
            "response_mime_type": "application/json",  # ask Gemini for raw JSON
        },
    )
    text = resp.text.strip()
    text = _FENCE.sub("", text).strip()
    # Last-ditch: grab the outermost {...} if the model added stray prose.
    if not text.startswith("{"):
        m = re.search(r"\{.*\}", text, re.DOTALL)
        text = m.group(0) if m else text
    return json.loads(text)


def research_node(state: TradeState) -> dict:
    """Assemble the evidence bundle: retrieve -> diff-annotate -> attach FMP signals."""
    from app.db import SessionLocal
    from app.ingestion.fmp import attach_signals
    from app.rag.build import build_diff_bundle

    ticker = state["ticker"]
    query = state.get("query")  # None -> build_diff_bundle uses DEFAULT_QUERY
    session = SessionLocal()
    try:
        bundle = build_diff_bundle(session, ticker, query)  # retrieve (relevance) + diff (annotate)
        bundle = attach_signals(session, ticker, bundle)    # Week 4: structured signals
    finally:
        session.close()
    return {"evidence": bundle}


HYPO_SYSTEM = (
    "You are a disciplined equity analyst. The account is LONG-ONLY (no shorting, no "
    "options, no margin). Output ONLY a JSON object, no prose."
)


def hypothesis_node(state: TradeState) -> dict:
    ev = state["evidence"]
    prompt = (
        "Given this evidence bundle (diffed filing passages + structured signals), propose "
        "AT MOST ONE long trade, or abstain.\n\n"
        f"EVIDENCE:\n{json.dumps(ev, default=str)[:12000]}\n\n"
        "Output JSON: {\n"
        '  "direction": "long" | "none",\n'
        '  "order_type": "limit" | "market",\n'
        '  "limit_price": number | null,\n'
        '  "size_usd": number,            // <= 5; the guardrail enforces this\n'
        '  "confidence": number,          // 0.0-1.0, calibrated honestly\n'
        '  "rationale": string,           // tie to specific evidence\n'
        '  "citations": [{"accession": str, "section": str}]\n'
        "}\n"
        "RULES: direction may NOT be 'short'. Cite ONLY (accession, section) pairs that appear "
        "in evidence.passages. If the evidence is weak or cosmetic, return direction 'none' "
        "with empty citations. Weight bullish-tail signals (high Piotroski, positive analyst "
        "skew, analyst price target above price)."
    )
    hyp = _json_call(prompt, HYPO_SYSTEM)
    return {"hypothesis": hyp}


CRITIC_SYSTEM = (
    "You are a skeptical risk reviewer. Your job is to KILL weak or uncited trades. "
    "Output ONLY a JSON object, no prose."
)


def critic_node(state: TradeState) -> dict:
    ev, hyp = state["evidence"], state["hypothesis"]
    valid = {(p.get("accession"), p.get("section")) for p in ev.get("passages", [])}
    prompt = (
        "Adversarially review this trade hypothesis against the evidence.\n\n"
        f"HYPOTHESIS:\n{json.dumps(hyp, default=str)}\n\n"
        f"EVIDENCE:\n{json.dumps(ev, default=str)[:12000]}\n\n"
        "Do ALL of:\n"
        "1. Steelman the OPPOSITE case (why this trade is wrong).\n"
        "2. Check for overfitting to noise / cosmetic filing edits.\n"
        "3. Verify EACH citation is actually supported by the cited passage.\n"
        "4. Cross-check direction against analyst consensus skew in evidence.signals.\n\n"
        "Output JSON: {\n"
        '  "verdict": "accept" | "reject",\n'
        '  "reasons": [string],\n'
        '  "unsupported_citations": [{"accession": str, "section": str}]\n'
        "}\n"
        "REJECT if any citation is unsupported, if it leans on cosmetic edits, or if "
        "confidence is unjustified by the evidence."
    )
    verdict = _json_call(prompt, CRITIC_SYSTEM)
    # Deterministic backstop: reject any citation not in the evidence set, regardless of LLM.
    cited = {(c.get("accession"), c.get("section")) for c in hyp.get("citations", [])}
    fabricated = [
        {"accession": a, "section": s} for (a, s) in cited - valid if a is not None
    ]
    if fabricated:
        verdict["verdict"] = "reject"
        verdict.setdefault("unsupported_citations", []).extend(fabricated)
        verdict.setdefault("reasons", []).append("Fabricated citation(s) not in evidence.")
    return {"critic_verdict": verdict}

def guardrail_node(state: TradeState) -> dict:
    """Read hypothesis + evidence from state, fetch account/today/cfg, run the pure validator,
    write the full result (passed + every rule) back to state. Never raises on a 'bad' trade —
    a blocked trade is a NORMAL outcome that gets logged, not an error. The DB write happens in
    log_node (which also runs on the critic-reject path), not here."""
    from app.db import session_scope
    from app.execution.dal import ExecutionRepo

    h = state.get("hypothesis") or {}
    evidence = state.get("evidence") or {}
    if not h or h.get("direction") == "none":
        return {"guardrail": {"passed": False,
                              "results": [{"rule": "schema", "passed": False,
                                           "severity": "hard", "reason": "no hypothesis"}]}}
    uid = state.get("clerk_user_id")
    with session_scope(uid) as db:
        account = ExecutionRepo(db).get_account_snapshot(uid, state["ticker"])
    result = validate(h, account, date.today(), evidence, guardrail_cfg())
    return {"guardrail": result}


def log_node(state: TradeState) -> dict:
    """Persist the decision record for EVERY run — the trail (incl. an advisory critic reject)
    must be complete before the approval gate. Always reached via guardrail; a rejected or
    abstaining hypothesis still lands here with guardrail passed=False (no Order).
    Runs before the execute interrupt."""
    from app.agents.logging import write_decision
    from app.db import session_scope

    # The write session carries the same clerk_user_id in the RLS GUC that we stamp into
    # the user_id column, so the row the policy sees and the row we write agree.
    clerk_user_id = state["clerk_user_id"]
    with session_scope(clerk_user_id) as db:
        write_decision(db, state, user_id=clerk_user_id)
    return {}
