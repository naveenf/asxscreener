/**
 * SignalList Component
 *
 * List of all trading signals with filtering and sorting.
 */

import React from 'react';
import SignalCard from './SignalCard';
import './SignalList.css';

function SignalList({ signals, loading, minScore, onMinScoreChange }) {
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
          <p>No stocks currently meet the entry conditions (ADX &gt; 30 and DI+ &gt; DI-)</p>
        </div>
      </div>
    );
  }

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
      </div>

      <div className="signal-count">
        Found {signals.length} signal{signals.length !== 1 ? 's' : ''}
      </div>

      <div className="signal-grid">
        {signals.map((signal) => (
          <SignalCard key={signal.ticker} signal={signal} />
        ))}
      </div>
    </div>
  );
}

export default SignalList;
