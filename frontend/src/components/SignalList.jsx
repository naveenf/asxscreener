/**
 * SignalList Component
 *
 * List of all trading signals with filtering and sorting.
 */

import React from 'react';
import SignalCard from './SignalCard';
import './SignalList.css';

function SignalList({ signals, loading, minScore, onMinScoreChange, strategyFilter, onStrategyFilterChange }) {
  if (loading) {
    return (
      <div className="signal-list-container">
        <div className="loading">Loading signals...</div>
      </div>
    );
  }

  if (!signals || signals.length === 0) {
    return (
      <div className="signal-list-container">
        <div className="no-signals">
          <h2>No signals found</h2>
          <p>No stocks currently meet the entry conditions</p>
        </div>
      </div>
    );
  }

  // Count signals by strategy
  const trendCount = signals.filter(s => s.strategy === 'trend_following').length;
  const mrCount = signals.filter(s => s.strategy === 'mean_reversion').length;

  return (
    <div className="signal-list-container">
      <div className="filters">
        <label className="filter-label">
          <span>Minimum Score: {minScore}</span>
          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={minScore}
            onChange={(e) => onMinScoreChange(Number(e.target.value))}
            className="score-slider"
          />
        </label>

        <label className="filter-label">
          <span>Strategy:</span>
          <select
            value={strategyFilter}
            onChange={(e) => onStrategyFilterChange(e.target.value)}
            className="strategy-select"
          >
            <option value="all">All Strategies ({signals.length})</option>
            <option value="trend_following">📈 Trend Following ({trendCount})</option>
            <option value="mean_reversion">📉 Mean Reversion ({mrCount})</option>
          </select>
        </label>
      </div>

      <div className="signal-count">
        Showing {signals.length} signal{signals.length !== 1 ? 's' : ''}
      </div>

      <div className="signal-grid">
        {signals.map((signal) => (
          <SignalCard key={`${signal.ticker}-${signal.strategy}`} signal={signal} />
        ))}
      </div>
    </div>
  );
}

export default SignalList;
