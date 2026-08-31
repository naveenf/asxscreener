"""Every write to a forex_portfolio doc must set `updated_at`.

`trade_cache.get_forex_trades_cached()` delta-syncs with
`where('updated_at', '>', cursor)`. Firestore inequality filters skip
documents where the field is ABSENT, so a trade doc written without
`updated_at` is invisible to every delta fetch — permanently, not just
until the next cycle. Two writers in this module used to omit it:
`_log_to_portfolio` (trade creation) and the "not found in Oanda" auto-close.
A trade created and then closed by those two paths never appeared in Trade
History at all.
"""
from datetime import datetime

from backend.app.services.oanda_trade_service import (
    OandaTradeService,
    build_auto_close_update,
)


class _FakeCollection:
    def __init__(self):
        self.added = []

    def add(self, doc_data):
        self.added.append(doc_data)


class _FakeDocument:
    def __init__(self, collection):
        self._collection = collection

    def collection(self, _name):
        return self._collection


class _FakeDb:
    def __init__(self, collection):
        self._document = _FakeDocument(collection)

    def collection(self, _name):
        return self

    def document(self, _name):
        return self._document


def test_logged_trade_has_updated_at(monkeypatch):
    collection = _FakeCollection()
    monkeypatch.setattr(
        "backend.app.services.oanda_trade_service.db", _FakeDb(collection)
    )

    OandaTradeService._log_to_portfolio(
        email="user@example.com",
        signal={
            'symbol': 'BCO_USD',
            'signal': 'BUY',
            'strategy': 'SmaScalping',
            'stop_loss': 90.0,
            'take_profit': 95.0,
        },
        units=100,
        exec_price=91.0,
        trade_id="12345",
    )

    assert len(collection.added) == 1
    doc = collection.added[0]
    assert isinstance(doc.get('updated_at'), datetime), (
        "a new trade doc without updated_at never reaches the delta-synced cache"
    )


def test_auto_close_update_has_updated_at():
    update = build_auto_close_update(existing_notes="Auto-traded via Bot.", close_type="SL")

    assert isinstance(update.get('updated_at'), datetime), (
        "auto-close without updated_at leaves the cached row stale/OPEN forever"
    )
    assert update['status'] == 'CLOSED'
    assert update['close_type'] == 'SL'
    assert update['notes'].endswith("| Auto-closed: Not found in Oanda open trades.")
    assert update['sell_date'] == datetime.utcnow().strftime("%Y-%m-%d")


def test_auto_close_update_tolerates_missing_notes():
    update = build_auto_close_update(existing_notes=None, close_type="UNKNOWN")

    assert update['notes'].strip().startswith("| Auto-closed") is False
    assert "Auto-closed: Not found in Oanda open trades." in update['notes']
