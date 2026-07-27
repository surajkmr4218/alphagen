from __future__ import annotations

from datetime import date

from app.guardrails.rules import _citations_resolve, validate

CFG = {
    "max_notional": 5.0, "max_exposure": 50.0, "min_conf": 0.60,
    "allowlist": ["AAPL", "MSFT"], "max_per_day": 3, "max_daily_loss": 5.0,
}
EVIDENCE = {"passages": [{"accession": "0000320193-25-000001", "section": "item 1a",
                          "text": "Risk factor language changed materially."}]}
TODAY = date(2026, 6, 16)
ACCOUNT = {"ticker": "AAPL", "deployed": 0.0, "trades_today": 0, "pnl_today": 0.0}


def _hyp(**over) -> dict:
    """A fully VALID hypothesis; override one field per test to violate one rule."""
    h = {
        "ticker": "AAPL", "direction": "long", "order_type": "limit",
        "limit_price": 190.0, "size_usd": 3.0, "confidence": 0.75,
        "rationale": "Material positive drift + insider buying.",
        "citations": [{"accession": "0000320193-25-000001", "section": "item 1a"}],
    }
    h.update(over)
    return h


def _failed_rules(result: dict) -> set[str]:
    return {r["rule"] for r in result["results"] if not r["passed"]}


def test_clean_hypothesis_passes():
    out = validate(_hyp(), ACCOUNT, TODAY, EVIDENCE, CFG)
    assert out["passed"] is True
    assert _failed_rules(out) == set()


def test_over_cap_blocks():
    # size 7 > max_notional 5 -> position_cap fails -> not passed.
    out = validate(_hyp(size_usd=7.0), ACCOUNT, TODAY, EVIDENCE, CFG)
    assert out["passed"] is False
    assert "position_cap" in _failed_rules(out)


def test_unresolved_citation_blocks():
    bad = _hyp(citations=[{"accession": "9999-99-999999", "section": "item 7"}])
    out = validate(bad, ACCOUNT, TODAY, EVIDENCE, CFG)
    assert out["passed"] is False
    assert "citations" in _failed_rules(out)


def test_empty_citation_blocks():
    out = validate(_hyp(citations=[]), ACCOUNT, TODAY, EVIDENCE, CFG)
    assert out["passed"] is False
    assert "citations" in _failed_rules(out)


def test_not_allowlisted_blocks():
    out = validate(_hyp(ticker="TSLA"), {**ACCOUNT, "ticker": "TSLA"},
                   TODAY, EVIDENCE, CFG)
    assert out["passed"] is False
    assert "allowlist" in _failed_rules(out)


def test_low_confidence_is_soft_still_passes():
    # confidence below floor: the SOFT rule fails, but passed stays True.
    out = validate(_hyp(confidence=0.30), ACCOUNT, TODAY, EVIDENCE, CFG)
    assert out["passed"] is True
    assert "confidence" in _failed_rules(out)   # flagged...
    # but it is the only failure and it is soft, so the trade is still eligible.
    soft = [r for r in out["results"] if r["rule"] == "confidence"][0]
    assert soft["severity"] == "soft"


def test_rate_limit_blocks():
    acct = {**ACCOUNT, "trades_today": 3}   # 3 == max_per_day -> blocked
    out = validate(_hyp(), acct, TODAY, EVIDENCE, CFG)
    assert out["passed"] is False
    assert "rate_limit" in _failed_rules(out)


def test_missing_schema_keys_blocks():
    out = validate({"ticker": "AAPL", "direction": "long"}, ACCOUNT, TODAY, EVIDENCE, CFG)
    assert out["passed"] is False
    assert "schema" in _failed_rules(out)


def test_all_rules_are_always_recorded():
    # Even a clean pass logs every rule — the dashboard needs the full trail.
    out = validate(_hyp(), ACCOUNT, TODAY, EVIDENCE, CFG)
    rules = {r["rule"] for r in out["results"]}
    assert rules == {"schema", "citations", "position_cap",
                     "confidence", "allowlist", "rate_limit"}


def test_citation_helper_directly():
    assert _citations_resolve(_hyp(), EVIDENCE) is True
    assert _citations_resolve(_hyp(citations=[]), EVIDENCE) is False


# --- Week-7 check-twice rules (keyword-only, execution-time only) -------------------

def test_check_twice_rules_absent_without_params():
    # Guardrail-node / offline callers pass neither -> the two rules are NOT recorded.
    out = validate(_hyp(), ACCOUNT, TODAY, EVIDENCE, CFG)
    assert "market_hours" not in _failed_rules(out)
    rules = {r["rule"] for r in out["results"]}
    assert "market_hours" not in rules and "price_sanity" not in rules


def test_market_closed_blocks():
    out = validate(_hyp(), ACCOUNT, TODAY, EVIDENCE, CFG, live_price=190.0, market_open=False)
    assert out["passed"] is False
    assert "market_hours" in _failed_rules(out)


def test_market_open_and_good_price_passes():
    out = validate(_hyp(), ACCOUNT, TODAY, EVIDENCE, CFG, live_price=190.0, market_open=True)
    assert out["passed"] is True
    rules = {r["rule"] for r in out["results"]}
    assert {"market_hours", "price_sanity"} <= rules   # both now recorded


def test_bad_live_price_blocks():
    out = validate(_hyp(), ACCOUNT, TODAY, EVIDENCE, CFG, live_price=0.0, market_open=True)
    assert out["passed"] is False
    assert "price_sanity" in _failed_rules(out)