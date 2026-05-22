import React, { useState } from 'react';
import RMultipleHistogram from './RMultipleHistogram';

const BacktestComparison = ({ data }) => {
  const [flipped, setFlipped] = useState(null);

  if (!data || Object.keys(data).length === 0) return null;

  return (
    <div className="bt-comparison-grid">
      {Object.entries(data).map(([pairKey, info]) => {
        const { live, backtest, delta_win_rate } = info;
        const insufficient  = live.trades < 10;
        const deltaPositive = delta_win_rate !== null && delta_win_rate >= 0;
        const liveWR        = live.win_rate_pct;
        const btWR          = backtest.win_rate_pct;
        const barWidth      = Math.min(liveWR, 100);
        const isFlipped     = flipped === pairKey;

        return (
          <div key={pairKey} className="bt-pair-card">
            <div
              className={`bt-card-flipper${isFlipped ? ' flipped' : ''}`}
              style={{ height: '100%' }}
              onClick={() => setFlipped(isFlipped ? null : pairKey)}
            >
              <div className="bt-card-inner">

                {/* ── Front: stats ── */}
                <div className="bt-card-face bt-card-face--front">
                  <div className="bt-pair-name">
                    {pairKey.replace('::', ' · ')}
                    <span className="bt-flip-hint">flip ↻</span>
                  </div>

                  {insufficient && (
                    <div className="bt-insufficient">Insufficient data (&lt;10 trades)</div>
                  )}

                  <div className="bt-wr-track" title={`Live ${liveWR.toFixed(1)}% vs BT ${btWR.toFixed(1)}%`}>
                    <div
                      className={`bt-wr-fill ${liveWR >= btWR ? 'pos' : 'neg'}`}
                      style={{ width: `${barWidth}%` }}
                    />
                    <div className="bt-wr-marker" style={{ left: `${Math.min(Math.max(btWR, 0), 99)}%` }} />
                  </div>

                  <div className="bt-wr-labels">
                    <span className="bt-wr-live">Live <strong>{liveWR.toFixed(1)}%</strong></span>
                    <span className="bt-wr-bt">BT {btWR.toFixed(1)}%</span>
                  </div>

                  {delta_win_rate !== null && (
                    <div className={`bt-delta ${deltaPositive ? 'bt-delta-positive' : 'bt-delta-negative'}`}>
                      {deltaPositive ? '▲ +' : '▼ '}{delta_win_rate.toFixed(1)}% vs BT
                    </div>
                  )}

                  <div className="bt-row">
                    <span className="bt-label">Live P&amp;L</span>
                    <span className={`bt-val ${live.pnl >= 0 ? 'positive' : 'negative'}`}>${live.pnl.toFixed(2)}</span>
                  </div>
                  <div className="bt-row">
                    <span className="bt-label">Trades</span>
                    <span className="bt-val">{live.trades}</span>
                  </div>
                  <div className="bt-row">
                    <span className="bt-label">BT Sharpe</span>
                    <span className="bt-val">{backtest.sharpe}</span>
                  </div>
                  <div className="bt-row">
                    <span className="bt-label">BT MaxDD</span>
                    <span className="bt-val negative">{backtest.max_dd_pct}%</span>
                  </div>
                </div>

                {/* ── Back: R-multiple histogram ── */}
                <div className="bt-card-face bt-card-face--back">
                  <div className="bt-pair-name">
                    {pairKey.replace('::', ' · ')}
                    <span className="bt-flip-hint">flip ↺</span>
                  </div>
                  <RMultipleHistogram rMultiples={live.r_multiples} />
                </div>

              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
};

export default BacktestComparison;
