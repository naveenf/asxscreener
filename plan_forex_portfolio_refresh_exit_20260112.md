# Implementation Plan: Forex Portfolio Price Refresh & Exit Signals

**Plan ID:** plan_forex_portfolio_refresh_exit_20260112
**Created:** 2026-01-12 10:20
**Author:** Gemini CLI (Plan Mode)
**Status:** ✅ IMPLEMENTED
**Completed:** 2026-01-12 11:00
**Estimated Complexity:** High
**Estimated Phases:** 3

---

## 📋 Executive Summary

This plan implements real-time OANDA price monitoring and automated exit signal detection for the Forex Portfolio. We will introduce an "Instant Price" refresh button using OANDA's API and an automated "Check Exits" feature that runs on page load. This checks open positions against their specific strategy rules (defaulting to Squeeze for legacy items). Exit signals will persist in the database and trigger email notifications, remaining until the user manually closes the position.

---

## 🔍 Analysis

### Codebase Exploration
*   **Models:** `ForexPortfolioItemCreate` and `ForexPortfolioItemResponse` in `backend/app/models/forex_portfolio_schema.py` need fields for `timeframe`, `strategy`, `exit_signal`, and `exit_reason`.
*   **Strategies:** `SqueezeDetector` needs an explicit `check_exit` method.
*   **Data:** `forex_pairs.json` maps symbols. OANDA API is used for data in `scripts/download_forex.py`.
*   **Frontend:** `Portfolio.jsx` needs to trigger exit checks automatically and display OANDA prices.

### Current Architecture
*   **Portfolio Storage:** Firestore (via `forex_portfolio.py`).
*   **Price Data:** Currently using `download_forex.py` (OANDA) for candles. Will add real-time fetch.
*   **Notifications:** `EmailService` exists.

### Dependencies Identified
| Dependency | Type | Impact |
|------------|------|--------|
| `oandapyV20` | Library | Used for "Instant Price" fetching (replacing YFinance proposal). |
| `pandas` | Library | Used for strategy analysis. |
| `ForexStrategy` | Interface | Requires `check_exit` method. |

### Risks & Considerations
| Risk | Severity | Mitigation |
|------|----------|------------|
| **OANDA Rate Limits** | Medium | "Instant Price" checks should be debounced or user-triggered (button) to avoid spamming OANDA API. |
| **Legacy Data** | Low | Existing items lack strategy info. Logic will default them to "Squeeze" as requested. |
| **Performance** | Medium | Auto-checking exits on load for large portfolios might be slow. We will process asynchronously if needed, but synchronous for now (MVP). |

---

## ✅ Implementation Plan

### Phase 1: Backend Core & Strategy Logic
**Objective:** Enable storage of strategy context and implement the exit logic engine.
**Complexity:** High
**Depends On:** None

#### Tasks:
- [x] **Task 1.1:** Update `ForexPortfolioItem` Models
  - **Files:** `backend/app/models/forex_portfolio_schema.py`
  - **Action:** Modify
  - **Details:** Add `timeframe` (str), `strategy` (str), `exit_signal` (bool, default False), `exit_reason` (str) to Create and Response models.
  - **Verification:** `pytest` or manual instantiation check.

- [x] **Task 1.2:** Update `ForexStrategy` Interface
  - **Files:** `backend/app/services/strategy_interface.py`
  - **Action:** Modify
  - **Details:** Add abstract method `check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]`.
  - **Verification:** Code compiles.

- [x] **Task 1.3:** Implement `check_exit` in `SqueezeDetector`
  - **Files:** `backend/app/services/squeeze_detector.py`
  - **Action:** Modify
  - **Details:**
    - Logic:
      - BUY Exit: Close < BB_Middle (SMA 20)
      - SELL Exit: Close > BB_Middle (SMA 20)
    - Returns: `{"exit_signal": True, "reason": "Price crossed BB Middle"}`
  - **Verification:** Unit test with mock DataFrame.

- [x] **Task 1.4:** Update `ForexDetector` (Placeholder/Basic)
  - **Files:** `backend/app/services/forex_detector.py`
  - **Action:** Modify
  - **Details:** Implement basic trend exit (Cross EMA34) to satisfy interface, though primarily unused for Forex.
  - **Verification:** Code compiles.

- [x] **Task 1.5:** Create `PortfolioMonitor` Service
  - **Files:** `backend/app/services/portfolio_monitor.py`
  - **Action:** Create
  - **Details:**
    - Method `check_portfolio_exits(user_email)`
    - Iterates open items.
    - Defaults strategy to "Squeeze" if missing.
    - Loads data (reuse `ForexScreener` data loading logic).
    - Calls `strategy.check_exit`.
    - **Persist Result:** If exit found, update Firestore document (`exit_signal=True`, `exit_reason=...`).
    - Sends email via `EmailService.send_exit_alert` (only if signal is *newly* detected).
  - **Verification:** Manual run via Python shell.

- [x] **Task 1.6:** Update Portfolio API for Exit Checks
  - **Files:** `backend/app/api/forex_portfolio.py`
  - **Action:** Modify
  - **Details:**
    - Update `add_forex_item` to save `strategy` and `timeframe`.
    - Add `POST /check-exits` endpoint calling `PortfolioMonitor`.
  - **Verification:** Curl request to endpoint.

#### Phase 1 Acceptance Criteria:
- [x] Portfolio items store strategy/timeframe.
- [x] `SqueezeDetector` correctly identifies exits based on BB Middle.
- [x] `check-exits` endpoint updates DB with exit signals.

---

### Phase 2: Instant Price (OANDA) & Data Refresh
**Objective:** Provide real-time pricing data via API using OANDA.
**Complexity:** Medium
**Depends On:** None

#### Tasks:
- [x] **Task 2.1:** Create OANDA Price Service
  - **Files:** `backend/app/services/oanda_price.py`
  - **Action:** Create
  - **Details:**
    - Adapt `get_oanda_api` from `scripts/download_forex.py`.
    - Method `get_current_price(symbol)`:
      - Use `instruments.InstrumentsCandles` with `count=1`, `granularity=S5` (or `M1`).
      - Return the "Close" of the latest candle.
  - **Verification:** Python shell test.

- [x] **Task 2.2:** Add Instant Price Endpoint
  - **Files:** `backend/app/api/forex.py`
  - **Action:** Modify
  - **Details:**
    - Add `GET /price/{symbol}`.
    - Call `OandaPriceService.get_current_price`.
  - **Verification:** `curl` returns OANDA price.

- [x] **Task 2.3:** Update Frontend API Service
  - **Files:** `frontend/src/services/api.js`
  - **Action:** Modify
  - **Details:** Add `fetchForexPrice(symbol)` and `checkPortfolioExits()`.
  - **Verification:** Functions available in frontend.

#### Phase 2 Acceptance Criteria:
- [x] API returns live OANDA price.
- [x] Falls back gracefully if OANDA token is missing/invalid.

---

### Phase 3: Frontend Integration
**Objective:** Update UI to capture strategy context and display price/exit signals.
**Complexity:** Medium
**Depends On:** Phase 1 & 2

#### Tasks:
- [x] **Task 3.1:** Update `AddForexModal`
  - **Files:** `frontend/src/components/AddForexModal.jsx`
  - **Action:** Modify
  - **Details:**
    - Accept `strategy` and `timeframe` from `forex` prop.
    - Include these in the POST payload.
    - Logic: If adding from screener, pre-fill these.
  - **Verification:** Adding a signal saves context to DB.

- [x] **Task 3.2:** Update `Portfolio` Component (Exits)
  - **Files:** `frontend/src/components/Portfolio.jsx`
  - **Action:** Modify
  - **Details:**
    - `useEffect`: Call `checkPortfolioExits` on mount.
    - Display "Checking exits..." loading state (non-blocking if possible, or small indicator).
    - Render **RED WARNING** badge/row highlight if `item.exit_signal` is True.
  - **Verification:** Load page, see exit alerts if applicable.

- [x] **Task 3.3:** Update `Portfolio` Component (Instant Price)
  - **Files:** `frontend/src/components/Portfolio.jsx`
  - **Action:** Modify
  - **Details:**
    - Add "Refresh Price" icon/button next to current price.
    - `onClick`: Call `fetchForexPrice`, update local state for that item temporarily.
  - **Verification:** Click refresh, see price update.

#### Phase 3 Acceptance Criteria:
- [x] Page load triggers backend exit check.
- [x] User sees persistent "EXIT SIGNAL" alerts from DB.
- [x] "Instant Price" button updates the displayed price.

---

## 📊 Task Summary

| Phase | Tasks | Complexity | Status |
|-------|-------|------------|--------|
| Phase 1: Backend Core | 6 | High | ⬜ Pending |
| Phase 2: Instant Price | 3 | Medium | ⬜ Pending |
| Phase 3: Frontend | 3 | Medium | ⬜ Pending |
| **Total** | **12** | - | - |

---

## 🔄 Rollback Strategy

1.  **Database:** New fields are optional/additive. No rollback needed.
2.  **Code:** `git reset --hard` if critical failures occur.
3.  **Strategy:** If `check_exit` is buggy, revert `strategy_interface.py` changes and return `None` in implementations.

