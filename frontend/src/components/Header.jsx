/**
 * Header Component
 *
 * Application header with title, status pills, and refresh button.
 */

import React from 'react';
import './Header.css';

function Header({ status, onRefresh, refreshing }) {
  return (
    <header className="header">
      <div className="header-content">
        <div className="header-left">
          <h1>ASX STOCK SCREENER</h1>
          <p className="subtitle">Pro Dashboard</p>
        </div>

        <div className="header-right">
          {status && (
            <div className="status-info">
              <div className="status-pill">
                <span className="label">Signals</span>
                <span className="value">{status.signals_count}</span>
              </div>
              <div className="status-pill">
                <span className="label">Stocks</span>
                <span className="value">{status.total_stocks}</span>
              </div>
            </div>
          )}

          <button
            className="refresh-button"
            onClick={onRefresh}
            disabled={refreshing}
          >
            {refreshing ? 'Refreshing...' : 'Refresh'}
          </button>
        </div>
      </div>
    </header>
  );
}

export default Header;