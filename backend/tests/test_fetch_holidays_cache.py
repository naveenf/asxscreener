"""
Tests for fetch_holidays()'s in-memory TTL cache.

Context: this was called every ~5 minutes by the pre-close cron job for one
Firestore document that essentially never changes — 288 avoidable reads/day.
Also fixes a reliability gap: the old code returned [] on ANY fetch error,
which would make the pre-close job treat a real holiday as a normal trading
day during a transient Firestore outage (exactly what happened today with the
429 quota error). The cache now serves the last known-good value instead.
"""
import backend.app.services.market_close_schedule as mcs


class FakeDoc:
    def __init__(self, data, exists=True):
        self._data = data
        self.exists = exists

    def to_dict(self):
        return self._data


class FakeCollectionRef:
    def __init__(self, doc):
        self._doc = doc

    def document(self, _name):
        return self

    def get(self):
        return self._doc


class FakeDb:
    """Counts .get() calls so tests can assert Firestore wasn't hit again."""
    def __init__(self, doc):
        self.get_calls = 0
        self._doc = doc

    def collection(self, _name):
        self.get_calls += 1
        return FakeCollectionRef(self._doc)


def _reset_cache():
    mcs._holidays_cache["data"] = None
    mcs._holidays_cache["fetched_at"] = None


def _patch_db(monkeypatch, fake_db):
    """fetch_holidays does a local `from ..firebase_setup import db` import —
    patch the module it's imported from."""
    import backend.app.firebase_setup as firebase_setup
    monkeypatch.setattr(firebase_setup, "db", fake_db)


def test_first_call_fetches_from_firestore(monkeypatch):
    _reset_cache()
    fake_db = FakeDb(FakeDoc({"holidays": [{"date": "2026-12-25", "label": "Christmas"}]}))
    _patch_db(monkeypatch, fake_db)

    result = mcs.fetch_holidays()

    assert result == [{"date": "2026-12-25", "label": "Christmas"}]
    assert fake_db.get_calls == 1


def test_second_call_within_ttl_does_not_refetch(monkeypatch):
    _reset_cache()
    fake_db = FakeDb(FakeDoc({"holidays": [{"date": "2026-12-25"}]}))
    _patch_db(monkeypatch, fake_db)

    mcs.fetch_holidays()
    mcs.fetch_holidays()
    mcs.fetch_holidays()

    assert fake_db.get_calls == 1


def test_refetches_after_ttl_expires(monkeypatch):
    _reset_cache()
    fake_db = FakeDb(FakeDoc({"holidays": [{"date": "2026-12-25"}]}))
    _patch_db(monkeypatch, fake_db)

    mcs.fetch_holidays()
    assert fake_db.get_calls == 1

    # Simulate the cache having gone stale
    from datetime import datetime, timezone, timedelta
    mcs._holidays_cache["fetched_at"] = (
        datetime.now(timezone.utc) - mcs._HOLIDAYS_CACHE_TTL - timedelta(seconds=1)
    )

    mcs.fetch_holidays()
    assert fake_db.get_calls == 2


def test_failed_refresh_serves_stale_cache_instead_of_empty(monkeypatch):
    """This is the reliability fix: a transient Firestore error must not make
    the pre-close job think there are no holidays when it already knew better."""
    _reset_cache()
    good_db = FakeDb(FakeDoc({"holidays": [{"date": "2026-12-25", "label": "Christmas"}]}))
    _patch_db(monkeypatch, good_db)
    mcs.fetch_holidays()  # seed the cache with a known-good value

    from datetime import datetime, timezone, timedelta
    mcs._holidays_cache["fetched_at"] = (
        datetime.now(timezone.utc) - mcs._HOLIDAYS_CACHE_TTL - timedelta(seconds=1)
    )

    class ExplodingDb:
        def collection(self, _name):
            raise Exception("429 Quota exceeded")

    _patch_db(monkeypatch, ExplodingDb())

    result = mcs.fetch_holidays()

    assert result == [{"date": "2026-12-25", "label": "Christmas"}]


def test_failed_fetch_with_no_prior_cache_returns_empty_list(monkeypatch):
    _reset_cache()

    class ExplodingDb:
        def collection(self, _name):
            raise Exception("429 Quota exceeded")

    _patch_db(monkeypatch, ExplodingDb())

    assert mcs.fetch_holidays() == []


def test_missing_document_returns_empty_list_and_caches_it(monkeypatch):
    _reset_cache()
    fake_db = FakeDb(FakeDoc({}, exists=False))
    _patch_db(monkeypatch, fake_db)

    assert mcs.fetch_holidays() == []
    assert mcs.fetch_holidays() == []
    assert fake_db.get_calls == 1  # empty result still cached, not refetched
