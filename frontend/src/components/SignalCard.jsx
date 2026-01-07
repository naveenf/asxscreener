/**
 * SignalCard Component
 *
 * Displays individual stock signal with score and indicators.
 * Updated for "Dark Mode Pro" Glassmorphism design.
 */

import React from 'react';
import { useAuth } from '../context/AuthContext';
import './SignalCard.css';

function SignalCard({ signal, onAdd, onWatchlist }) {
  const { user } = useAuth();
  const getScoreClass = (score) => {
    if (score >= 70) return 'score-high';
    if (score >= 50) return 'score-medium';
    return 'score-low';
  };

  const formatPrice = (price) => {
    return `$${price.toFixed(2)}`;
  };

  const renderIndicators = () => {
    const strategy = signal.strategy || 'trend_following';

    if (strategy === 'trend_following') {
      return (
        <>
          <div className="indicator">
            <span className="indicator-label">Fib Pos</span>
            <span className={`indicator-value ${signal.indicators.Fib_Pos > 0 ? 'positive' : 'negative'}`}>
              {signal.indicators.Fib_Pos > 0 ? 'BULL' : 'BEAR'}
            </span>
          </div>

          <div className="indicator">
            <span className="indicator-label">Supertrend</span>
            <span className={`indicator-value ${signal.indicators.PP_Trend === 1 ? 'positive' : 'negative'}`}>
              {signal.indicators.PP_Trend === 1 ? 'BULL' : 'BEAR'}
            </span>
          </div>

          <div className="indicator">
            <span className="indicator-label">IT Trigger</span>
            <span className="indicator-value">{signal.indicators.IT_Trigger?.toFixed(2)}</span>
          </div>

          <div className="indicator">
            <span className="indicator-label">IT Trend</span>
            <span className="indicator-value">{signal.indicators.IT_Trend?.toFixed(2)}</span>
          </div>
        </>
      );
    } else if (strategy === 'mean_reversion') {
      return (
        <>
          <div className="indicator">
            <span className="indicator-label">RSI</span>
            <span className="indicator-value">{signal.indicators.RSI?.toFixed(1)}</span>
          </div>

          <div className="indicator">
            <span className="indicator-label">BB Upp</span>
            <span className="indicator-value">{signal.indicators.BB_Upper?.toFixed(2)}</span>
          </div>

          <div className="indicator">
            <span className="indicator-label">Dist%</span>
            <span className="indicator-value positive">{signal.indicators.BB_Distance_PCT?.toFixed(1)}%</span>
          </div>
        </>
      );
    }
  };

  const getStrategyName = () => {
    const strategy = signal.strategy || 'trend_following';
    return strategy === 'trend_following' ? 'Trend Following' : 'Mean Reversion';
  };

  return (
    <div className="signal-card">
      {/* Header: Title Left, Score Right */}
      <div className="card-header">
        <div className="card-title-group">
          <h3>{signal.ticker}</h3>
          <span className="company-name">{signal.name}</span>
        </div>
        <div className={`score-badge ${getScoreClass(signal.score)}`}>
          {signal.score.toFixed(0)}
        </div>
      </div>

      {/* Price Section */}
      <div className="price-section">
        <span className="price-value">{formatPrice(signal.current_price)}</span>
        {signal.sector && <span className="sector-tag">{signal.sector}</span>}
      </div>

      {/* Grid of Data */}
      <div className="indicators-grid">
        {renderIndicators()}
      </div>

      {/* Footer: Strategy Tag & Badges */}
      <div className="card-footer">
        <span className="strategy-badge active">
          {getStrategyName()}
        </span>
        {user && (
          <div className="card-actions">
            <button className="add-watchlist-btn-small" onClick={() => onWatchlist(signal)}>
              + Watch
            </button>
            <button className="add-portfolio-btn" onClick={() => onAdd(signal)}>
              + Portfolio
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default SignalCard;