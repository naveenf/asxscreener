# Strategy Toggle Settings Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a Settings page where a logged-in user can enable/disable individual pair+strategy combos, with the cron job respecting those choices.

**Architecture:** Preferences stored in Firestore under `config/strategy_overrides` as a `disabled` list of `"PAIR::Strategy"` keys. Backend reads these at the start of each cron run and filters the screener accordingly. Frontend shows a Settings page (new nav tab) with toggles grouped by pair.

**Tech Stack:** FastAPI (Python), Firestore Admin SDK, React 18, CSS Modules

---

## Task 1: Backend — Settings API endpoint

**Files:**
- Create: `backend/app/api/settings.py`
- Modify: `backend/app/api/routes.py` (add 1 line to register router)

### Step 1: Create `backend/app/api/settings.py`

```python
"""
Settings Routes

Global screener configuration managed by the admin user.
"""

import json
import logging
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel
from typing import List
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from firebase_admin import firestore

from ..firebase_setup import db
from ..config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings")

BEST_STRATEGIES_PATH = Path(__file__).parent.parent.parent.parent / "data" / "metadata" / "best_strategies.json"


async def get_current_user_email(authorization: str = Header(...)) -> str:
    """Dependency to verify Google ID token and return email."""
    try:
        token = authorization.replace("Bearer ", "")
        id_info = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            settings.GOOGLE_CLIENT_ID
        )
        email = id_info.get("email")
        if not email:
            raise HTTPException(status_code=401, detail="Email missing from token")
        return email
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def _build_combos(disabled: set) -> List[dict]:
    """
    Parse best_strategies.json and return full combo list with enabled/disabled status.
    Each combo is identified by 'PAIR::StrategyName'.
    """
    combos = []
    try:
        with open(BEST_STRATEGIES_PATH, "r") as f:
            strategy_map = json.load(f)
    except Exception as e:
        logger.error(f"Failed to read best_strategies.json: {e}")
        return combos

    for pair, config in strategy_map.items():
        strategies_list = config.get("strategies", [config]) if "strategies" not in config else config["strategies"]
        for s in strategies_list:
            strategy_name = s.get("strategy", "Unknown")
            timeframe = s.get("timeframe", "?")
            key = f"{pair}::{strategy_name}"
            combos.append({
                "key": key,
                "pair": pair,
                "strategy": strategy_name,
                "timeframe": timeframe,
                "enabled": key not in disabled
            })

    return combos


@router.get("/strategy-overrides")
async def get_strategy_overrides(email: str = Depends(get_current_user_email)):
    """
    Return all pair+strategy combos with their enabled/disabled state.
    Any logged-in user can read this.
    """
    disabled = set()
    try:
        doc = db.collection("config").document("strategy_overrides").get()
        if doc.exists:
            disabled = set(doc.to_dict().get("disabled", []))
    except Exception as e:
        logger.warning(f"Could not read strategy_overrides from Firestore: {e}")

    combos = _build_combos(disabled)
    return {"combos": combos, "disabled": list(disabled)}


class StrategyOverridesUpdate(BaseModel):
    disabled: List[str]


@router.put("/strategy-overrides")
async def update_strategy_overrides(
    body: StrategyOverridesUpdate,
    email: str = Depends(get_current_user_email)
):
    """
    Update the global disabled strategy list.
    Only the authorized auto-trader email can write.
    """
    if email != settings.AUTHORIZED_AUTO_TRADER_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required")

    try:
        db.collection("config").document("strategy_overrides").set({
            "disabled": body.disabled,
            "updated_by": email,
            "updated_at": firestore.SERVER_TIMESTAMP
        })
        logger.info(f"Strategy overrides updated by {email}: {len(body.disabled)} disabled")
        return {"success": True, "disabled": body.disabled}
    except Exception as e:
        logger.error(f"Failed to update strategy_overrides: {e}")
        raise HTTPException(status_code=500, detail="Failed to save overrides")
```

### Step 2: Register the router in `backend/app/api/routes.py`

Add these two lines in the imports + include block:

```python
# After the existing imports at top:
from . import settings as settings_api   # Import settings router

# After the existing router.include_router(...) calls:
router.include_router(settings_api.router)
```

Exact diff — add after line 24 (`from . import forex_portfolio`):
```
from . import settings as settings_api
```

Add after line 40 (`router.include_router(forex_portfolio.router)`):
```
router.include_router(settings_api.router)
```

### Step 3: Manual test (no unit tests needed — Firestore integration)

Start the backend: `cd backend && uvicorn app.main:app --reload`

Test GET (requires valid Google token from browser localStorage):
```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/settings/strategy-overrides
```
Expected: JSON with `combos` array (19 combos) and empty `disabled` list.

Test PUT with invalid email (expect 403):
```bash
curl -X PUT -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"disabled": ["XAG_USD::SilverSniper"]}' \
  http://localhost:8000/api/settings/strategy-overrides
```

### Step 4: Commit

```bash
git add backend/app/api/settings.py backend/app/api/routes.py
git commit -m "feat: add settings API for strategy override management"
```

---

## Task 2: Backend — Cron job reads Firestore overrides

**Files:**
- Modify: `backend/app/services/forex_screener.py` (2 methods)
- Modify: `backend/app/services/tasks.py` (1 function)

### Step 1: Modify `forex_screener.py` — `run_orchestrated_refresh()` static method

Current signature (line 108-114):
```python
@staticmethod
def run_orchestrated_refresh(
    project_root: Path,
    data_dir: Path,
    config_path: Path,
    output_path: Path,
    mode: str = 'dynamic'
):
```

Replace with:
```python
@staticmethod
def run_orchestrated_refresh(
    project_root: Path,
    data_dir: Path,
    config_path: Path,
    output_path: Path,
    mode: str = 'dynamic',
    disabled_combos: set = None
):
```

And update the `screener.screen_all(mode=mode)` call at line 138:
```python
return screener.screen_all(mode=mode, disabled_combos=disabled_combos)
```

### Step 2: Modify `forex_screener.py` — `screen_all()` method

Current signature (line 144):
```python
def screen_all(self, mode: str = 'dynamic') -> Dict:
```

Replace with:
```python
def screen_all(self, mode: str = 'dynamic', disabled_combos: set = None) -> Dict:
```

At the top of the `for strategy_config in strategies_to_run:` loop (after line 200, where `strategy_name` is set), add:
```python
                # FILTER: Skip user-disabled combos
                combo_key = f"{symbol}::{strategy_name}"
                if disabled_combos and combo_key in disabled_combos:
                    logger.info(f"Skipping {combo_key} (user-disabled via Settings)")
                    continue
```

This goes right after line 201 (`strategy_name = strategy_config.get("strategy", "TrendFollowing")`), before the existing `# FILTER: If sniper mode` block.

### Step 3: Modify `tasks.py` — `run_forex_refresh_task()`

At the start of the `try:` block in `run_forex_refresh_task()` (after `refresh_manager.start_forex_refresh()`), add:

```python
        # Fetch user override config from Firestore
        disabled_combos = set()
        try:
            from ..firebase_setup import db as firestore_db
            doc = firestore_db.collection("config").document("strategy_overrides").get()
            if doc.exists:
                disabled_combos = set(doc.to_dict().get("disabled", []))
                logger.info(f"[{task_id}] Loaded {len(disabled_combos)} disabled combos from Firestore")
        except Exception as e:
            logger.warning(f"[{task_id}] Could not load strategy overrides, running all: {e}")
```

Then update the `ForexScreener.run_orchestrated_refresh(...)` call to include the new param:
```python
        results = ForexScreener.run_orchestrated_refresh(
            project_root=settings.PROJECT_ROOT,
            data_dir=settings.DATA_DIR / "forex_raw",
            config_path=settings.METADATA_DIR / "forex_pairs.json",
            output_path=settings.PROCESSED_DATA_DIR / "forex_signals.json",
            mode=mode,
            disabled_combos=disabled_combos
        )
```

Note: `db` is already imported at line 21 of `tasks.py` — use the existing import instead of the inline import above. Replace the `from ..firebase_setup import db as firestore_db` with just `db` (already available).

### Step 4: Verify manually

Disable one combo via PUT endpoint, then trigger a forex refresh via `POST /api/forex/refresh`. Check the backend logs for:
```
Skipping XAG_USD::SilverSniper (user-disabled via Settings)
```

### Step 5: Commit

```bash
git add backend/app/services/forex_screener.py backend/app/services/tasks.py
git commit -m "feat: screener respects user-disabled pair/strategy combos from Firestore"
```

---

## Task 3: Frontend — API service functions

**Files:**
- Modify: `frontend/src/services/api.js`

### Step 1: Add two functions to `api.js`

Append to the end of `frontend/src/services/api.js`:

```javascript
/**
 * Fetch all strategy combos with their enabled/disabled state
 */
export async function getStrategyOverrides() {
  const token = localStorage.getItem('google_token');
  const response = await fetch(`${API_BASE}/settings/strategy-overrides`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch strategy overrides: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Save updated disabled strategy list
 * @param {string[]} disabled - Array of "PAIR::Strategy" combo keys to disable
 */
export async function updateStrategyOverrides(disabled) {
  const token = localStorage.getItem('google_token');
  const response = await fetch(`${API_BASE}/settings/strategy-overrides`, {
    method: 'PUT',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ disabled })
  });

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || `Failed to save: ${response.statusText}`);
  }

  return response.json();
}
```

### Step 2: Commit

```bash
git add frontend/src/services/api.js
git commit -m "feat: add API functions for strategy override GET/PUT"
```

---

## Task 4: Frontend — Settings component

**Files:**
- Create: `frontend/src/components/Settings.jsx`
- Create: `frontend/src/components/Settings.module.css`

### Step 1: Create `frontend/src/components/Settings.jsx`

```jsx
/**
 * Settings Component
 *
 * Allows the admin user to enable/disable individual pair+strategy combos.
 * All logged-in users can view; only the admin can save.
 */

import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import { getStrategyOverrides, updateStrategyOverrides } from '../services/api';
import styles from './Settings.module.css';

const ADMIN_EMAIL = 'naveenf.opt@gmail.com';

function Settings({ onShowToast }) {
  const { user } = useAuth();
  const [combos, setCombos] = useState([]);
  const [disabled, setDisabled] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const isAdmin = user?.email === ADMIN_EMAIL;

  useEffect(() => {
    if (!user) return;
    loadOverrides();
  }, [user]);

  const loadOverrides = async () => {
    setLoading(true);
    try {
      const data = await getStrategyOverrides();
      setCombos(data.combos || []);
      setDisabled(new Set(data.disabled || []));
    } catch (err) {
      onShowToast({ message: 'Failed to load strategy settings', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = (key) => {
    if (!isAdmin) return;
    setDisabled(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateStrategyOverrides([...disabled]);
      onShowToast({ message: 'Strategy settings saved. Takes effect on next screener run.', type: 'success' });
    } catch (err) {
      onShowToast({ message: err.message || 'Failed to save', type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  // Group combos by pair
  const grouped = combos.reduce((acc, combo) => {
    if (!acc[combo.pair]) acc[combo.pair] = [];
    acc[combo.pair].push(combo);
    return acc;
  }, {});

  if (!user) {
    return (
      <div className={styles.container}>
        <p className={styles.authMessage}>Please log in to view strategy settings.</p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className={styles.container}>
        <p className={styles.loading}>Loading strategy settings...</p>
      </div>
    );
  }

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h2 className={styles.title}>Strategy Controls</h2>
        <p className={styles.subtitle}>
          Enable or disable pair/strategy combinations. Changes apply from the next screener run.
          {!isAdmin && <span className={styles.readOnlyBadge}> Read-only</span>}
        </p>
      </div>

      <div className={styles.groups}>
        {Object.entries(grouped).map(([pair, pairCombos]) => (
          <div key={pair} className={styles.group}>
            <h3 className={styles.pairHeader}>{pair.replace('_', '/')}</h3>
            {pairCombos.map(combo => {
              const isEnabled = !disabled.has(combo.key);
              return (
                <div key={combo.key} className={styles.row}>
                  <span className={styles.strategyName}>{combo.strategy}</span>
                  <span className={styles.timeframe}>{combo.timeframe}</span>
                  <label className={`${styles.toggle} ${!isAdmin ? styles.readOnly : ''}`}>
                    <input
                      type="checkbox"
                      checked={isEnabled}
                      onChange={() => handleToggle(combo.key)}
                      disabled={!isAdmin}
                    />
                    <span className={styles.slider} />
                    <span className={styles.toggleLabel}>{isEnabled ? 'ON' : 'OFF'}</span>
                  </label>
                </div>
              );
            })}
          </div>
        ))}
      </div>

      {isAdmin && (
        <div className={styles.footer}>
          <button
            className={styles.saveButton}
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
          <span className={styles.disabledCount}>
            {disabled.size} combo{disabled.size !== 1 ? 's' : ''} disabled
          </span>
        </div>
      )}
    </div>
  );
}

export default Settings;
```

### Step 2: Create `frontend/src/components/Settings.module.css`

```css
.container {
  max-width: 700px;
  margin: 2rem auto;
  padding: 0 1rem;
}

.header {
  margin-bottom: 1.5rem;
}

.title {
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--color-text-primary, #f0f0f0);
  margin: 0 0 0.5rem;
}

.subtitle {
  font-size: 0.875rem;
  color: var(--color-text-muted, #888);
  margin: 0;
}

.readOnlyBadge {
  display: inline-block;
  margin-left: 0.5rem;
  padding: 0.1rem 0.5rem;
  background: rgba(255, 165, 0, 0.15);
  color: orange;
  border-radius: 4px;
  font-size: 0.75rem;
}

.loading,
.authMessage {
  color: var(--color-text-muted, #888);
  text-align: center;
  padding: 2rem;
}

.groups {
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

.group {
  background: var(--color-surface, #1a1a2e);
  border: 1px solid var(--color-border, #333);
  border-radius: 8px;
  overflow: hidden;
}

.pairHeader {
  font-size: 0.8rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  color: var(--color-accent, #4f9cf9);
  background: rgba(79, 156, 249, 0.08);
  margin: 0;
  padding: 0.6rem 1rem;
  border-bottom: 1px solid var(--color-border, #333);
}

.row {
  display: flex;
  align-items: center;
  padding: 0.6rem 1rem;
  gap: 1rem;
  border-bottom: 1px solid rgba(255,255,255,0.04);
}

.row:last-child {
  border-bottom: none;
}

.strategyName {
  flex: 1;
  font-size: 0.9rem;
  color: var(--color-text-primary, #f0f0f0);
}

.timeframe {
  font-size: 0.75rem;
  color: var(--color-text-muted, #888);
  width: 3rem;
  text-align: right;
}

.toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  user-select: none;
}

.toggle.readOnly {
  cursor: not-allowed;
  opacity: 0.6;
}

.toggle input {
  display: none;
}

.slider {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  background: #444;
  border-radius: 10px;
  transition: background 0.2s;
}

.toggle input:checked + .slider {
  background: #22c55e;
}

.slider::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  width: 14px;
  height: 14px;
  background: white;
  border-radius: 50%;
  transition: transform 0.2s;
}

.toggle input:checked + .slider::after {
  transform: translateX(16px);
}

.toggleLabel {
  font-size: 0.75rem;
  width: 2.5rem;
  color: var(--color-text-muted, #888);
}

.footer {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 1.5rem;
  padding-top: 1rem;
}

.saveButton {
  padding: 0.6rem 1.5rem;
  background: var(--color-accent, #4f9cf9);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 0.9rem;
  font-weight: 600;
  cursor: pointer;
  transition: opacity 0.2s;
}

.saveButton:hover:not(:disabled) {
  opacity: 0.85;
}

.saveButton:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.disabledCount {
  font-size: 0.8rem;
  color: var(--color-text-muted, #888);
}
```

### Step 3: Commit

```bash
git add frontend/src/components/Settings.jsx frontend/src/components/Settings.module.css
git commit -m "feat: add Settings component with pair/strategy toggles"
```

---

## Task 5: Frontend — Wire Settings into routing and nav

**Files:**
- Modify: `frontend/src/components/Header.jsx` (add Settings nav link)
- Modify: `frontend/src/App.jsx` (import Settings, add route)

### Step 1: Add Settings nav link to `Header.jsx`

After the `Portfolio` NavLink block (lines 49-53), add:

```jsx
            {user && (
              <NavLink to="/settings" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                Settings
              </NavLink>
            )}
```

The nav block will now read:
```jsx
          <nav className="nav-links">
            <NavLink to="/" ...>Screener</NavLink>
            <NavLink to="/forex" ...>Forex</NavLink>
            {user && (
              <NavLink to="/portfolio" ...>Portfolio</NavLink>
            )}
            <NavLink to="/insider-trades" ...>Insider Trades</NavLink>
            {user && (
              <NavLink to="/settings" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
                Settings
              </NavLink>
            )}
          </nav>
```

### Step 2: Add Settings route to `App.jsx`

Add import at the top with other component imports:
```jsx
import Settings from './components/Settings';
```

Add route inside `<Routes>` after the insider-trades route:
```jsx
          <Route path="/settings" element={<Settings onShowToast={setToast} />} />
```

### Step 3: Verify end-to-end

1. Start frontend: `cd frontend && npm run dev`
2. Log in with `naveenf.opt@gmail.com`
3. Click Settings tab — should show all 19 combos grouped by pair, all ON
4. Toggle one OFF (e.g. XAG_USD SilverSniper)
5. Click Save — toast should say "Strategy settings saved..."
6. Reload page — toggled combo should still be OFF (loaded from Firestore)
7. Log out, log in as another account — Settings tab still visible, toggles read-only (disabled inputs, "Read-only" badge visible)
8. Check backend log when next cron fires — should see `Skipping XAG_USD::SilverSniper (user-disabled via Settings)`

### Step 4: Commit

```bash
git add frontend/src/components/Header.jsx frontend/src/App.jsx
git commit -m "feat: add Settings nav tab and route for strategy toggle management"
```

---

## Summary

| Task | Files | Key change |
|------|-------|-----------|
| 1 | `api/settings.py`, `api/routes.py` | GET/PUT endpoints with auth guard |
| 2 | `forex_screener.py`, `tasks.py` | Cron reads Firestore, filters disabled combos |
| 3 | `services/api.js` | 2 frontend API functions |
| 4 | `Settings.jsx`, `Settings.module.css` | Settings UI with grouped toggles |
| 5 | `Header.jsx`, `App.jsx` | Nav link + route wiring |

**Total files changed:** 8 (2 created for backend, 2 created for frontend, 4 modified)
