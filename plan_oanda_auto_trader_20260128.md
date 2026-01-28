# Implementation Plan: Oanda Auto-Trading Bot

**Plan ID:** plan_oanda_auto_trader_20260128
**Created:** 2026-01-28 14:30
**Author:** Gemini CLI
**Status:** ✅ IMPLEMENTED
**Completed:** 2026-01-28 14:55

---

## 📋 Executive Summary
This plan implements an autonomous trading bot integrated with Oanda. It monitors forex/commodity signals, calculates position sizes using a 2% risk model (AUD), and executes trades for `naveenf.opt@gmail.com`. It includes a dedicated verification phase for account connectivity and a dummy trade on Silver (XAG_USD) to ensure end-to-end functionality.

---

## 🔍 Analysis

### Codebase Exploration
- **Configuration:** `backend/app/config.py` handles environment variables.
- **Oanda Integration:** `backend/app/services/oanda_price.py` uses `oandapyV20`.
- **Screener:** `backend/app/services/forex_screener.py` generates signals with SL/TP.
- **Portfolio:** `backend/app/api/forex_portfolio.py` manages Firestore trade records.

### Technical Parameters
- **Authorized User:** `naveenf.opt@gmail.com`
- **Account ID:** `001-011-5746119-001`
- **Account Currency:** AUD
- **Risk Model:** 2% of balance per trade.
- **Leverage:** 50:1 (to be verified per instrument via API).
- **Concurrent Limit:** Max 3 open automated trades.

---

## ✅ Implementation Plan

### Phase 1: Configuration & Connectivity Test          ✅ COMPLETED
**Objective:** Establish secure connection and verify account access.
**Complexity:** Medium

#### Tasks:
- [x] **Task 1.1:** Update `backend/app/config.py` with trading-specific settings. ✅ [2026-01-28 14:38]
  - **Files:** `backend/app/config.py`
  - **Details:** Add `OANDA_ACCOUNT_ID`, `AUTHORIZED_AUTO_TRADER_EMAIL`, and `MAX_CONCURRENT_TRADES`.
- [x] **Task 1.2:** Create a connectivity diagnostic script. ✅ [2026-01-28 14:42]
  - **Files:** `scripts/test_oanda_connection.py`
  - **Action:** create
  - **Details:** Fetch account summary (balance, NAV) and list available instruments with their margin rates.
  - **Verification:** Run script and confirm balance matches Oanda dashboard.

### Phase 2: Oanda Service Expansion                  ✅ COMPLETED
**Objective:** Implement order execution and instrument detail fetching.
**Complexity:** Medium

#### Tasks:
- [x] **Task 2.1:** Expand `OandaPriceService` with trading methods. ✅ [2026-01-28 14:45]
  - **Files:** `backend/app/services/oanda_price.py`
  - **Details:** Implement `get_account_details()`, `get_instrument_info(symbol)`, and `place_market_order(symbol, units, sl, tp)`.
- [x] **Task 2.2:** Implement unit calculation logic. ✅ [2026-01-28 14:49]
  - **Files:** `backend/app/services/oanda_trade_service.py`
  - **Details:** Formula: `Units = (Balance * 0.02) / (SL_Distance_in_Quote * Conversion_to_AUD)`.

### Phase 3: Trade Orchestrator & Portfolio Sync          ✅ COMPLETED
**Objective:** Handle ranking, execution, and database logging.
**Complexity:** Complex

#### Tasks:
- [x] **Task 3.1:** Implement the `OandaTradeService` orchestrator. ✅ [2026-01-28 14:49]
  - **Files:** `backend/app/services/oanda_trade_service.py`
  - **Details:** 
    - Sort signals by `score` (Backtest performance).
    - Limit to top 3 signals.
    - Check for existing positions in Firestore to avoid duplicates.
- [x] **Task 3.2:** Automate Portfolio entries. ✅ [2026-01-28 14:49]
  - **Files:** `backend/app/services/oanda_trade_service.py`
  - **Details:** Upon successful Oanda response, write trade details to `users/naveenf.opt@gmail.com/forex_portfolio`.

### Phase 4: Integration with Refresh Cycle              ✅ COMPLETED
**Objective:** Enable the bot to run during the 15-minute refresh.
**Complexity:** Simple

#### Tasks:
- [x] **Task 4.1:** Update `run_forex_refresh_task` in `tasks.py`. ✅ [2026-01-28 14:52]
  - **Files:** `backend/app/services/tasks.py`
  - **Details:** Trigger `OandaTradeService.execute_trades(signals)` after screening.

### Phase 5: Live Verification (Silver Dummy Trade)        ✅ COMPLETED
**Objective:** Perform a real-world test with minimal risk.
**Complexity:** Medium

#### Tasks:
- [x] **Task 5.1:** Execute Dummy Trade on Silver (XAG_USD). ✅ [2026-01-28 14:55]
  - **Action:** Manual Trigger or Script.
  - **Details:** Open a trade for 1 unit of Silver, verify it appears in Oanda and the Portfolio UI, then close it immediately.

---

## ❓ Open Points (CLOSED)
1. **Leverage:** 50:1 confirmed; code will fetch dynamic margin rates from Oanda to be safe.
2. **Ranking:** Signals will be prioritized by the `score` field (based on backtest results).

---

## 📊 Task Summary
| Phase | Tasks | Complexity | Status |
|-------|-------|------------|--------|
| Phase 1: Connectivity | 2 | Medium | ✅ Completed |
| Phase 2: Oanda Service | 2 | Medium | ✅ Completed |
| Phase 3: Orchestration | 2 | Complex | ✅ Completed |
| Phase 4: Integration | 1 | Simple | ✅ Completed |
| Phase 5: Live Test | 1 | Medium | ✅ Completed |
| **Total** | **8** | - | - |

---

## 📝 Notes
- Ensure `OANDA_ENV` is set to `live` in `.env` for the final test.
- The 2% risk calculation must account for the AUD conversion if the pair quote currency is not AUD (e.g., USD, JPY).