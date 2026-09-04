"""Tests for the cooldown-candidate selection used by check_pair_lock_cooldowns.

The Firestore query behind this filters on updated_at ALONE (so it uses the
automatic single-field index and stays cheap); every other condition —
symbol, status, lock_fired, lock_cooldown_set — is applied here, client-side.
That makes this function the whole correctness surface of the read reduction,
so it is tested exhaustively.

No Firestore access: these are plain dicts, the same shape doc.to_dict()
returns. Running this suite costs zero reads.
"""
from backend.app.services.tasks import select_cooldown_candidates

# Two pairs with a cooldown, one breakeven-only pair without.
CONFIGS = {
    "BCO_USD":    {"lock_at_r": 2.0, "lock_to_r": 1.5, "cooldown_min": 90, "sl_precision": 3},
    "NAS100_USD": {"lock_at_r": 1.5, "lock_to_r": 0.5, "cooldown_min": 90, "sl_precision": 1},
    "JP225_USD":  {"be_at_r": 0.25, "be_to_r": -0.1, "sl_precision": 1},
}


def trade(symbol="BCO_USD", status="CLOSED", lock_fired=True, cooldown_set=False, **extra):
    d = {"symbol": symbol, "status": status, "lock_fired": lock_fired}
    if cooldown_set:
        d["lock_cooldown_set"] = True
    d.update(extra)
    return d


# ── the happy path ───────────────────────────────────────────────────────────
def test_closed_locked_unprocessed_trade_is_selected():
    got = select_cooldown_candidates([("t1", trade())], CONFIGS)
    assert got == [("t1", "BCO_USD", 90)]


def test_multiple_pairs_selected_in_one_pass():
    """One query now covers every pair, so the selector must handle a mixed batch."""
    docs = [("t1", trade(symbol="BCO_USD")), ("t2", trade(symbol="NAS100_USD"))]
    got = select_cooldown_candidates(docs, CONFIGS)
    assert sorted(s for _, s, _ in got) == ["BCO_USD", "NAS100_USD"]


def test_carries_the_pairs_own_cooldown_minutes():
    cfgs = {"BCO_USD": {"cooldown_min": 90}, "NAS100_USD": {"cooldown_min": 25}}
    docs = [("t1", trade(symbol="BCO_USD")), ("t2", trade(symbol="NAS100_USD"))]
    assert dict((s, m) for _, s, m in select_cooldown_candidates(docs, cfgs)) == {
        "BCO_USD": 90, "NAS100_USD": 25,
    }


# ── each filter that the Firestore query no longer applies ───────────────────
def test_open_trade_is_skipped():
    assert select_cooldown_candidates([("t1", trade(status="OPEN"))], CONFIGS) == []


def test_trade_whose_lock_never_fired_is_skipped():
    assert select_cooldown_candidates([("t1", trade(lock_fired=False))], CONFIGS) == []


def test_missing_lock_fired_field_is_skipped():
    d = trade()
    del d["lock_fired"]
    assert select_cooldown_candidates([("t1", d)], CONFIGS) == []


def test_already_processed_trade_is_skipped():
    """lock_cooldown_set=True is what stops a cooldown being rewritten every cycle."""
    assert select_cooldown_candidates([("t1", trade(cooldown_set=True))], CONFIGS) == []


def test_pair_without_any_lock_config_is_skipped():
    assert select_cooldown_candidates([("t1", trade(symbol="XAU_USD"))], CONFIGS) == []


def test_breakeven_only_pair_is_skipped():
    """JP225 has no cooldown_min — a breakeven locks in nothing, so no cooldown."""
    docs = [("t1", trade(symbol="JP225_USD", lock_fired=True))]
    assert select_cooldown_candidates(docs, CONFIGS) == []


def test_zero_cooldown_min_is_skipped():
    assert select_cooldown_candidates([("t1", trade())], {"BCO_USD": {"cooldown_min": 0}}) == []


def test_missing_symbol_is_skipped():
    d = trade()
    del d["symbol"]
    assert select_cooldown_candidates([("t1", d)], CONFIGS) == []


# ── batch behaviour ──────────────────────────────────────────────────────────
def test_only_the_eligible_trade_is_picked_from_a_mixed_batch():
    docs = [
        ("open", trade(status="OPEN")),
        ("done", trade(cooldown_set=True)),
        ("nolock", trade(lock_fired=False)),
        ("other", trade(symbol="XAU_USD")),
        ("hit", trade()),
    ]
    assert select_cooldown_candidates(docs, CONFIGS) == [("hit", "BCO_USD", 90)]


def test_empty_batch_returns_empty():
    """The common case — most 5-minute cycles have no recently-updated trades."""
    assert select_cooldown_candidates([], CONFIGS) == []


def test_accepts_a_generator():
    """check_pair_lock_cooldowns passes a generator expression, not a list."""
    docs = (x for x in [("t1", trade())])
    assert select_cooldown_candidates(docs, CONFIGS) == [("t1", "BCO_USD", 90)]
