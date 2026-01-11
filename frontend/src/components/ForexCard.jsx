/**
 * ForexCard Component - Power Filter Edition
 */

import React from 'react';
import { useAuth } from '../context/AuthContext';
import './SignalCard.css';

function ForexCard({ signal, onAdd }) {
  const { user } = useAuth();
  const getScoreClass = (score) => {
    if (score >= 80) return 'score-high';
    if (score >= 60) return 'score-medium';
    return 'score-low';
  };

  const isBuy = signal.signal === 'BUY';
  const { indicators } = signal;

  return (
    <div className={`signal-card ${signal.is_power_signal ? 'power-signal-border' : ''}`}>
      {signal.is_power_signal && (
        <div className="power-badge">⚡ POWER SIGNAL</div>
      )}
      
      <div className="card-header">
        <div className="card-title-group">
          <h3>{signal.name}</h3>
          <span className="company-name">{signal.symbol}</span>
        </div>
        <div className={`score-badge ${getScoreClass(signal.score)}`}>
          {signal.score.toFixed(0)}
        </div>
      </div>

      <div className="price-section">
        <span className="price-value">{signal.price}</span>
        <span className={`signal-direction ${isBuy ? 'positive' : 'negative'}`}>
          {signal.signal}
        </span>
      </div>

      <div className="indicators-grid">
        <div className="indicator">
          <span className="indicator-label">ADX</span>
          <span className="indicator-value">{indicators.ADX.toFixed(1)}</span>
        </div>
        <div className="indicator">
          <span className="indicator-label">Vol Accel</span>
          <span className={`indicator-value ${indicators.is_power_volume ? 'positive' : ''}`}>
            {indicators.vol_accel}x
          </span>
        </div>
        <div className="indicator">
          <span className="indicator-label">DI Momentum</span>
          <span className={`indicator-value ${indicators.is_power_momentum ? 'positive' : ''}`}>
            +{indicators.di_momentum.toFixed(1)}
          </span>
        </div>
        <div className="indicator">
          <span className="indicator-label">DI+ / DI-</span>
          <span className="indicator-value">
            {indicators.DIPlus.toFixed(0)} / {indicators.DIMinus.toFixed(0)}
          </span>
        </div>
      </div>

      <div className="card-footer">
        <span className="strategy-badge active">
          Power Trend (15m)
        </span>
        {user ? (
          <div className="card-actions">
            <button className="add-portfolio-btn" onClick={() => onAdd(signal)}>
              + Portfolio
            </button>
          </div>
        ) : (
          <span className="timestamp-small">
              {new Date(signal.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}
          </span>
        )}
      </div>
    </div>
  );
}

export default ForexCard;