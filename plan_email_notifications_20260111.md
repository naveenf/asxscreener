# Implementation Plan: Email Notifications for Screener Alerts

**Plan ID:** plan_email_notifications_20260111
**Created:** 2026-01-11 10:45
**Author:** Gemini CLI (Plan Mode)
**Status:** 🟢 APPROVED
**Estimated Complexity:** Medium
**Estimated Phases:** 3

---

## 📋 Executive Summary

This plan implements an automated email notification system for the Forex and Stock screeners. It addresses the user's need to be alerted of trading signals even when away from the dashboard. The solution leverages the existing `apscheduler` background task to detect *new* signals and uses a standard SMTP client to send emails to subscribed users. To prevent spam, a "diff" logic will be introduced to only notify on *new* or *changed* signals.

---

## 🔍 Analysis

### Codebase Exploration
- **Scheduler:** Found `apscheduler` in `backend/app/main.py` running `scheduled_forex_refresh` every 15 minutes. This is the ideal hook point.
- **Data Source:** `ForexScreener` and `StockScreener` output JSON files. `ForexScreener.run_orchestrated_refresh` returns the latest results directly.
- **User Store:** Users are stored in Firebase Firestore (`users` collection). Currently, there is no "email preference" field.
- **Configuration:** `backend/app/config.py` uses `pydantic-settings`. SMTP credentials need to be added here.

### Current Architecture
- **Periodic Refresh:** The app refreshes data and runs analysis every 15 minutes.
- **Stateless Analysis:** Currently, each run is independent. To detect "new" signals, we must compare the current run's output with the previous run's output.

### Dependencies Identified
| Dependency | Type | Impact |
|------------|------|--------|
| `smtplib` | Internal (Python Std Lib) | Used for sending emails. No new package install needed. |
| `email.mime` | Internal (Python Std Lib) | Used for constructing HTML emails. |
| `firebase_admin` | Existing | Used to fetch user emails from Firestore. |

### Risks & Considerations
| Risk | Severity | Mitigation |
|------|----------|------------|
| **Spamming Users** | High | Implement strict "diff" logic: only email if `ticker` wasn't in the previous 15-min batch or signal type changed. |
| **Email Blocking** | Medium | Use standard SMTP (e.g., Gmail/Outlook) for MVP. For production, recommend SendGrid/AWS SES. |
| **Performance** | Low | Email sending is I/O bound. It will be run in the async background task, but `smtplib` is blocking. We should run it in a thread pool or use `fastapi-mail` (async) if volume grows. For MVP, synchronous send in background task is acceptable. |

---

## ✅ Implementation Plan

### Phase 1: Configuration & Email Service
**Objective:** Set up the infrastructure to send emails.
**Complexity:** Medium
**Depends On:** None

#### Tasks:
- [ ] **Task 1.1:** Update `backend/app/config.py`
  - **Files:** `backend/app/config.py`
  - **Action:** Modify
  - **Details:** Add `SMTP_SERVER`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `EMAIL_FROM` to `Settings` class.
  - **Verification:** Run `python -c "from backend.app.config import settings; print(settings.SMTP_SERVER)"` (ensure env vars are loaded).

- [ ] **Task 1.2:** Create `EmailService`
  - **Files:** `backend/app/services/notification.py`
  - **Action:** Create
  - **Details:**
    - Class `EmailService`.
    - Method `send_signal_alert(users: List[str], signals: List[Dict])`.
    - Generates a simple HTML table of the signals.
    - Connects to SMTP server and sends individual emails (BCC or loop).
  - **Verification:** Create a temporary test script to send a "Hello World" email to your own address.

#### Phase 1 Acceptance Criteria:
- [ ] App starts without errors with new config.
- [ ] Test script successfully delivers an email.

---

### Phase 2: Logic & Integration
**Objective:** Hook the email service into the scheduler and implement "New Signal" detection.
**Complexity:** Complex
**Depends On:** Phase 1

#### Tasks:
- [ ] **Task 2.1:** Implement Signal Diff Logic
  - **Files:** `backend/app/services/notification.py`
  - **Action:** Modify
  - **Details:**
    - Add logic to cache the `last_signals` (can be in-memory variable in the module or a small JSON file `data/processed/last_sent.json`).
    - Method `filter_new_signals(current_signals: List[Dict]) -> List[Dict]`.
    - Returns only signals that were NOT in the last successful notification batch.
  - **Verification:** Unit test: Pass list A, then list A + B. Ensure only B is returned.

- [ ] **Task 2.2:** Update Scheduler in `main.py`
  - **Files:** `backend/app/main.py`
  - **Action:** Modify
  - **Details:**
    - Import `EmailService` and `db` (Firestore).
    - In `scheduled_forex_refresh`:
      1. Capture `current_results`.
      2. Call `EmailService.filter_new_signals(current_results['signals'])`.
      3. If new signals exist:
         - Query Firestore for all users (or filtered users).
         - Call `EmailService.send_signal_alert`.
  - **Verification:** Trigger the scheduled task manually (or wait 15 mins) and verify an email is sent ONLY for new signals.

#### Phase 2 Acceptance Criteria:
- [ ] Running the scheduler twice with the same data results in ONE email (the first time).
- [ ] Adding a new signal results in a second email containing ONLY the new signal.

---

### Phase 3: User Preferences (Optional but Recommended)
**Objective:** Allow users to opt-in/out of emails.
**Complexity:** Low
**Depends On:** Phase 1

#### Tasks:
- [ ] **Task 3.1:** Update Auth/User Model
  - **Files:** `backend/app/api/auth.py`
  - **Action:** Modify
  - **Details:** When creating a user, default `email_notifications` to `False` (safe default) or `True`.
- [ ] **Task 3.2:** Update Notification Logic
  - **Files:** `backend/app/main.py`
  - **Action:** Modify
  - **Details:** Filter Firestore query: `db.collection('users').where('email_notifications', '==', True).stream()`.

---
