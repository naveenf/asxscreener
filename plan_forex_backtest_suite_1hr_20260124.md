# Implementation Plan: Forex Backtest Suite (1HR - Squeeze Only)

**Plan ID:** plan_forex_backtest_suite_1hr_20260124
**Created:** 2026-01-24 12:35
**Author:** Gemini CLI (Plan Mode)
**Status:** ✅ APPROVED
**Estimated Complexity:** Medium
**Estimated Phases:** 3

---

## 📋 Executive Summary
This plan implements a high-performance backtesting script to evaluate all Forex pairs, Commodities, and Indices using the 1-hour (1H) timeframe. Following user direction, the suite will exclusively utilize the **Squeeze Strategy** (Volatility Compression) and implement a **Trailing Stop Loss** mechanism to optimize profit capture. The backtest will incorporate differentiated spread costs based on asset class (Forex, Indices, Commodities) to reflect OANDA's market depth and liquidity.

---

## 🔍 Analysis

### Codebase Exploration
- **Strategy:** `SqueezeDetector` in `backend/app/services/squeeze_detector.py` uses Bollinger Band width and MTF confirmation.
- **Data:** 1H data is stored as `{Symbol}_1_Hour.csv` in `data/forex_raw/`.
- **Indicators:** `TechnicalIndicators` service provides the necessary BB and ATR calculations for trailing logic.

### Dependencies Identified
| Dependency | Type | Impact |
|------------|------|--------|
| `data/forex_raw/*.csv` | Data | Historical source for 1H bars. |
| `SqueezeDetector` | Logic | Core entry logic for all pairs. |
| `best_strategies.json`| Config | Source for `target_rr` parameters. |

### Risks & Considerations
| Risk | Severity | Mitigation |
|------|----------|------------|
| Trailing SL Complexity | Medium | Use a standard "High-Water Mark" trailing logic (SL moves up with price, never down). |
| Spread Calculation | Medium | Implement an asset-class lookup table to apply correct costs (Pips for FX, Points for Indices). |

---

## ✅ Implementation Plan

### Phase 1: Environment & Logic Setup                 ✅ COMPLETED
**Objective:** Prepare data class and asset-specific configurations.
**Complexity:** Simple
**Depends On:** None

#### Tasks:
- [x] **Task 1.1:** Define Spread & Tick Configuration. ✅ [2026-01-24 12:43]
- [x] **Task 1.2:** Initialize Squeeze Strategy for Backtesting. ✅ [2026-01-24 12:46]
  - **Files:** `scripts/backtest_all_pairs_1hr.py`
  - **Action:** Create script and import `SqueezeDetector`.
  - **Verification:** Ensure the script can load the strategy and metadata correctly.

#### Phase 1 Acceptance Criteria:
- [x] Script skeleton exists with asset-class spread logic. ✅
- [x] Metadata for `target_rr` is successfully loaded. ✅

---

### Phase 2: Engine Development (Trailing SL & Squeeze)    🔄 IN PROGRESS
**Objective:** Implement the core backtest loop with Trailing SL.
**Complexity:** Medium
**Depends On:** Phase 1

#### Tasks:
- [x] **Task 2.1:** Implement Trailing Stop Loss Logic. ✅ [2026-01-24 12:54]
  - **Details:** When a Squeeze signal triggers an entry:
    - Set Initial SL as per Strategy (BB Middle).
    - As price moves toward TP (based on `target_rr`), the SL "trails" at a fixed distance or moves to Break-Even at a certain threshold.
  - **Verification:** Verify SL movement logic with unit tests or log traces.
- [x] **Task 2.2:** Multi-Pair 1H Loop. ✅ [2026-01-24 13:08]
  - **Details:** Iterate through all pairs in `forex_pairs.json`.
  - **Details:** Load `_1_Hour.csv` and process the *entire* available dataset.
  - **Verification:** Script processes multiple files sequentially with progress tracking (`tqdm`).
- [ ] **Task 2.3:** Success Metric Calculation.
  - **Details:** Success % = (Trades hitting TP or Trailed Profit) / Total Trades.
  - **Details:** Calculate Net PnL (AUD) and Profit Factor.
  - **Verification:** Print results per pair to console.

#### Phase 2 Acceptance Criteria:
- Trailing SL logic correctly triggers and captures profit.
- All pairs are processed on the 1H timeframe.

---

### Phase 3: Reporting & Review
**Objective:** Final validation and results persistence.
**Complexity:** Simple
**Depends On:** Phase 2

#### Tasks:
- [ ] **Task 3.1:** Export Results to JSON.
  - **Files:** `data/metadata/backtest_results_1hr_squeeze.json`
  - **Verification:** Ensure results include Win Rate, Avg R:R, and Total Trades.
- [ ] **Task 3.2:** Generate Summary Report.
  - **Details:** Print a ranked list of pairs where the 1H Squeeze strategy is most effective.
  - **Verification:** Review report for architectural soundness.

#### Phase 3 Acceptance Criteria:
- Final report lists Success Percent and R:R for all pairs.
- Results are saved for future strategy optimization.

---

## ❓ Open Points (ADDRESSED)

1. **R:R Selection:** Dynamic (Uses `target_rr` from `best_strategies.json`).
2. **Strategy Selection:** Squeeze strategy only.
3. **Exit Method:** Trailing Stop Loss.
4. **Spread Model:** Differentiated (FX: ~1.2 pips, Indices: ~1pt, Commodities: ~2pts).

---

## 📊 Task Summary

| Phase | Tasks | Complexity | Status |
|-------|-------|------------|--------|
| Phase 1: Environment Setup | 2 | Simple | ⬜ Pending |
| Phase 2: Engine Development | 3 | Medium | ⬜ Pending |
| Phase 3: Reporting & Review | 2 | Simple | ⬜ Pending |
| **Total** | **7** | - | - |

---

## 🔄 Rollback Strategy
- Deletion of `scripts/backtest_all_pairs_1hr.py`.
- No modifications to production `backend/` services or database.

---

## ⏳ READY FOR IMPLEMENTATION
Plan is approved. Use `/implement plan_forex_backtest_suite_1hr_20260124.md` to begin.
