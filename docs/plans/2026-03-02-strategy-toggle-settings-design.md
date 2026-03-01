# Strategy Toggle Settings — Design Doc

**Date:** 2026-03-02
**Feature:** Per-pair/strategy on/off controls accessible from the frontend
**Status:** Approved

---

## Problem

The cron job runs all pairs + strategies defined in `best_strategies.json` unconditionally.
The user needs a way to temporarily disable specific pair+strategy combinations (e.g. during volatile market conditions) without touching the config file.

---

## Decisions

| Question | Decision |
|----------|----------|
| UI placement | Dedicated `/settings` route, new "Settings" nav tab |
| Storage | Firestore global doc `config/strategy_overrides` |
| Data model | `disabled` list — new strategies default ON |
| Cron integration | Read Firestore at start of each `run_forex_refresh_task()` |
| Write auth guard | Only `AUTHORIZED_AUTO_TRADER_EMAIL` (naveenf.opt@gmail.com) |
| Visibility | All logged-in users can view; only admin can save changes |

---

## Data Model

Firestore document: `config/strategy_overrides`

```json
{
  "disabled": ["XAG_USD::SilverSniper", "USD_CAD::SmaScalping"],
  "updated_by": "naveenf.opt@gmail.com",
  "updated_at": "<Firestore server timestamp>"
}
```

A combo key is `"{PAIR}::{StrategyName}"` (e.g. `"XAG_USD::SmaScalping"`).
If `disabled` is empty or the doc doesn't exist, all strategies run (safe default).

**Current 19 combos** (from `best_strategies.json`):
- XAU_USD: HeikenAshi, SmaScalping
- XAG_USD: DailyORB, SilverSniper, SilverMomentum, PVTScalping, SmaScalping
- JP225_USD: HeikenAshi, SmaScalping
- AUD_USD: EnhancedSniper, SmaScalping
- NAS100_USD: NewBreakout, PVTScalping, SmaScalping
- BCO_USD: CommoditySniper
- USD_CAD: SmaScalping
- USD_CHF: NewBreakout
- UK100_GBP: PVTScalping
- USD_JPY: SmaScalping

---

## Backend Changes

### 1. `forex_screener.py`

Modify `screen_all()` to accept `disabled_combos: set[str] = None`:

```python
def screen_all(self, mode='dynamic', disabled_combos=None):
    disabled_combos = disabled_combos or set()
    ...
    # Before running a strategy:
    combo_key = f"{symbol}::{strategy_name}"
    if combo_key in disabled_combos:
        logger.info(f"Skipping {combo_key} (user disabled)")
        continue
```

Also propagate through `run_orchestrated_refresh()` static method.

### 2. `tasks.py`

At the top of `run_forex_refresh_task()`:

```python
# Fetch user override config
disabled_combos = set()
try:
    doc = db.collection('config').document('strategy_overrides').get()
    if doc.exists:
        disabled_combos = set(doc.to_dict().get('disabled', []))
        logger.info(f"Loaded {len(disabled_combos)} disabled combos from Firestore")
except Exception as e:
    logger.warning(f"Could not load strategy overrides, running all: {e}")

results = ForexScreener.run_orchestrated_refresh(
    ...,
    disabled_combos=disabled_combos
)
```

### 3. New `backend/app/api/settings.py`

Two endpoints:

```
GET  /api/settings/strategy-overrides
     → Returns { disabled: [...] }
     → Auth required (any logged-in user, for read)

PUT  /api/settings/strategy-overrides
     → Body: { disabled: ["XAG_USD::SilverSniper", ...] }
     → Auth required (only AUTHORIZED_AUTO_TRADER_EMAIL)
     → Writes to Firestore config/strategy_overrides
     → Returns { success: true, disabled: [...] }
```

Auth check reuses the Google Bearer token pattern from existing routes.

### 4. `main.py`

Register the new `settings` router.

---

## Frontend Changes

### 1. `Header.jsx`

Add "Settings" nav link, visible only when `user` is truthy (i.e., logged in).

### 2. `App.jsx`

Add route: `<Route path="/settings" element={<Settings onShowToast={setToast} />} />`

### 3. New `frontend/src/components/Settings.jsx`

Layout:
- Page title: "Strategy Controls"
- Subtitle: "Enable or disable pair/strategy combinations. Changes apply from the next screener run."
- Grouped by pair (e.g. "XAG_USD" as a section header)
- Each row: `[Pair label] [Strategy badge] [Timeframe] [Toggle switch]`
- "Save Changes" button — calls PUT endpoint
  - Disabled and tooltip "Read only" for non-admin users
- Success/error feedback via `onShowToast` prop
- Loading state while fetching

### 4. `frontend/src/services/api.js`

```js
export const getStrategyOverrides = async () => { ... }   // GET
export const updateStrategyOverrides = async (disabled) => { ... }  // PUT
```

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Firestore read fails in cron | Warning logged, all strategies run (safe fallback) |
| Non-admin user calls PUT | Backend returns 403 |
| Frontend save fails | Toast error message shown |
| `best_strategies.json` changes | New combos default to ON (disabled list doesn't include them) |

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `backend/app/api/settings.py` | Create |
| `backend/app/main.py` | Modify — register settings router |
| `backend/app/services/forex_screener.py` | Modify — accept/apply `disabled_combos` |
| `backend/app/services/tasks.py` | Modify — fetch overrides from Firestore |
| `frontend/src/components/Settings.jsx` | Create |
| `frontend/src/components/Header.jsx` | Modify — add Settings nav link |
| `frontend/src/App.jsx` | Modify — add /settings route |
| `frontend/src/services/api.js` | Modify — add 2 API functions |
