/**
 * Main App Component
 *
 * Root component for the ASX Stock Screener application.
 * Updated for "Dark Mode Pro" layout.
 */

import React, { useState, useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';
import Header from './components/Header';
import SignalList from './components/SignalList';
import Portfolio from './components/Portfolio';
import AddStockModal from './components/AddStockModal';
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
  
  // Modal states
  const [selectedStockToAdd, setSelectedStockToAdd] = useState(null);
  
  // Key to force refresh of Portfolio component when stock is added
  const [portfolioKey, setPortfolioKey] = useState(0);

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

  const formatLastUpdated = (dateString) => {
    if (!dateString) return '';
    try {
      return new Date(dateString).toLocaleString();
    } catch (e) {
      return dateString;
    }
  };

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

        <Routes>
          <Route path="/" element={
            <SignalList
              signals={filteredSignals}
              loading={loading}
              minScore={minScore}
              onMinScoreChange={setMinScore}
              strategyFilter={strategyFilter}
              onStrategyFilterChange={setStrategyFilter}
              onAddStock={(stock) => setSelectedStockToAdd(stock)}
            />
          } />
          <Route path="/portfolio" element={
            <Portfolio 
              key={portfolioKey} 
              onAddStock={() => setSelectedStockToAdd({})} 
            />
          } />
        </Routes>
      </main>

      {selectedStockToAdd && (
        <AddStockModal 
          stock={selectedStockToAdd} 
          onClose={() => setSelectedStockToAdd(null)}
          onAdded={() => {
            alert('Stock added to portfolio!');
            setPortfolioKey(prev => prev + 1);
          }}
        />
      )}

      <footer className="footer">
        <p>ASX Stock Screener Pro</p>
        <p style={{ fontSize: '0.8rem', marginTop: '4px', color: 'var(--color-text-muted)' }}>
          Strategies: Trend (ADX &gt; 30) • Mean Reversion (RSI &gt; 70)
        </p>
        {status?.last_updated && (
          <p style={{ marginTop: '8px', fontFamily: 'var(--font-body)' }}>
            Last Updated: {formatLastUpdated(status.last_updated)}
          </p>
        )}
      </footer>
    </div>
  );
}

export default App;
