import React, { useState, useEffect } from 'react';
import { fetchTradeHistory } from '../services/api';
import '../styles/TradeHistory.css';

const TradeHistory = () => {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Default to today (2026-02-19) to show only synced trades
  const getTodayDate = () => new Date().toISOString().split('T')[0];

  // Filters
  const [startDate, setStartDate] = useState(getTodayDate());
  const [endDate, setEndDate] = useState(getTodayDate());
  const [selectedSymbol, setSelectedSymbol] = useState('all');
  const [selectedStrategy, setSelectedStrategy] = useState('all');
  const [sortBy, setSortBy] = useState('sell_date');
  const [statusFilter, setStatusFilter] = useState('all'); // 'all', 'OPEN', 'CLOSED'

  const loadTrades = async () => {
    setLoading(true);
    try {
      const params = {};
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      if (selectedSymbol !== 'all') params.symbol = selectedSymbol;
      if (selectedStrategy !== 'all') params.strategy = selectedStrategy;
      if (statusFilter !== 'all') params.status = statusFilter; // Only set if not 'all'
      params.sort_by = sortBy;

      // Fetch from Firestore (synced with Oanda, source of truth)
      const data = await fetchTradeHistory(params);
      setTrades(data);
      setError(null);
    } catch (err) {
      setError('Failed to load trade history from Firestore');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTrades();
  }, [statusFilter, sortBy]); // Reload when status or sort changes

  const syncOandaTrades = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('google_token');
      const response = await fetch('/api/forex-portfolio/sync-oanda-closes', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to sync trades');
      }

      const result = await response.json();
      setError(null);

      if (result.synced > 0) {
        alert(`✅ Synced ${result.synced} closed trades from Oanda!\nReload to see updated exit prices and P&L.`);
        setTimeout(() => loadTrades(), 1000);
      } else {
        alert('No new closed trades to sync from Oanda.');
      }
    } catch (err) {
      setError('Failed to sync from Oanda');
      alert('❌ Sync failed: ' + err.message);
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleExport = () => {
    if (trades.length === 0) return;

    const headers = ['Date', 'Symbol', 'Direction', 'Strategy', 'Entry', 'Exit', 'P&L (AUD)', 'Gain %', 'R:R'];
    const csvData = trades.map(t => [
      t.sell_date || t.buy_date,
      t.symbol,
      t.direction,
      t.strategy || 'N/A',
      t.buy_price.toFixed(5),
      t.sell_price?.toFixed(5) || 'N/A',
      t.realized_gain_aud?.toFixed(2) || '0.00',
      t.gain_loss_percent.toFixed(2),
      t.actual_rr?.toFixed(2) || 'N/A'
    ]);

    const csvContent = [headers, ...csvData].map(e => e.join(",")).join("\n");
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", `trade_history_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const symbols = ['all', ...new Set(trades.map(t => t.symbol))];
  const strategies = ['all', ...new Set(trades.map(t => t.strategy).filter(Boolean))];

  return (
    <div className="trade-history">
      <div className="history-header">
        <h2>Trade History</h2>
        <div className="header-buttons">
          <button className="sync-btn" onClick={syncOandaTrades} title="Sync closed trades from Oanda">
            🔄 Sync from Oanda
          </button>
          <button className="export-btn" onClick={handleExport} disabled={trades.length === 0}>
            Export CSV
          </button>
        </div>
      </div>

      {/* Status Toggle Buttons */}
      <div className="status-toggle">
        <label>Show:</label>
        <button
          className={`status-btn ${statusFilter === 'all' ? 'active' : ''}`}
          onClick={() => setStatusFilter('all')}
        >
          All Trades ({trades.length})
        </button>
        <button
          className={`status-btn ${statusFilter === 'OPEN' ? 'active' : ''}`}
          onClick={() => setStatusFilter('OPEN')}
        >
          Open Only
        </button>
        <button
          className={`status-btn ${statusFilter === 'CLOSED' ? 'active' : ''}`}
          onClick={() => setStatusFilter('CLOSED')}
        >
          Closed Only
        </button>
      </div>

      <div className="filters-bar">
        <div className="filter-group">
          <label>From:</label>
          <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </div>
        <div className="filter-group">
          <label>To:</label>
          <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
        <div className="filter-group">
          <label>Symbol:</label>
          <select value={selectedSymbol} onChange={(e) => setSelectedSymbol(e.target.value)}>
            {symbols.map(s => <option key={s} value={s}>{s.replace('_', '/')}</option>)}
          </select>
        </div>
        <div className="filter-group">
          <label>Strategy:</label>
          <select value={selectedStrategy} onChange={(e) => setSelectedStrategy(e.target.value)}>
            {strategies.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <button className="load-btn" onClick={loadTrades}>Apply Filters</button>
      </div>

      {loading ? (
        <div className="loading-state">Loading trade history...</div>
      ) : error ? (
        <div className="error-state">{error}</div>
      ) : trades.length === 0 ? (
        <div className="empty-state">
          {statusFilter === 'CLOSED' && "No closed trades found. Trades appear here once they are exited."}
          {statusFilter === 'OPEN' && "No open trades found. You currently have no active positions."}
          {statusFilter === 'all' && "No trades found for the selected filters. Try adjusting the date range or clearing filters."}
        </div>
      ) : (
        <div className="table-container">
          <table className="trades-table">
            <thead>
              <tr>
                <th onClick={() => setSortBy('sell_date')}>Date</th>
                <th onClick={() => setSortBy('symbol')}>Symbol</th>
                <th>Strategy</th>
                <th>Entry</th>
                <th>Exit</th>
                <th onClick={() => setSortBy('realized_gain_aud')}>P&L (AUD)</th>
                <th onClick={() => setSortBy('gain_loss_percent')}>%</th>
                <th>R:R</th>
              </tr>
            </thead>
            <tbody>
              {trades.map(trade => (
                <tr key={trade.id}>
                  <td>{trade.sell_date || trade.buy_date}</td>
                  <td className="symbol-cell">{trade.symbol.replace('_', '/')}</td>
                  <td><span className="strategy-tag">{trade.strategy || 'Manual'}</span></td>
                  <td>{trade.buy_price.toFixed(5)}</td>
                  <td>{trade.sell_price?.toFixed(5)}</td>
                  <td className={trade.realized_gain_aud >= 0 ? 'positive' : 'negative'}>
                    ${trade.realized_gain_aud?.toFixed(2)}
                  </td>
                  <td className={trade.gain_loss_percent >= 0 ? 'positive' : 'negative'}>
                    {trade.gain_loss_percent.toFixed(2)}%
                  </td>
                  <td>{trade.actual_rr?.toFixed(2) || 'N/A'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default TradeHistory;
