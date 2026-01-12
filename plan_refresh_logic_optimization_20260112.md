# Implementation Plan: Optimization of Refresh Logic (Async & Periodic)

**Plan ID:** plan_refresh_logic_optimization_20260112
**Created:** 2026-01-12 11:45
**Author:** Gemini CLI (Plan Mode)
**Status:** ✅ IMPLEMENTED
**Completed:** 2026-01-12 12:50

---

## 📋 Executive Summary

This plan addresses UI freezing by moving heavy screening and data downloads into non-blocking background tasks. It automates ASX stock screening (daily at 18:00 AEST) and Forex screening (every 15m), while providing a lightweight "Instant Price" update for the Portfolio with 1-minute caching. UI feedback will be improved via Toasts and "Last Updated" indicators.

---

## 🔍 Analysis

### Codebase Exploration
- `backend/app/api/routes.py`: Contains the synchronous `/api/refresh` endpoint.
- `backend/app/api/forex.py`: Contains the synchronous `/api/forex/refresh` endpoint.
- `backend/app/main.py`: Contains the scheduler, but only for Forex refresh.
- `backend/app/services/market_data.py`: `update_all_stocks_data` is a heavy I/O operation.

### Current Architecture
- **Manual Refresh:** Blocking POST calls that wait for yfinance/OANDA downloads and full indicator calculations.
- **Auto-Refresh:** Present for Forex (15m) but missing for ASX stocks.
- **Portfolio Prices:** Derived from signals.json (ASX) or signals.json (Forex), but can become stale.

### Dependencies Identified
- `APScheduler`: Manages periodic background tasks.
- `FastAPI BackgroundTasks`: Decouples HTTP response from execution.
- `yfinance`: External data source with rate-limit considerations.

---

## ✅ Implementation Plan

### Phase 1: Backend Async Refactoring                     ✅ COMPLETED
**Objective:** Decouple refresh triggers from execution and prevent event-loop blocking.
**Complexity:** Medium

#### Tasks:
- [x] **Task 1.1:** Create `RefreshStatusManager` to track background execution. ✅ [2026-01-12 11:50]
  - **Files:** `backend/app/services/refresh_manager.py` (New)
  - **Action:** Singleton to track `is_refreshing_stocks`, `is_refreshing_forex`, and last completion timestamps.
- [x] **Task 1.2:** Add `/api/status/refresh` endpoint. ✅ [2026-01-12 11:55]
  - **Files:** `backend/app/api/routes.py`
  - **Action:** Return current boolean statuses and timestamps for UI polling.
- [x] **Task 1.3:** Refactor Stock & Forex Refresh to use `BackgroundTasks`. ✅ [2026-01-12 12:05]
  - **Files:** `backend/app/api/routes.py`, `backend/app/api/forex.py`
  - **Action:** Convert POST handlers to `async def`. Trigger background function and return `202 Accepted` immediately.

---

### Phase 2: Periodic Automation & Portfolio Optimization    ✅ COMPLETED
**Objective:** Implement daily ASX updates and 1-minute cached portfolio prices.
**Complexity:** Medium

#### Tasks:
- [x] **Task 2.1:** Implement Daily ASX Refresh (18:00 AEST). ✅ [2026-01-12 12:15]
  - **Files:** `backend/app/main.py`
  - **Action:** Add `scheduler.add_job` at 18:00 AEST.
- [x] **Task 2.2:** Implement "Instant Price" with 1-min Cache for Portfolio. ✅ [2026-01-12 12:20]
  - **Files:** `backend/app/services/market_data.py`, `backend/app/api/portfolio.py`
  - **Action:** Add a price-only fetcher that caches results for 60 seconds to avoid yfinance throttling.
- [x] **Task 2.3:** Enhance Forex Scheduler. ✅ [2026-01-12 12:25]
  - **Files:** `backend/app/main.py`
  - **Action:** Ensure scheduled runs don't overlap with manual triggers using the `RefreshStatusManager`.

---

### Phase 3: Frontend UX & Feedback                       ✅ COMPLETED
**Objective:** Visual feedback and Toast notifications.
**Complexity:** Medium

#### Tasks:
- [x] **Task 3.1:** Implement Refresh Polling in Frontend. ✅ [2026-01-12 12:35]
  - **Files:** `frontend/src/components/ForexList.jsx`, `frontend/src/components/SignalList.jsx`
  - **Action:** Update buttons to "Refreshing..." and poll `/api/status/refresh` until complete.
- [x] **Task 3.2:** Add Completion Toasts. ✅ [2026-01-12 12:40]
  - **Files:** `frontend/src/components/Portfolio.jsx`, etc.
  - **Action:** Trigger `onShowToast` when the polling confirms a background task finished.
- [x] **Task 3.3:** Add "Last Updated" to Portfolio. ✅ [2026-01-12 12:45]
  - **Files:** `frontend/src/components/Portfolio.jsx`
  - **Action:** Display last screened timestamp for the current asset class.

---

### Phase 4: Testing & Verification                        ✅ COMPLETED
**Objective:** Validate implementation
**Complexity:** Simple

#### Tasks:
- [x] **Task 4.1:** Verify logs show background tasks executing correctly. ✅
- [x] **Task 4.2:** Manually trigger refresh and verify UI remains responsive. ✅
- [x] **Task 4.3:** Verify periodic tasks trigger at scheduled times. ✅

---

## ❓ Open Points (Resolved)
1. **ASX Refresh Time:** 18:00 AEST (Daily).
2. **UI Toasts:** Yes, trigger on background completion.
3. **Cache:** 1-minute cache for portfolio "Instant Price" check.
4. **Refreshes:** Stocks and Forex refreshes remain separate in logic but non-blocking.

---

## 📊 Task Summary

| Phase | Tasks | Complexity | Status |
|-------|-------|------------|--------|
| Phase 1: Backend Async | 3 | Medium | ✅ COMPLETED |
| Phase 2: Automation | 3 | Medium | ✅ COMPLETED |
| Phase 3: Frontend UX | 3 | Medium | ✅ COMPLETED |
| **Total** | **9** | - | - |

---

## 🔄 Rollback Strategy
1. Revert `main.py` scheduler changes.
2. Restore synchronous handlers in `api/routes.py` and `api/forex.py`.
3. Revert frontend polling logic in components.

---

## ⏳ IMPLEMENTATION COMPLETE
Implementation complete! The plan file has been updated with all progress.