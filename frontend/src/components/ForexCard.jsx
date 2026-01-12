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

  // Helper to format price based on magnitude (e.g. 1.0800 vs 150.00 vs 35000)
  const formatPrice = (val) => {
    if (val === undefined || val === null) return '-';
    const num = parseFloat(val);
    if (isNaN(num)) return val;
    if (num > 500) return num.toFixed(2); // Indices, Gold
    if (num > 50) return num.toFixed(3);  // Oil, JPY pairs
    return num.toFixed(5);                // Standard Forex
  };

  const renderIndicators = () => {
    if (signal.strategy === 'Squeeze') {
      return (
        <>
          <div className="indicator">
            <span className="indicator-label">ADX</span>
            <span className="indicator-value">{indicators.ADX?.toFixed(1) || '-'}</span>
          </div>
          <div className="indicator">
            <span className="indicator-label">BB Width</span>
            <span className="indicator-value">{indicators.BB_Width?.toFixed(4) || '-'}</span>
          </div>
          <div className="indicator">
            <span className="indicator-label">Vol Accel</span>
            <span className="indicator-value">{indicators.vol_accel ? `${indicators.vol_accel}x` : '-'}</span>
          </div>
        </>
      );
    }
    
    // Default / TrendFollowing
    return (
      <>
        <div className="indicator">
          <span className="indicator-label">ADX</span>
          <span className="indicator-value">{indicators.ADX?.toFixed(1) || '-'}</span>
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
            {indicators.di_momentum > 0 ? '+' : ''}{indicators.di_momentum?.toFixed(1) || '0.0'}
          </span>
        </div>
        <div className="indicator">
          <span className="indicator-label">DI+ / DI-</span>
          <span className="indicator-value">
            {indicators.DIPlus?.toFixed(0) || 0} / {indicators.DIMinus?.toFixed(0) || 0}
          </span>
        </div>
      </>
    );
  };

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
        <span className="price-value">{formatPrice(signal.price)}</span>
        <span className={`signal-direction ${isBuy ? 'positive' : 'negative'}`}>
          {signal.signal}
        </span>
      </div>

      {/* Trade Setup Row (SL/TP) */}
      {(signal.stop_loss || signal.take_profit) && (
        <div className="trade-setup-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', marginBottom: '12px', padding: '0 8px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
            <span style={{ color: '#888' }}>SL:</span>
            <span style={{ fontFamily: 'monospace', color: '#ff6b6b' }}>{formatPrice(signal.stop_loss)}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.85rem' }}>
            <span style={{ color: '#888' }}>TP:</span>
            <span style={{ fontFamily: 'monospace', color: '#4ecdc4' }}>{formatPrice(signal.take_profit)}</span>
          </div>
        </div>
      )}

      <div className="indicators-grid">
        {renderIndicators()}
      </div>

      <div className="card-footer">
        <span className="strategy-badge active">
          {signal.strategy === 'TrendFollowing' ? 'Power Trend' : signal.strategy} ({signal.timeframe_used || '15m'})
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