/**
 * ForexList Component
 *
 * Dashboard for Forex and Commodity signals.
 */

import React, { useState, useEffect } from 'react';
import { fetchForexSignals, triggerForexRefresh, fetchRefreshStatus } from '../services/api';
import ForexCard from './ForexCard';
import './SignalList.css'; // Reuse base styles

function ForexList({ onAddStock, onShowToast }) {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [error, setError] = useState(null);

  const pollRefreshStatus = () => {
    return new Promise((resolve, reject) => {
      const interval = setInterval(async () => {
        try {
          const status = await fetchRefreshStatus();
          const task = status.forex;
          if (!task.in_progress) {
            clearInterval(interval);
            if (task.error) reject(new Error(task.error));
            else resolve();
          }
        } catch (err) {
          clearInterval(interval);
          reject(err);
        }
      }, 3000);
    });
  };

  const loadData = async () => {
    try {
      setLoading(true);
      const data = await fetchForexSignals();
      setSignals(data.signals || []);
      setLastUpdated(data.generated_at);
      setError(null);
    } catch (err) {
      setError("Failed to load forex signals.");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    try {
      setRefreshing(true);
      await triggerForexRefresh();
      if (onShowToast) onShowToast({ message: 'Forex refresh started...', type: 'info' });
      
      await pollRefreshStatus();
      
      await loadData();
      if (onShowToast) onShowToast({ message: 'Forex refresh complete!', type: 'success' });
    } catch (err) {
      alert("Refresh failed: " + err.message);
      if (onShowToast) onShowToast({ message: 'Forex refresh failed', type: 'error' });
    } finally {
      setRefreshing(false);
    }
  };

  useEffect(() => {
    loadData();
    
    // Listen for global refresh events
    const handleGlobalRefresh = () => {
      console.log("Global refresh detected, updating forex list...");
      loadData();
    };
    window.addEventListener('data-refreshed', handleGlobalRefresh);

    // Auto refresh every 5 minutes
    const interval = setInterval(loadData, 5 * 60 * 1000);
    return () => {
      clearInterval(interval);
      window.removeEventListener('data-refreshed', handleGlobalRefresh);
    };
  }, []);

  if (loading && !signals.length) {
    return <div className="loading">Loading Forex Signals...</div>;
  }

  return (
    <div className="signal-list-container">
      <div className="section-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h2 className="signal-count">
          FOREX & COMMODITIES
        </h2>
        <button 
          className="refresh-button" 
          onClick={handleRefresh} 
          disabled={refreshing}
          style={{ margin: 0 }}
        >
          {refreshing ? 'Refreshing...' : 'Refresh Forex'}
        </button>
      </div>

      {lastUpdated && (
        <p className="last-updated-hint">
          Last Updated: {new Date(lastUpdated).toLocaleString()}
        </p>
      )}

      {error && <div className="error-message">{error}</div>}

      {signals.length === 0 ? (
        <div className="no-signals">
          <h2>No signals found</h2>
          <p>The markets might be quiet or data is still being processed.</p>
        </div>
      ) : (
        <div className="signal-grid">
          {signals.map((signal) => (
            <ForexCard key={signal.symbol} signal={signal} onAdd={onAddStock} />
          ))}
        </div>
      )}
    </div>
  );
}

export default ForexList;
