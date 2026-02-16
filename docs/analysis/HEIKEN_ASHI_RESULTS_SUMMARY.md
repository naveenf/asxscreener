# Heikin Ashi Multi-Symbol Backtest Results

**Date:** 2026-02-03
**Timeframe:** 1H (Base), 4H (HTF)
**Starting Balance:** $10000
**Risk Per Trade:** 1.0%

### Strategy Comparison: JP225_USD



| Strategy | Trades | Win Rate | ROI |

| --- | --- | --- | --- |

| **Heikin Ashi (New)** | **77** | **31.2%** | **+23.5%** |

| Squeeze (Current) | 21 | 19.0% | -9.0% |



**Recommendation:** Migrate **JP225_USD** to Heikin Ashi strategy immediately. It shows significantly better trend capture and higher frequency of profitable setups.



### Analysis of Other Assets



For most other assets (NAS100, XCU, Forex), Heikin Ashi underperformed compared to the benchmark or resulted in higher drawdowns due to increased trade frequency in range-bound environments. 



- **NAS100_USD:** Both strategies are struggling, but Squeeze (-5.9% ROI) is more defensive than Heikin Ashi (-14.3% ROI).

- **XCU_USD:** Heikin Ashi had a significant loss (-23.7% ROI) compared to Squeeze (-5.3% ROI).



**Next Steps:**

1. Update `best_strategies.json` for JP225_USD.

2. Maintain Squeeze for other assets until further optimization.
