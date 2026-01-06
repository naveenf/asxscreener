/**
 * SignalList Component
 *
 * List of all trading signals with filtering and sorting.
 * Updated for "Dark Mode Pro" dashboard design.
 */

import React from 'react';
import { useAuth } from '../context/AuthContext';
import SignalCard from './SignalCard';
import './SignalList.css';

function SignalList({ signals, loading, minScore, onMinScoreChange, strategyFilter, onStrategyFilterChange, onAddStock, onAddWatchlist }) {
  const { user } = useAuth();
  
  if (loading) {
    return (
      <div className="signal-list-container">
        <div className="loading">Loading signals...</div>
      </div>
    );
  }

  // Count signals by strategy for the dropdown labels (approximation since we might be filtering the parent list already? 
  // Actually, 'signals' passed here is already filtered by strategy in App.jsx. 
  // Ideally, we'd want the full counts, but for now we'll just show the count of *visible* signals or simplify the dropdown labels.)
  // Let's just keep simple labels to avoid confusion if we don't have the full list.
  
  return (
    <div className="signal-list-container">
      {!user && (
        <div className="guest-banner">
          <div className="banner-content">
            <span className="banner-icon">💹</span>
            <div className="banner-text">
              <h3>Unlock Full Potential</h3>
              <p>Log in to track these signals in your <strong>Personal Portfolio</strong> and <strong>Watchlist</strong>.</p>
            </div>
          </div>
          <div className="banner-features">
            <span className="feature-pill">Real-time Tracking</span>
            <span className="feature-pill">Profit/Loss Analytics</span>
            <span className="feature-pill">Custom Watchlists</span>
          </div>
        </div>
      )}

      {/* Filters Section */}
      <div className="filters">
        <div className="filter-group">
          <label className="filter-label">Minimum Score: {minScore}</label>
          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={minScore}
            onChange={(e) => onMinScoreChange(Number(e.target.value))}
            className="score-slider"
          />
        </div>

        <div className="filter-group">
          <label className="filter-label">Strategy</label>
          <select
            value={strategyFilter}
            onChange={(e) => onStrategyFilterChange(e.target.value)}
            className="strategy-select"
          >
            <option value="all">All Strategies</option>
            <option value="trend_following">Trend Following</option>
            <option value="mean_reversion">Mean Reversion</option>
          </select>
        </div>
      </div>

      {/* Section Header with Bungee Spice */}
      <div className="section-header">
        <h2 className="signal-count">
          SHOWING {signals.length} SIGNAL{signals.length !== 1 ? 'S' : ''}
        </h2>
      </div>

      {signals.length === 0 ? (
        <div className="no-signals">
          <h2>No signals found</h2>
          <p>Adjust your filters to see more results.</p>
        </div>
      ) : (
        <div className="signal-grid">
          {signals.map((signal) => (
            <SignalCard 
              key={`${signal.ticker}-${signal.strategy}`} 
              signal={signal} 
              onAdd={onAddStock}
              onWatchlist={onAddWatchlist}
            />
          ))}
        </div>
      )}
    </div>
  );
}

export default SignalList;