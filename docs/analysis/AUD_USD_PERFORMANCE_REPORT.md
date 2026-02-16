# AUD_USD Performance Report
## Sniper Strategy Backtest Results

**Generated:** 2026-02-05
**Strategy:** Sniper (15m base, 1H HTF)
**Backtest Period:** November 10, 2025 - February 5, 2026 (3 months)
**Data Source:** `/data/backtest_results_AUD_USD.csv`

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Total Trades** | 17 |
| **Win Rate** | 47.1% (8 wins, 9 losses) |
| **Net Return** | +2.03% |
| **Starting Balance** | $360.00 |
| **Final Balance** | $367.30 |
| **Total P&L** | +$7.30 |

---

## Risk Metrics

| Metric | Value |
|--------|-------|
| **Max Drawdown** | -8.53% |
| **Max Consecutive Losses** | 4 |
| **Largest Single Loss** | -$8.85 |
| **Largest Single Win** | +$10.92 |
| **Sharpe Ratio** | 0.19 |

---

## R:R Analysis

| Metric | Value |
|--------|-------|
| **Target R:R** | 1.5:1 |
| **Average Win** | $10.23 (1.50 R) |
| **Average Loss** | -$8.28 (-1.00 R) |
| **Average R:R (All Trades)** | 0.18 R |
| **Average R:R (Wins Only)** | 1.50 R |
| **Average R:R (Losses Only)** | -1.00 R |

---

## Trade-by-Trade Breakdown

### Winning Trades (8 total)

| # | Date | Direction | Entry | Exit | P&L | R |
|---|------|-----------|-------|------|-----|---|
| 2 | 2025-11-17 | SELL | 0.64934 | 0.64357 | $9.85 | 1.50 |
| 4 | 2025-11-26 | BUY | 0.65026 | 0.65604 | $9.90 | 1.50 |
| 5 | 2025-12-03 | BUY | 0.65775 | 0.66358 | $10.18 | 1.50 |
| 8 | 2025-12-23 | BUY | 0.66913 | 0.67505 | $10.00 | 1.50 |
| 10 | 2026-01-20 | BUY | 0.67318 | 0.67913 | $10.05 | 1.50 |
| 11 | 2026-01-22 | BUY | 0.68074 | 0.68675 | $10.33 | 1.50 |
| 12 | 2026-01-26 | BUY | 0.69170 | 0.69779 | $10.62 | 1.50 |
| 13 | 2026-01-28 | BUY | 0.70046 | 0.70661 | $10.92 | 1.50 |

**Win Pattern:** 7 of 8 wins were BUY trades during uptrend (late Nov - late Jan)

### Losing Trades (9 total)

| # | Date | Direction | Entry | Exit | P&L | R |
|---|------|-----------|-------|------|-----|---|
| 1 | 2025-11-10 | BUY | 0.65229 | 0.64843 | -$7.93 | -1.00 |
| 3 | 2025-11-21 | SELL | 0.64372 | 0.64754 | -$7.97 | -1.00 |
| 6 | 2025-12-05 | BUY | 0.66397 | 0.66005 | -$8.24 | -1.00 |
| 7 | 2025-12-17 | SELL | 0.66006 | 0.66396 | -$8.06 | -1.00 |
| 9 | 2026-01-08 | SELL | 0.66984 | 0.67379 | -$8.10 | -1.00 |
| 14 | 2026-01-29 | BUY | 0.70600 | 0.70187 | -$8.85 | -1.00 |
| 15 | 2026-01-30 | BUY | 0.70080 | 0.69670 | -$8.66 | -1.00 |
| 16 | 2026-02-02 | SELL | 0.69657 | 0.70065 | -$8.47 | -1.00 |
| 17 | 2026-02-03 | BUY | 0.70120 | 0.69709 | -$8.28 | -1.00 |

**Loss Pattern:** 4 consecutive losses occurred between Jan 29 - Feb 3 during reversal period

---

## Performance Analysis

### Strengths
1. **Consistent R:R Achievement:** All winning trades hit the exact 1.5R target
2. **Strong Mid-Period Run:** 6 consecutive wins between Dec 3 - Jan 28 (+$62.09)
3. **Trend Following:** 7 of 8 wins captured the November-January uptrend
4. **Risk Management:** All losses stopped at exactly -1.0R, no catastrophic failures

### Weaknesses
1. **Low Win Rate:** 47.1% below the 50% breakeven threshold for 1.5R strategy
2. **Trend Reversal Vulnerability:** 4 consecutive losses during late-January reversal
3. **Low Sharpe Ratio:** 0.19 indicates poor risk-adjusted returns
4. **High Drawdown:** -8.53% max drawdown relative to +2.03% return
5. **Spread Impact:** 0.06% spread cost affects short-term 15m trades

### Critical Findings
- **Expectancy:** (0.471 × $10.23) + (0.529 × -$8.28) = **$0.43 per trade**
- At current performance, needs **16 trades to gain $7** (current result)
- **Breakeven Analysis:** Requires 60%+ win rate to consistently profit at 1.5R
- **Comparison to Best Performers:**
  - XAU_USD (HeikenAshi): 46.75% return vs AUD_USD 2.03%
  - XAG_USD (SilverSniper): 19.02% return vs AUD_USD 2.03%
  - WHEAT (CommoditySniper): 7.95% return vs AUD_USD 2.03%

---

## Strategy Configuration

### Current Settings (from best_strategies.json)
```json
{
  "AUD_USD": {
    "strategy": "Sniper",
    "timeframe": "15m",
    "target_rr": 1.5
  }
}
```

### Execution Parameters
- **Base Timeframe:** 15 minutes
- **HTF Confirmation:** 1 Hour
- **Entry Signal:** DI+/DI- crossover with casket filters
- **HTF Filter:** ADX > 25, EMA34 alignment
- **Exit:** 1.5R Target or SMA20 cross
- **Risk per Trade:** 2% of balance
- **Spread Cost:** 0.06% per trade

---

## Comparison: Expected vs Actual

### Initial Documentation Claims (Feb 4)
| Metric | Documented | Actual (Feb 5) | Variance |
|--------|-----------|---------------|----------|
| Win Rate | 60.0% | 47.1% | **-12.9%** ⚠️ |
| Total Trades | 20 | 17 | -3 |
| Return | +22.90% | +2.03% | **-20.87%** ⚠️ |
| Max Drawdown | -4.68% | -8.53% | **+3.85%** ⚠️ |
| Sharpe Ratio | 1.87 | 0.19 | **-1.68** ⚠️ |

**Analysis:** Current backtest results significantly underperform documented expectations. Possible causes:
1. Documentation based on optimized/selected period
2. Market regime change (trending → ranging/reversal)
3. Data quality or indicator calculation differences
4. Live execution slippage not captured in original test

---

## Recommendations

### Immediate Actions
1. **Status Change:** Moved from "ACTIVE" to "⚠️ MONITORING" in portfolio ranking
2. **Position Sizing:** Reduce risk to 1% per trade until performance stabilizes
3. **Filter Enhancement:** Add trend filter to avoid counter-trend entries during reversals

### Optimization Opportunities
1. **Increase R:R to 2.0:** Current 1.5R requires 57% win rate, 2.0R only needs 50%
2. **Add HTF Trend Filter:** Only trade with 4H trend alignment
3. **Time-Based Filters:** Analyze loss patterns by hour/day to identify unfavorable periods
4. **Casket Reassignment:** Test if AUD_USD fits better in different casket group
5. **Alternative Strategy:** Test SilverSniper (5m precision) or Squeeze (volatility-based)

### Portfolio Implications
- **Ranked #5 of 6:** Only outperforms BCO_USD (tied at +2.03%)
- **Portfolio Avg Impact:** Reduced from 23.8% to 26.6% (Top 4 only)
- **Capital Allocation:** Consider reallocating to higher-performing assets (XAU, JP225, XAG)

---

## Status: ⚠️ MONITORING

**Next Review:** After 10 more trades or 1 month (whichever comes first)

**Success Criteria for ACTIVE Status:**
- Win rate ≥ 55% over 20+ trades
- Net return ≥ +10%
- Max drawdown ≤ 6%
- Sharpe ratio ≥ 1.0

---

## Files Reference
- **Trade Data:** `/data/backtest_results_AUD_USD.csv`
- **15m Data:** `/data/forex_raw/AUD_USD_15_Min.csv`
- **1H Data:** `/data/forex_raw/AUD_USD_1_Hour.csv`
- **Strategy Config:** `/data/metadata/best_strategies.json`
- **Backtest Script:** `/scripts/backtest_sniper_detailed.py`

---

**Report Generated By:** ASX Screener Backtest Engine
**Last Updated:** 2026-02-05 14:45 UTC
