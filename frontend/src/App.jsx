/**
 * Main App Component
 *
 * Root component for the ASX Stock Screener application.
 * Updated for "Dark Mode Pro" layout.
 */

import React, { useState, useEffect } from 'react';
import { Routes, Route } from 'react-router-dom';
import axios from 'axios';
import Header from './components/Header';
import SignalList from './components/SignalList';
import Portfolio from './components/Portfolio';
import InsiderTrades from './components/InsiderTrades';
import AddStockModal from './components/AddStockModal';
import StockSearchModal from './components/StockSearchModal';
import Toast from './components/Toast';
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
  const [toast, setToast] = useState(null);
  
  // Modal states
  const [selectedStockToAdd, setSelectedStockToAdd] = useState(null);
  const [showSearchModal, setShowSearchModal] = useState(false);
  const [searchModalTicker, setSearchModalTicker] = useState(null);
  
  // Key to force refresh of Portfolio component when stock is added
  const [portfolioKey, setPortfolioKey] = useState(0);

  const handleAddToWatchlist = async (signal) => {
    try {
      const token = localStorage.getItem('google_token');
      if (!token) {
        setToast({ message: 'Please login to add to watchlist', type: 'error' });
        return;
      }
      await axios.post('/api/watchlist', { 
        ticker: signal.ticker,
        notes: `Added from screener: ${signal.strategy}`
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setToast({ message: `${signal.ticker} added to watchlist!`, type: 'success' });
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to add to watchlist';
      setToast({ message: msg, type: 'error' });
    }
  };

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
      return new Date(dateString).toLocaleString('en-AU', {
        timeZone: 'Australia/Sydney',
        dateStyle: 'short',
        timeStyle: 'medium'
      });
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
        onSearch={() => {
            setSearchModalTicker(null); // Clear previous
            setShowSearchModal(true);
        }}
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
              onAddWatchlist={handleAddToWatchlist}
            />
          } />
          <Route path="/portfolio" element={
            <Portfolio 
              key={portfolioKey} 
              onAddStock={(stock) => setSelectedStockToAdd(stock)} 
              onShowToast={setToast}
            />
          } />
          <Route path="/insider-trades" element={
            <InsiderTrades 
              onAnalyze={(ticker) => {
                setSearchModalTicker(ticker);
                setShowSearchModal(true);
              }}
            />
          } />
        </Routes>
      </main>

      {showSearchModal && (
        <StockSearchModal 
          initialTicker={searchModalTicker}
          onClose={() => {
            setShowSearchModal(false);
            setSearchModalTicker(null);
          }}
          onAddStock={(stock) => setSelectedStockToAdd(stock)}
        />
      )}

      {selectedStockToAdd && (
        <AddStockModal 
          stock={selectedStockToAdd} 
          onClose={() => setSelectedStockToAdd(null)}
          onAdded={(msg) => {
            setToast({ message: msg || 'Stock added to portfolio!', type: 'success' });
            setPortfolioKey(prev => prev + 1);
          }}
          onError={(msg) => setToast({ message: msg, type: 'error' })}
        />
      )}

      {toast && (
        <Toast 
          key={Date.now()}
          message={toast.message} 
          type={toast.type} 
          onClose={() => setToast(null)} 
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
