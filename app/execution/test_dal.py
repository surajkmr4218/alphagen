from __future__ import annotations

from app.execution.dal import ExecutionRepo
from app.models import Order


class _FakeSession:
    """Minimal Session double: an in-memory {decision_id: Order} store. Enough to exercise the
    DAL's field-mapping and idempotency logic without a live Postgres."""

    def __init__(self, rows: dict[str, Order] | None = None, count: int = 0) -> None:
        self.rows = rows or {}
        self._count = count
        self.committed = False

    def get(self, _model, pk):
        return self.rows.get(pk)

    def merge(self, obj):
        self.rows[obj.decision_id] = obj
        return obj

    def commit(self):
        self.committed = True

    def scalar(self, _stmt):
        return self._count


def test_order_exists_ignores_pending_placeholder():
    # The log_node 'pending' row must NOT short-circuit execution.
    sess = _FakeSession({"d1": Order(decision_id="d1", status="pending")})
    repo = ExecutionRepo(sess)
    assert repo.order_exists("d1") is None


def test_order_exists_returns_placed_order():
    sess = _FakeSession({"d1": Order(decision_id="d1", status="submitted", symbol="AAPL")})
    repo = ExecutionRepo(sess)
    got = repo.order_exists("d1")
    assert got is not None
    assert got["status"] == "submitted"
    assert got["symbol"] == "AAPL"


def test_order_exists_missing_returns_none():
    assert ExecutionRepo(_FakeSession()).order_exists("nope") is None


def test_write_order_maps_result_fields_onto_row():
    sess = _FakeSession({"d1": Order(decision_id="d1", status="pending")})
    repo = ExecutionRepo(sess)
    repo.write_order("d1", {
        "status": "submitted", "broker_order_id": "RH-9", "symbol": "AAPL",
        "side": "buy", "order_type": "market", "quantity": "0.1234",
    })
    row = sess.rows["d1"]
    assert row.status == "submitted"
    assert row.broker_order_id == "RH-9"
    assert row.qty == 0.1234
    assert sess.committed is True


def test_write_order_rejection_only_sets_status():
    sess = _FakeSession()
    repo = ExecutionRepo(sess)
    repo.write_order("d2", {"status": "rejected", "reason": "check_twice: allowlist"})
    assert sess.rows["d2"].status == "rejected"


def test_today_counters_shape():
    repo = ExecutionRepo(_FakeSession(count=2))
    assert repo.today_counters("owner") == {"trades_today": 2}
    snap = repo.get_account_snapshot("owner")
    assert snap == {"deployed": 0.0, "trades_today": 2, "pnl_today": 0.0}
