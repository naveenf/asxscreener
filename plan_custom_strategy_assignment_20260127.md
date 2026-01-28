
# Implementation Plan: Custom Intraday Strategy Assignment (Silver Sniper & 1H Squeeze)

**Plan ID:** plan_custom_strategy_assignment_20260127
**Created:** 2026-01-27 22:15
**Author:** Gemini CLI (Plan Mode)
**Status:** 🟢 APPROVED
**Estimated Complexity:** Medium
**Estimated Phases:** 3

---

## 📋 Executive Summary

This plan updates the main screening engine to use specialized strategies based on asset type. **XAG_USD (Silver)**, **BCO_USD (Oil)**, and **WHEAT_USD** will use the **Silver Sniper** strategy (5m base, 15m HTF). All other assets will default to the **Squeeze** strategy on a **1-hour** base timeframe. We will also perform a quick optimization to find the best Target RR for the 1H Squeeze assets and ensure the UI clearly displays which algorithm generated each signal.

---

## 🔍 Analysis

### Codebase Exploration
- **`backend/app/services/forex_screener.py`**: Orchestrates screening. Needs to load 5m data and support the `SilverSniper` name.
- **`frontend/src/components/SignalCard.jsx`**: Needs to be verified to ensure it displays the `strategy` field clearly to the user.
- **`scripts/squeeze_test.py`**: Can be used to quickly test RR for 1H Squeeze assets.

### Current Architecture
- Metadata-driven strategy selection via `best_strategies.json`.
- Frontend receives a list of signal objects containing a `strategy` key.

---

## ✅ Implementation Plan

### Phase 1: Engine & Data Support                     ✅ COMPLETED
**Objective:** Enable granular data loading and register the new strategy.
**Complexity:** Medium
**Depends On:** None

#### Tasks:
- [x] **Task 1.1:** Register `SilverSniperDetector` in `ForexScreener`. ✅ [2026-01-27 22:25]
  - **Files:** `backend/app/services/forex_screener.py`
  - **Action:** Modify
  - **Details:** Import `SilverSniperDetector` and add to `self.strategies`.
  - **Verification:** Start backend, no errors.

- [x] **Task 1.2:** Update `_load_data_mtf` to fetch 5m data`. ✅ [2026-01-27 22:26]
  - **Files:** `backend/app/services/forex_screener.py`
  - **Action:** Modify
  - **Details:** Ensure `5_Min` CSVs are loaded into the data dictionary.
  - **Verification:** Run a debug print during refresh.

- [x] **Task 1.3:** Update timeframe mapping logic in `screen_all`. ✅ [2026-01-27 22:27]
  - **Files:** `backend/app/services/forex_screener.py`
  - **Action:** Modify
  - **Details:** Map `timeframe: 5m` -> `base=5m, htf=15m`.
  - **Verification:** Logic check.

#### Phase 1 Acceptance Criteria:
- [x] `ForexScreener` supports 5m/15m MTF pairs`. ✅

---

### Phase 2: RR Optimization (1H Squeeze)
**Objective:** Determine the best Target RR for the remaining assets on 1H.
**Complexity:** Medium
**Depends On:** None

#### Tasks:
- [ ] **Task 2.1:** Run RR Optimization Script.
  - **Files:** `scripts/optimize_1h_rr.py` (New)
  - **Action:** Create & Run
  - **Details:** Test Squeeze strategy on 1H data for non-sniper assets (Gold, Nasdaq, Forex) with RR values of 1.5, 2.0, and 3.0.
  - **Verification:** Analyze output for the best Win Rate / Profit combo.

#### Phase 2 Acceptance Criteria:
- [ ] Best RR for 1H Squeeze identified and documented.

---

### Phase 3: Deployment & UI Verification
**Objective:** Apply new mappings and ensure user visibility.
**Complexity:** Simple
**Depends On:** Phase 1, Phase 2

#### Tasks:
- [ ] **Task 3.1:** Update `data/metadata/best_strategies.json`.
  - **Files:** `data/metadata/best_strategies.json`
  - **Action:** Modify
  - **Details:** 
    - XAG, BCO, WHEAT -> `SilverSniper` (5m, 3.0 RR).
    - Others -> `Squeeze` (1H, Optimized RR).
  - **Verification:** Inspect file.

- [ ] **Task 3.2:** Verify Signal Card UI.
  - **Files:** `frontend/src/components/SignalCard.jsx`
  - **Action:** Read/Modify
  - **Details:** Ensure the `strategy` name (e.g., "SilverSniper" or "Squeeze") is visible on the dashboard card.
  - **Verification:** Open UI, see labels.

#### Phase 3 Acceptance Criteria:
- [ ] Dashboard shows signals using the specific assigned algorithms.
- [ ] User can clearly distinguish between "SilverSniper" and "Squeeze" signals.

---

## ❓ Open Points (Resolutions)

- **Target RR:** 3.0 for Snipers; Optimized (1.5 - 2.0 range) for 1H Squeeze based on Phase 2 results.
- **UI Visibility:** Labels will be added/verified on Signal Cards.

---

## 📊 Task Summary

| Phase | Tasks | Complexity | Status |
|-------|-------|------------|--------|
| Phase 1: Engine Support | 3 | Medium | ⬜ Pending |
| Phase 2: RR Optimization | 1 | Medium | ⬜ Pending |
| Phase 3: Deployment & UI | 2 | Simple | ⬜ Pending |
| **Total** | **6** | - | - |

---

## ⏳ AWAITING YOUR APPROVAL

**Ready for implementation.**
To begin, run:
`/implement plan_custom_strategy_assignment_20260127.md`
