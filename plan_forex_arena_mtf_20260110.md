# Implementation Plan: Forex Backtest Arena & Dynamic Strategy Selection (MTF Enhanced)

**Plan ID:** `plan_forex_arena_mtf_20260110`
**Created:** 2026-01-10 11:50
**Completed:** 2026-01-10 12:30
**Author:** Gemini CLI (Plan Mode)
**Status:** ✅ IMPLEMENTED
**Estimated Complexity:** High
**Estimated Phases:** 4

---

## 📋 Executive Summary

This plan implements a scientific approach to trading strategy selection, leveraging the new **Oanda Multi-Timeframe (MTF) Data**. We will build a **Backtest Arena** that tests multiple strategies against all forex pairs using 15m, 1h, and 4h data. The strategies will be updated to use native HTF data for trend confirmation rather than on-the-fly resampling. The results will generate a `best_strategies.json` map for the live screener.

---

## 🔍 Analysis

### Codebase Exploration
- **Data Source:** Now using Oanda. Structure implies separate files or dataframes for `15m`, `1h`, `4h` are available.
- **Current Logic:** `SniperDetector` currently uses `TechnicalIndicators.resample_to_1h(df_15m)`. This is inefficient and less accurate than using the native Oanda 1h data.
- **Strategies:**
  - `Sniper`: Can now use true 1H/4H for the "Casket" trend filters.
  - `Triple Trend`: Can confirm supertrend on 4H before entering on 15m.
  - `Squeeze`: Can detect volatility compression on 15m aligned with 1H expansion.

### Dependencies Identified
| Dependency | Type | Impact |
|------------|------|--------|
| `ForexStrategy` Interface | New | Must accept a *dictionary* of DataFrames `{ "15m": df, "1h": df, "4h": df }` instead of a single df. |
| `BacktestArena` | Script | Must load multiple CSVs per symbol during the test loop. |
| `ForexScreener` | Service | Must load multiple timeframes during live analysis. |

### Risks & Considerations
| Risk | Severity | Mitigation |
|------|----------|------------|
| **Data Synchronization** | Medium | Timestamps between 15m, 1h, and 4h files must align. The backtester must match the 15m entry candle to the *completed* 1h/4h candle. |
| **Complexity** | Medium | Passing multiple dataframes increases memory usage slightly, but is manageable for text/csv data. |

---

## ✅ Implementation Plan

### Phase 1: Standardization & Interface Update                               ✅ COMPLETED
**Objective:** Define a standard way for strategies to request and use Multi-Timeframe data.
**Complexity:** Medium
**Depends On:** None

#### Tasks:
- [x] **Task 1.1:** Extract hardcoded caskets to config.
  - **Files:** `data/metadata/forex_baskets.json`, `backend/app/services/sniper_detector.py`
  - **Action:** Move 'Momentum', 'Steady', 'Cyclical' lists to JSON.
  - **Verification:** Read file in Python to confirm valid JSON.

- [x] **Task 1.2:** Define MTF `ForexStrategy` Interface.
  - **Files:** `backend/app/services/strategy_interface.py`
  - **Action:** Create abstract base class.
    - Signature: `analyze(data: Dict[str, pd.DataFrame], symbol: str) -> Optional[Dict]`
    - `data` keys will be `'15m'`, `'1h'`, `'4h'`.
  - **Verification:** Code compiles.

- [x] **Task 1.3:** Refactor existing detectors for MTF.
  - **Files:** `ForexDetector`, `SniperDetector`, `TripleTrendDetector`
  - **Action:**
    - `SniperDetector`: Remove `resample_to_1h`. Use `data['1h']` directly for HTF trend checks.
    - `TripleTrendDetector`: Add optional 4H trend confirmation (Supertrend on `data['4h']`).
    - `ForexDetector`: Check 4H EMA Trend for direction bias.
  - **Verification:** Run a simple script to instantiate each.

- [x] **Task 1.4:** Create `SqueezeDetector` (MTF).
  - **Files:** `backend/app/services/squeeze_detector.py`
  - **Action:** Implement BB Squeeze on 15m, confirmed by ADX < 25 on 1H (energy building).
  - **Verification:** Run against a known ranging pair (e.g., EURCHF).

#### Phase 1 Acceptance Criteria:
- [x] Interface accepts dict of dataframes.
- [x] Detectors compile and use native 1h/4h data instead of resampling.

---

### Phase 2: The Backtest Arena (MTF)                                        ✅ COMPLETED
**Objective:** Run the strategies using the rich Oanda dataset.
**Complexity:** High
**Depends On:** Phase 1

#### Tasks:
- [x] **Task 2.1:** Create `BacktestArena` class with MTF Loader.
  - **Files:** `scripts/backtest_arena.py`
  - **Action:**
    - Logic to find `symbol_15m.csv`, `symbol_1h.csv`, `symbol_4h.csv`.
    - Align timestamps (forward fill HTF data to match 15m index for easy lookup, or use merge_asof).
  - **Verification:** Verify alignment (e.g., 10:00, 10:15, 10:30 15m candles all see the 10:00 1h candle).

- [x] **Task 2.2:** Implement Scoring & Optimization.
  - **Files:** `scripts/backtest_arena.py`
  - **Action:** Run all strategies. Calculate Weighted Score (WR + PF).
  - **Verification:** Manually calculate score for sample data.

- [x] **Task 2.3:** Generate `best_strategies.json`.
  - **Files:** `scripts/backtest_arena.py`
  - **Action:** Save map: `{"EURUSD": "SteadySniper", "GBPUSD": "TripleTrend"}`.
  - **Verification:** Check generated JSON file structure.

#### Phase 2 Acceptance Criteria:
- [x] `best_strategies.json` generated using Oanda MTF data.

---

### Phase 3: Screener Integration                                            ✅ COMPLETED
**Objective:** Live screener uses the updated data and configs.
**Complexity:** Medium
**Depends On:** Phase 2

#### Tasks:
- [x] **Task 3.1:** Update `ForexScreener` data loading.
  - **Files:** `backend/app/services/forex_screener.py`
  - **Action:** `run_orchestrated_refresh` must ensure 1h/4h data is present. `screen_all` must load all 3 timeframes before calling `detector.analyze`.
  - **Verification:** Print loaded map on startup.

- [x] **Task 3.2:** Implement Dynamic Strategy Selection.
  - **Files:** `backend/app/services/forex_screener.py`
  - **Action:** Load `best_strategies.json` and pick the right detector for each pair.
  - **Verification:** Run screener, verify logs show different strategies.

- [x] **Task 3.3:** Unify Result Formatting.
  - **Files:** `backend/app/services/forex_screener.py`
  - **Action:** Ensure output JSON has a `strategy_used` field.
  - **Verification:** Check `data/processed/forex_signals.json` output.

#### Phase 3 Acceptance Criteria:
- [x] Screener runs without error using multiple input files per symbol.

---

### Phase 4: Validation                                                       ✅ COMPLETED
**Objective:** Final end-to-end check.
**Complexity:** Low
**Depends On:** Phase 3

#### Tasks:
- [x] **Task 4.1:** Run Backtest Arena (Validate Data Loading).
  - **Command:** `python scripts/backtest_arena.py`
- [x] **Task 4.2:** Run Live Screener (Validate Execution).
  - **Command:** `python start.py`

---

## 🔄 Rollback Strategy
- Revert `ForexScreener` to use hardcoded `SniperDetector`.
- Delete `best_strategies.json` and `forex_baskets.json`.
- Restore previous `ForexDetector` and `SniperDetector` logic from git history.

---

## 📊 Task Summary

| Phase | Tasks | Complexity | Status |
|-------|-------|------------|--------|
| Phase 1: Standardization | 4 | Medium | ✅ COMPLETED |
| Phase 2: Backtest Arena | 3 | High | ✅ COMPLETED |
| Phase 3: Screener Integration | 3 | Medium | ✅ COMPLETED |
| Phase 4: Validation | 2 | Low | ✅ COMPLETED |
| **Total** | **12** | - | - |

---

## 📝 Notes
- Oanda data is superior to yfinance for forex as it includes spread and higher tick resolution.
- Ensure the backtester doesn't "look ahead" by using the current 1h/4h candle that hasn't closed yet.