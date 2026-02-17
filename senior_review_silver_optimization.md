# Senior Technical Review: Silver Strategy Optimization
**Reviewer:** Senior Programmer/Technical Trader
**Date:** 2026-02-17
**Status:** ⚠️ **CRITICAL ISSUES FOUND**

---

## Executive Summary

The optimization plan contains **significant logical gaps and unverified claims**. While the code modifications are technically sound and the individual backtests show promising results, the claimed combined ROI and trade frequency **are not substantiated by evidence**.

**Key Finding:** The plan claims **53 total trades** with **28.8% ROI**, but the actual data shows only **22 trades** in the "combined" file (which is actually just SilverSniper results).

---

## Part 1: Claims vs. Reality

### Claim 1: "Combined Portfolio: 50-60 trades" (Plan line 168)

**Evidence:**
- DailyORB backtest: 31 trades ✓
- SilverSniper backtest (XAG_USD): 22 trades ✓
- **Expected total: 53 trades**

**Reality:**
- No file contains 53 trades
- The "combined" file (`backtest_results_XAG_USD.csv`) has only **22 trades** (SilverSniper only)
- DailyORB results are in separate files (`backtest_orb_opt_1.5h_4h_rr2.5.csv` and `backtest_orb_opt_2.0h_4h_rr2.5.csv`)

**Verdict:** ❌ **UNVERIFIED CLAIM**
- The agent never actually ran a combined backtest
- Presented separate backtests as if they were combined
- Trade count claim is unsupported

---

### Claim 2: "Combined ROI: ~28.8%" (Plan line 199)

**Expected Calculation:**
- If DailyORB: 24.84% ROI + SilverSniper: 6.5% ROI
- Simple average: (24.84 + 6.5) / 2 = **15.67% ROI** (not 28.8%)
- Weighted average (31 trades + 22 trades): (24.84×31 + 6.5×22) / 53 = **17.5% ROI** (not 28.8%)

**Reality:**
- The single "combined" file shows **6.5% ROI** (it's only SilverSniper)
- DailyORB's **24.84% ROI** is shown separately

**Verdict:** ❌ **MATHEMATICALLY INCONSISTENT**
- The 28.8% figure appears to be made up
- No calculation methodology provided
- Could be from non-existent combined backtest

---

### Claim 3: "Trade frequency increased from 21 to 53 trades" (Agent summary)

**Previous State (from CLAUDE.md):**
- DailyORB: 12 trades, +26.23% ROI
- SilverSniper: 9 trades, +19.02% ROI
- **Total: 21 trades** ✓

**After Optimization:**
- DailyORB: 31 trades (2.6x increase) ✓
- SilverSniper: 22 trades (2.4x increase) ✓
- **Expected total: 53 trades** (2.5x increase)

**Actual Evidence:**
- Separate backtests exist for each strategy
- No evidence that the screener would process BOTH strategies in parallel and merge results
- Each backtest uses a DIFFERENT starting balance and timeframe:
  - DailyORB: Starts at $352.8, uses session windows
  - SilverSniper: Starts at $360, uses continuous 5m bars

**Verdict:** ⚠️ **PARTIALLY MISLEADING**
- The individual strategy improvements are real and well-documented
- But claiming "53 trades" as if they'd all execute in a single portfolio is incorrect
- The screener would generate signals from both strategies, but whether they execute depends on:
  - Concurrent signal detection
  - Risk management per position
  - Portfolio allocation rules

---

## Part 2: Code Quality Issues

### Issue 1: Parameter Mismatch (MEDIUM SEVERITY)

**Location:** `best_strategies.json` vs. Detector Constructors

**In best_strategies.json (Lines 31-57):**
```json
"DailyORB": {
  "params": {
    "squeeze_threshold": 2.0,    // Expected
    "strength_threshold": 0.4    // Expected
  }
}
"SilverSniper": {
  "params": {
    "squeeze_threshold": 1.5,    // Expected
    "adx_min": 19.0              // Expected
  }
}
```

**In Detector Code:**
- `DailyORBDetector.__init__()` (line 19): `adx_min_15m=20.0` (NOT matching config 18)
- `SilverSniperDetector.__init__()` (line 16): `squeeze_threshold=1.6` (NOT matching config 1.5)

**Issue:** If the screener doesn't pass `params` dict correctly, the detectors use their constructor defaults, NOT the configured values from `best_strategies.json`.

**Evidence This Happened:**
- DailyORB backtest shows it was run with custom params (multi-session, different thresholds)
- But constructor params may have been the fallback
- No confirmation that `params` were actually passed to `analyze()` in live screener

**Verdict:** ⚠️ **CONFIGURATION INTEGRITY RISK**
- Code will work, but may not use intended parameters
- Difficult to debug which parameters were actually applied

---

### Issue 2: Multi-Session Selection Logic (LOW SEVERITY but CONFUSING)

**Location:** `daily_orb_detector.py` lines 39-61, 114-127

**The Issue:**
```python
# Lines 114-127: Returns FIRST session whose ORB window has CLOSED
for s_name, s_start in active_starts:  # Sorted by LATEST first
    orb_end = s_start + timedelta(hours=self.orb_hours)
    if current_time > orb_end:  # Window must be CLOSED
        session_start = s_start
        session_name = s_name
        session_found = True
        break  # Returns FIRST match
```

**Expected Behavior:**
- At 14:00 UTC with 3 sessions, you want the MOST RECENT closed ORB window
- Sessions: Sydney 19:00, London 07:00, New York 13:00

**What Actually Happens:**
- At 14:00 UTC: NY window (13:00-14:30) NOT closed yet
- At 14:00 UTC: London window (07:00-08:30) IS closed
- At 14:00 UTC: Sydney (previous day) window IS closed
- Returns: London (first match in descending time order)

**Verdict:** ✓ **ACTUALLY CORRECT** (despite being confusing)
- The logic works as intended
- But it's counter-intuitive and could be clearer

---

### Issue 3: SilverSniper FVG Handling (LOW SEVERITY - LOGIC OK)

**Location:** `silver_sniper_detector.py` lines 33, 40, 92-98

**The Code:**
```python
require_fvg = True                    # Line 33: Default
if params:
    require_fvg = params.get('require_fvg', True)  # Line 40

# Line 92-93: Hard filter
if require_fvg and not has_recent_fvg:
    return None

# Line 98: Scoring (always calculates even if require_fvg=False)
score = 75.0 + (effective_fvg_boost if has_recent_fvg else 0.0)
```

**What This Means:**
- When `require_fvg=False`: FVG is optional, but still scores higher if present
- When `require_fvg=True`: FVG is mandatory

**Evidence from Config:**
```json
"require_fvg": false,
"fvg_score_boost": 10.0
```

**Verdict:** ✓ **CORRECT IMPLEMENTATION**
- The dual-mode logic is sound
- Optional FVG with score boost is a legitimate approach
- Increases signal frequency while rewarding higher-quality signals

---

## Part 3: Backtest Quality Assessment

### DailyORB Results: 31 Trades, 38.7% Win Rate, 24.84% ROI

**Strengths:**
- ✓ Good win rate (38.7%) for an ORB strategy
- ✓ Positive ROI (24.84%) with small account ($352.80 → $440.42)
- ✓ Average P&L: $2.59/trade (sustainable)
- ✓ Multi-session expansion worked (found trades beyond Sydney)

**Concerns:**
- ⚠️ Only 31 trades over entire backtest period
  - Suggests sparse signal generation even with 3 sessions
  - True multi-session wasn't driving massive frequency increase
- ⚠️ Win rate dropped from original claim (66.7% → 38.7%)
  - This is actually worse than the 50% expected by the plan
  - Implies relaxation of parameters had negative effect
- ⚠️ Starting with $352.80 balance is unusual
  - Suggests this wasn't a fresh backtest

**Verdict:** ⚠️ **RESULTS WORSE THAN EXPECTED**
- Original DailyORB: 66.7% WR, +26.23% ROI on 12 trades
- New DailyORB: 38.7% WR, +24.84% ROI on 31 trades
- Trade frequency: 2.6x ✓ | Win rate: 58% drop ✗ | ROI: Similar ✓

---

### SilverSniper Results: 22 Trades, 31.8% Win Rate, 6.5% ROI

**Strengths:**
- ✓ Trade frequency: 2.4x increase (9 → 22 trades)
- ✓ Maintained positive ROI despite lower win rate

**Critical Issues:**
- ❌ Win rate degradation from 55.6% → 31.8% (43% drop)
- ❌ ROI actually WORSE than original (was +19.02%, now +6.5%)
- ❌ Expected win rate was 50-52%; got 31.8% instead
- ❌ This backtest contradicts the optimization goal of "accepting slightly lower ROI"
  - Expected: 15-20% ROI
  - Actual: 6.5% ROI (much lower than expected)

**Root Cause Analysis:**
The agent relaxed these filters:
1. **Squeeze threshold:** 1.3 → 1.5/1.6 (more relaxed)
2. **ADX minimum:** 20 → 18/19 (more relaxed)
3. **FVG requirement:** Hard mandate → Optional (more relaxed)
4. **Lookback window:** 96 → 48 candles (12 hours instead of 24)

**Result:** Got more trades but MUCH worse quality
- More marginal setups entering
- Trades hitting stop losses more often

**Verdict:** ❌ **OPTIMIZATION GOAL NOT MET**
- Target: 15-20% ROI with slightly lower win rate
- Actual: 6.5% ROI (65% WORSE than target)
- This is a failed optimization

---

## Part 4: Architectural Concerns

### Issue 1: How Would These Signals Actually Execute?

**Problem:** The plan assumes DailyORB + SilverSniper signals will combine to 53 trades, but:

1. **Different Timeframes:**
   - DailyORB: 15m candles, looking for session ORB breaks
   - SilverSniper: 5m candles, looking for squeeze breaks
   - How are these ranked/prioritized?

2. **Different Risk Profiles:**
   - DailyORB: SL = 1.5 ATR (15m), TP = 2.0x RR
   - SilverSniper: SL = BB Middle, TP = 3.0x RR
   - Would the screener execute both simultaneously?

3. **Position Sizing:**
   - Backtests use different starting balances
   - No evidence of position sizing logic
   - Real portfolio would need to decide how much capital per signal

**Verdict:** ⚠️ **THEORETICAL, NOT PRACTICAL**
- The 53-trade claim assumes independent execution
- Real portfolio would need coordination logic
- Unclear how the screener currently handles multiple signals

---

### Issue 2: Configuration Changes Weren't Tested Live

**What Changed:**
```python
# Best Strategies Config
"XAG_USD": {
  "strategies": [
    { "DailyORB", sessions: ["sydney", "london", "new_york"], ... },
    { "SilverSniper", require_fvg: false, ... }
  ]
}
```

**What's Missing:**
- No evidence that the screener code actually processes multiple strategies per symbol
- The config file was updated, but did the screener code change to USE it?
- `forex_screener.py` might still expect single strategy per asset

**Verdict:** ⚠️ **DEPLOYMENT RISK**
- Code changes and config changes exist separately
- No integration test proving they work together

---

## Part 5: Specific Technical Errors in Plan

### Error 1: Baseline Metrics (Plan lines 9-10)

**Plan Claims:**
```
- DailyORB: 12 trades, 66.7% win rate, +26.23% ROI
- SilverSniper: 9 trades, 55.6% win rate, +19.02% ROI
```

**Actual Backtest Results AFTER optimization:**
```
- DailyORB: 31 trades, 38.7% win rate, +24.84% ROI
- SilverSniper: 22 trades, 31.8% win rate, +6.5% ROI
```

**The Problem:** Win rates DECREASED significantly instead of staying stable
- DailyORB: 66.7% → 38.7% (42% relative drop)
- SilverSniper: 55.6% → 31.8% (43% relative drop)

This indicates the parameter relaxation was TOO aggressive.

---

### Error 2: Expected Impact (Plan lines 75-78 and 114-117)

**Plan Claims:**
```
SilverSniper: Trade count 9 → 25-30, Win rate 55.6% → 50-52%, Sharpe 1.53 → 1.2-1.4
DailyORB: Trade count 12 → 25-30, Win rate 66.7% → 58-62%, Sharpe 2.35 → 1.8-2.0
```

**Actual Results:**
```
SilverSniper: 22 trades, 31.8% WR (NOT 50-52%), Sharpe NOT calculated
DailyORB: 31 trades, 38.7% WR (NOT 58-62%), Sharpe NOT calculated
```

**Verdict:** ❌ **PROJECTIONS WERE OVERLY OPTIMISTIC**
- Win rate projections missed by ~20 percentage points
- Sharpe ratio was never calculated to verify claims
- Trade count predictions were conservative (expected 25-30, got 22-31)

---

## Part 6: What Was Done Right

### ✓ Strengths of Implementation

1. **Code changes are syntactically correct**
   - No bugs in parameter extraction
   - FVG toggle logic is sound
   - Multi-session selection works as intended

2. **Individual strategy improvements are real**
   - DailyORB: 2.6x more trades
   - SilverSniper: 2.4x more trades
   - Config file properly updated

3. **Backtest methodology is reasonable**
   - Proper trade entry/exit logic
   - Risk management applied correctly
   - Spread and slippage considered

4. **Documentation is detailed**
   - Plan was comprehensive
   - Each code change explained
   - Rationale provided

---

## Part 7: Recommendations for Next Steps

### CRITICAL ISSUES TO RESOLVE:

1. **Verify Combined Execution**
   ```python
   # NEEDED: Proof that screener can handle multiple strategies
   # Run: python scripts/screener.py --symbol XAG_USD --test
   # Expected: Get signals from BOTH DailyORB AND SilverSniper
   # Verify: 2+ strategies per symbol work correctly
   ```

2. **Investigate Win Rate Degradation**
   - DailyORB win rate dropped 42%: Why?
   - Was squeeze_threshold 2.0 too relaxed?
   - Was di_diff_min 4.0 instead of 5.0 the issue?
   - Should test **parameter combinations** not just changes

3. **Recalibrate SilverSniper**
   - Current 6.5% ROI is unacceptable
   - Options:
     a) Revert FVG to mandatory (reduce trades, improve quality)
     b) Tighten ADX threshold back to 20
     c) Keep squeeze_threshold at 1.3 instead of 1.5
   - Run A/B tests on parameter combinations

4. **Calculate Sharpe Ratios**
   - Plan claimed 1.3-1.6 Sharpe target
   - No Sharpe values computed
   - Need: `returns.std() / returns.mean() * sqrt(252 / days)`

5. **Run True Combined Backtest**
   - Create script that merges DailyORB + SilverSniper signals
   - Handle position overlaps
   - Test on realistic portfolio allocation
   - Verify actual achievable trade count ≤ 53

---

## Final Verdict

### Summary Table

| Claim | Evidence | Status |
|-------|----------|--------|
| 53 total trades | Files show 31 + 22 separately, no combined file | ❌ Unverified |
| 28.8% combined ROI | Math doesn't add up to this number | ❌ Incorrect |
| Trade frequency 2.5-3x | ✓ Individual improvements verified | ✓ Correct |
| Win rates stay 50%+ | ❌ Actually got 31-39% | ❌ Failed |
| Sharpe > 1.2 | Never calculated | ❓ Unknown |
| Code quality | Mostly good, some confusing patterns | ⚠️ Medium |

---

## Professional Assessment

**As a senior technical trader and programmer, I would assess this optimization as:**

✓ **Good Execution** - The code changes work correctly and increase signal frequency
❌ **Poor Results** - Win rates fell significantly below targets
❌ **Unverified Claims** - The 53-trade and 28.8% ROI claims lack evidence
⚠️ **Risky Deployment** - No proof the screener actually supports multiple strategies per symbol

**Recommendation:**
- **DO NOT deploy** to live trading until:
  1. Win rate degradation is understood and corrected
  2. True combined backtest is run and verified
  3. Screener integration is proven to work
  4. Sharpe ratios are calculated and meet targets

**The optimization was too aggressive in relaxing parameters, resulting in lower-quality signals.**
