/**
 * Header Component
 *
 * Application header with title, status, and refresh button.
 */

import React from 'react';
import './Header.css';

function Header({ status, onRefresh, refreshing }) {
  const formatDate = (dateString) => {
    if (!dateString || dateString === 'Never') return dateString;

    try {
      const date = new Date(dateString);
      return date.toLocaleString();
    } catch (e) {
      return dateString;
    }
  };

  return (
    <header className="header">
      <div className="header-content">
        <div className="header-left">
          <h1>ASX Stock Screener</h1>
          <p className="subtitle">ADX/DI Strategy</p>
        </div>

        <div className="header-right">
          {status && (
            <div className="status-info">
              <div className="status-item">
                <span className="label">Last Updated:</span>
                <span className="value">{formatDate(status.last_updated)}</span>
              </div>
              <div className="status-item">
                <span className="label">Signals:</span>
                <span className="value signal-count">{status.signals_count}</span>
              </div>
              <div className="status-item">
                <span className="label">Stocks:</span>
                <span className="value">{status.total_stocks}</span>
              </div>
            </div>
          )}

          <button
            className="refresh-button"
            onClick={onRefresh}
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing...' : '🔄 Refresh'}
          </button>
        </div>
      </div>
    </header>
  );
}

export default Header;
