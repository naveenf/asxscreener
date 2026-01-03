/**
 * SignalCard Component
 *
 * Displays individual stock signal with score and indicators.
 */

import React from 'react';
import './SignalCard.css';

function SignalCard({ signal }) {
  const getScoreClass = (score) => {
    if (score >= 70) return 'score-high';
    if (score >= 50) return 'score-medium';
    return 'score-low';
  };

  const formatPrice = (price) => {
    return `$${price.toFixed(2)}`;
  };

  const getStrategyBadge = () => {
    const strategy = signal.strategy || 'trend_following';
    if (strategy === 'trend_following') {
      return <span className="strategy-badge trend">📈 Trend</span>;
    } else if (strategy === 'mean_reversion') {
      return <span className="strategy-badge mean-rev">📉 Mean Rev</span>;
    }
    return null;
  };

  const renderIndicators = () => {
    const strategy = signal.strategy || 'trend_following';

    if (strategy === 'trend_following') {
      return (
        <>
          <div className="indicator">
            <span className="indicator-label">ADX</span>
            <span className="indicator-value">{signal.indicators.ADX?.toFixed(1)}</span>
          </div>

          <div className="indicator">
            <span className="indicator-label">DI+</span>
            <span className="indicator-value positive">{signal.indicators.DIPlus?.toFixed(1)}</span>
          </div>

          <div className="indicator">
            <span className="indicator-label">DI-</span>
            <span className="indicator-value negative">{signal.indicators.DIMinus?.toFixed(1)}</span>
          </div>

          {signal.indicators.SMA200 && (
            <div className="indicator">
              <span className="indicator-label">SMA200</span>
              <span className="indicator-value">{signal.indicators.SMA200.toFixed(2)}</span>
            </div>
          )}
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
            <span className="indicator-label">BB Upper</span>
            <span className="indicator-value">{signal.indicators.BB_Upper?.toFixed(2)}</span>
          </div>

          <div className="indicator">
            <span className="indicator-label">BB Middle</span>
            <span className="indicator-value">{signal.indicators.BB_Middle?.toFixed(2)}</span>
          </div>

          {signal.indicators.BB_Distance_PCT && (
            <div className="indicator">
              <span className="indicator-label">Distance</span>
              <span className="indicator-value positive">{signal.indicators.BB_Distance_PCT.toFixed(2)}%</span>
            </div>
          )}
        </>
      );
    }
  };

  const renderBadges = () => {
    const strategy = signal.strategy || 'trend_following';

    if (strategy === 'trend_following') {
      return (
        <>
          {signal.indicators.above_sma200 && (
            <span className="badge badge-success">Above 200 SMA</span>
          )}
          {signal.entry_conditions?.fresh_crossover && (
            <span className="badge badge-info">Fresh Crossover</span>
          )}
          {signal.entry_conditions?.adx_above_30 && (
            <span className="badge badge-primary">Strong Trend</span>
          )}
        </>
      );
    } else if (strategy === 'mean_reversion') {
      return (
        <>
          {signal.entry_conditions?.rsi_overbought && (
            <span className="badge badge-warning">RSI Overbought</span>
          )}
          {signal.entry_conditions?.price_above_upper_bb && (
            <span className="badge badge-info">Above BB Upper</span>
          )}
          {signal.indicators.below_sma200 && (
            <span className="badge badge-secondary">Counter Trend</span>
          )}
        </>
      );
    }
  };

  return (
    <div className="signal-card">
      <div className="card-header">
        <div className="card-title">
          <h3>{signal.ticker}</h3>
          {getStrategyBadge()}
          <span className={`score ${getScoreClass(signal.score)}`}>
            {signal.score.toFixed(1)}
          </span>
        </div>
        <p className="company-name">{signal.name}</p>
        {signal.sector && <span className="sector-tag">{signal.sector}</span>}
      </div>

      <div className="card-body">
        <div className="price-section">
          <span className="price-label">Current Price</span>
          <span className="price-value">{formatPrice(signal.current_price)}</span>
        </div>

        <div className="indicators-grid">
          {renderIndicators()}
        </div>

        <div className="badges">
          {renderBadges()}
        </div>
      </div>
    </div>
  );
}

export default SignalCard;
