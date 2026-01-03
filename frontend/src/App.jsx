/**
 * Main App Component
 *
 * Root component for the ASX Stock Screener application.
 */

import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import SignalList from './components/SignalList';
import { fetchSignals, fetchStatus, triggerRefresh } from './services/api';
import './App.css';

function App() {
  const [signals, setSignals] = useState([]);
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [minScore, setMinScore] = useState(0);
  const [strategyFilter, setStrategyFilter] = useState('all');
  const [error, setError] = useState(null);

  // Load data
  const loadData = async () => {
    try {
      setError(null);

      // Fetch signals and status in parallel
      const [signalsData, statusData] = await Promise.all([
        fetchSignals(minScore),
        fetchStatus()
      ]);

      setSignals(signalsData);
      setStatus(statusData);
    } catch (err) {
      console.error('Error loading data:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Handle refresh
  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await triggerRefresh();
      await loadData();
    } catch (err) {
      console.error('Error refreshing data:', err);
      setError(err.message);
    } finally {
      setRefreshing(false);
    }
  };

  // Load data on mount and when minScore changes
  useEffect(() => {
    loadData();
  }, [minScore]);

  // Auto-refresh every 5 minutes
  useEffect(() => {
    const interval = setInterval(loadData, 5 * 60 * 1000);
    return () => clearInterval(interval);
  }, [minScore]);

  // Filter signals by strategy
  const filteredSignals = strategyFilter === 'all'
    ? signals
    : signals.filter(signal => signal.strategy === strategyFilter);

  return (
    <div className="app">
      <Header
        status={status}
        onRefresh={handleRefresh}
        refreshing={refreshing}
      />

      <main className="main-content">
        {error && (
          <div className="error-message">
            <strong>Error:</strong> {error}
          </div>
        )}

        <SignalList
          signals={filteredSignals}
          loading={loading}
          minScore={minScore}
          onMinScoreChange={setMinScore}
          strategyFilter={strategyFilter}
          onStrategyFilterChange={setStrategyFilter}
        />
      </main>

      <footer className="footer">
        <p>ASX Stock Screener - Dual Strategy | 📈 Trend: ADX &gt; 30 &amp; DI+ &gt; DI- | 📉 Mean Rev: Price &gt; BB Upper &amp; RSI &gt; 70</p>
      </footer>
    </div>
  );
}

export default App;
