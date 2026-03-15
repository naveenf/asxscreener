import React from 'react';

const BacktestComparison = ({ data }) => {
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

        return (
          <div key={pairKey} className="bt-pair-card">
            {/* Header */}
            <div className="bt-pair-name">{pairKey.replace('::', ' · ')}</div>

            {insufficient && (
              <div className="bt-insufficient">Insufficient data (&lt;10 trades)</div>
            )}

            {/* Visual win-rate track */}
            <div className="bt-wr-track" title={`Live ${liveWR.toFixed(1)}% vs BT ${btWR.toFixed(1)}%`}>
              <div
                className={`bt-wr-fill ${liveWR >= btWR ? 'pos' : 'neg'}`}
                style={{ width: `${barWidth}%` }}
              />
              {/* BT marker line — clamped so it never overflows the track */}
              <div className="bt-wr-marker" style={{ left: `${Math.min(Math.max(btWR, 0), 99)}%` }} />
            </div>

            {/* Live vs BT labels */}
            <div className="bt-wr-labels">
              <span className="bt-wr-live">
                Live <strong>{liveWR.toFixed(1)}%</strong>
              </span>
              <span className="bt-wr-bt">BT {btWR.toFixed(1)}%</span>
            </div>

            {/* Delta badge */}
            {delta_win_rate !== null && (
              <div className={`bt-delta ${deltaPositive ? 'bt-delta-positive' : 'bt-delta-negative'}`}>
                {deltaPositive ? '▲ +' : '▼ '}{delta_win_rate.toFixed(1)}% vs BT
              </div>
            )}

            {/* Stats */}
            <div className="bt-row">
              <span className="bt-label">Live P&amp;L</span>
              <span className={`bt-val ${live.pnl >= 0 ? 'positive' : 'negative'}`}>
                ${live.pnl.toFixed(2)}
              </span>
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
        );
      })}
    </div>
  );
};

export default BacktestComparison;
