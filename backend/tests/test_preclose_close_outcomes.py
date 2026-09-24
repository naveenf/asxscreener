"""Regression tests for how _close_open_positions_for_pair interprets Oanda's
response when flattening a position before the weekly close.

Four defects motivated these, all of which wrote — or withheld — Firestore state
on bad evidence:

  1. `get_trade_details() is None` was read as "already closed". It returns None
     for ANY failure (API unavailable, auth, network — oanda_price.py:533,545),
     so an outage marked a LIVE position CLOSED. Every job that manages a trade
     queries status == "OPEN", so the position then became invisible to the
     stop-move stages, to _sync_oanda_closed_trades, and to this very job the
     following week — which for BCO_USD means ALWAYS_CLOSE_PAIRS weekend
     flattening silently stops applying.
  2. The genuinely-already-closed case (trade hit TP/SL between the Firestore
     read and the close attempt) returns a DICT with state CLOSED, so it fell
     into the "still open" branch and logged a false error forever.
  3. A REJECTED close returns a truthy response, so a bare `result is None`
     test treated it as success and marked the doc CLOSED while the position
     stayed live.
  4. sell_price/pnl were never written. _sync_oanda_closed_trades is the only
     other writer of those and it queries status == "OPEN", so marking CLOSED
     first booked the trade at $0 P&L permanently.
"""
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.app.services import tasks


NOW = datetime(2026, 9, 25, 20, 5, tzinfo=timezone.utc)


class _FakeRef:
    def __init__(self):
        self.id = "doc1"
        self.updates = []

    def update(self, payload):
        self.updates.append(payload)


class _FakeDoc:
    def __init__(self, data):
        self._data = data
        self.id = "doc1"
        self.reference = _FakeRef()

    def to_dict(self):
        return self._data


@pytest.fixture
def trade_doc():
    return _FakeDoc({
        "symbol": "BCO_USD",
        "oanda_trade_id": "7788",
        "notes": "Auto-traded via Bot.",
        "status": "OPEN",
    })


@pytest.fixture
def harness(monkeypatch, trade_doc):
    """Drive the real _close_open_positions_for_pair with Oanda stubbed out."""
    monkeypatch.setattr(tasks, "db", MagicMock())
    monkeypatch.setattr(tasks, "_firestore_call", lambda fn, **kw: [trade_doc])

    calls = {}

    def _install(close_result, details_result):
        svc = MagicMock()
        svc.close_trade.side_effect = lambda tid, *a, **k: (
            calls.__setitem__("close", tid) or close_result)
        svc.get_trade_details.side_effect = lambda tid, *a, **k: (
            calls.__setitem__("details", tid) or details_result)
        monkeypatch.setattr(tasks, "OandaPriceService", svc)
        return calls

    return _install


def _run():
    tasks._close_open_positions_for_pair("BCO_USD", "user@example.com", NOW)


# ── 1. unconfirmed state must NOT be written as CLOSED ───────────────────────
def test_oanda_unreachable_leaves_doc_open(harness, trade_doc):
    """close_trade None + get_trade_details None = 'cannot determine'.
    Writing CLOSED here would hide a live position from next week's flatten."""
    harness(None, None)
    _run()
    assert trade_doc.reference.updates == []


def test_close_failed_but_trade_still_open_leaves_doc_open(harness, trade_doc):
    harness(None, {"state": "OPEN"})
    _run()
    assert trade_doc.reference.updates == []


# ── 2. the already-closed case is recognised, not mis-logged ─────────────────
def test_already_closed_at_oanda_is_synced(harness, trade_doc):
    harness(None, {"state": "CLOSED", "averageClosePrice": "81.2", "realizedPL": "-13.5"})
    _run()
    assert len(trade_doc.reference.updates) == 1
    payload = trade_doc.reference.updates[0]
    assert payload["status"] == "CLOSED"
    assert payload["sell_price"] == 81.2
    assert payload["pnl"] == -13.5


# ── 3. a rejection is never a success ────────────────────────────────────────
def test_rejected_close_leaves_doc_open(harness, trade_doc):
    """close_trade returns a TRUTHY response on rejection."""
    harness({"orderRejectTransaction": {"rejectReason": "MARKET_HALTED"}}, None)
    _run()
    assert trade_doc.reference.updates == []


# ── 4. a real close records P&L ──────────────────────────────────────────────
def test_successful_close_writes_pnl_and_price(harness, trade_doc):
    harness({"orderFillTransaction": {
        "tradesClosed": [{"price": "80.55", "realizedPL": "42.10"}]}}, None)
    _run()
    payload = trade_doc.reference.updates[0]
    assert payload["status"] == "CLOSED"
    assert payload["close_type"] == "PRE_CLOSE"
    assert payload["sell_price"] == 80.55
    assert payload["pnl"] == 42.10
    assert "updated_at" in payload


def test_successful_close_without_fill_data_still_closes(harness, trade_doc):
    """Missing P&L must not block the close — the position is already flat."""
    harness({"orderFillTransaction": {}}, None)
    _run()
    payload = trade_doc.reference.updates[0]
    assert payload["status"] == "CLOSED"
    assert "sell_price" not in payload
    assert "updated_at" in payload


def test_no_second_oanda_call_when_close_succeeds(harness, trade_doc):
    """get_trade_details is only consulted when close_trade failed."""
    calls = harness({"orderFillTransaction": {"price": "80.0", "pl": "1.0"}}, None)
    _run()
    assert "close" in calls
    assert "details" not in calls


# ── keep_through_close still wins ────────────────────────────────────────────
def test_keep_through_close_skips_the_trade(monkeypatch, harness):
    doc = _FakeDoc({"symbol": "BCO_USD", "oanda_trade_id": "7788",
                    "keep_through_close": True, "status": "OPEN"})
    monkeypatch.setattr(tasks, "_firestore_call", lambda fn, **kw: [doc])
    harness({"orderFillTransaction": {}}, None)
    _run()
    assert doc.reference.updates == []
