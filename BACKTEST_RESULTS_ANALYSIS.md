# Squeeze Optimization Backtest Results - Final Analysis Report
**Date:** 2026-02-03
**Backtest Period:** ~10 months (5000+ candles)
**Starting Balance:** $10,000
**Risk per Trade:** 1%

---

## Executive Summary
The second phase of optimization successfully increased trade frequency across all assets by relaxing filters (ADX, Cooldown, Time Filters, and FVG). However, the migration of **XCU_USD** to **HeikenAshi** proved unsuccessful, while **JP225_USD** continues to show exceptional performance.

## Key Results Summary

### ✅ SUCCESS: JP225_USD HeikenAshi
- **ROI:** +32.3%
- **Trades:** 209
- **Win Rate:** 31.1%
- **Status:** Verified and Deployed.

### 🟡 IMPROVED: Squeeze Indices (NAS100, UK100)
- **NAS100_USD:** 1 trade (previously 0). FVG removal helped, but still very selective.
- **UK100_GBP:** 3 trades, +1.3% ROI. Positive expectancy.
- **Status:** Strategy is working but remains highly selective.

### 🔴 FAILED: XCU_USD HeikenAshi Migration
- **ROI:** -35.5%
- **Trades:** 176
- **Win Rate:** 22.7%
- **Observation:** High frequency but extremely low win rate suggests HeikenAshi noise filtering is not effective for Copper's volatility.
- **Recommendation:** Revert to Squeeze strategy.

### ⚖️ Forex Relaxation (USD_JPY, AUD_USD, USD_CHF)
- **Trade Count:** Increased to 8-9 trades (from 4-5).
- **ROI:** Remains negative (-4.6% to -6.9%).
- **Observation:** While trade frequency doubled, the quality did not improve enough to overcome spread costs and whipsaws.

---

## Strategy Comparison Table

| Asset      | Strategy          | Trades | Win Rate | ROI   | Status                     |
|------------|-------------------|--------|----------|-------|----------------------------|
| JP225_USD  | HeikenAshi        | 209    | 31.1%    | +32.3%| ✅ DEPLOYED                |
| XCU_USD    | HeikenAshi        | 176    | 22.7%    | -35.5%| ❌ REVERT TO SQUEEZE       |
| UK100_GBP  | Squeeze Optimized | 3      | 33.3%    | +1.3% | ✅ ACTIVE                  |
| NAS100_USD | Squeeze Optimized | 1      | 0.0%     | -1.0% | 🟡 ACTIVE                  |
| USD_JPY    | Squeeze Optimized | 9      | 22.2%    | -4.6% | 🟡 ACTIVE (High Frequency) |
| AUD_USD    | Squeeze Optimized | 9      | 0.0%     | -6.2% | 🔴 MONITOR                 |
| USD_CHF    | Squeeze Optimized | 8      | 0.0%     | -6.9% | 🔴 MONITOR                 |

---

## Final Actions Taken
1. **JP225_USD:** Migrated to HeikenAshi.
2. **Squeeze Detector:** Relaxed ADX (23), Cooldown (2h), and removed news-hour filters.
3. **FVG:** Disabled for indices.
4. **XCU_USD:** Recommended to revert to Squeeze (will be done in post-implementation cleanup).