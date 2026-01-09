import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import './InsiderTrades.css';

function InsiderTrades({ onAnalyze }) {
  const [groups, setGroupedTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedTickers, setExpandedTickers] = useState(new Set());
  const [sortOption, setSortOption] = useState('abs_value');

  const fetchTrades = async () => {
    try {
      setLoading(true);
      const response = await axios.get('/api/insider-trades');
      setGroupedTrades(response.data);
    } catch (err) {
      console.error('Error fetching insider trades:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrades();
  }, []);

  const toggleExpand = (ticker) => {
    const newExpanded = new Set(expandedTickers);
    if (newExpanded.has(ticker)) {
      newExpanded.delete(ticker);
    } else {
      newExpanded.add(ticker);
    }
    setExpandedTickers(newExpanded);
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-AU', {
      style: 'currency',
      currency: 'AUD',
      maximumFractionDigits: 0
    }).format(value);
  };

  const sortedGroups = useMemo(() => {
    let sorted = [...groups];
    switch (sortOption) {
      case 'value_desc': // Top Buyers
        sorted.sort((a, b) => b.net_value - a.net_value);
        break;
      case 'value_asc': // Top Sellers
        sorted.sort((a, b) => a.net_value - b.net_value);
        break;
      case 'date_desc': // Most Recent
        sorted.sort((a, b) => {
          const dateA = a.trades.reduce((max, t) => t.date > max ? t.date : max, '');
          const dateB = b.trades.reduce((max, t) => t.date > max ? t.date : max, '');
          return dateB.localeCompare(dateA);
        });
        break;
      case 'ticker_asc': // Alphabetical
        sorted.sort((a, b) => a.ticker.localeCompare(b.ticker));
        break;
      case 'abs_value': // High Impact (Absolute Value)
      default:
        sorted.sort((a, b) => Math.abs(b.net_value) - Math.abs(a.net_value));
        break;
    }
    return sorted;
  }, [groups, sortOption]);

  if (loading) {
    return <div className="loading">Loading significant insider trades...</div>;
  }

  return (
    <div className="insider-trades-container">
      <div className="insider-header">
        <div className="header-title-section">
          <h2>Significant Insider Trades</h2>
          <div className="insider-summary">
            Last 30 Days • On-market trades &gt; $50,000
          </div>
        </div>
        
        <div className="sort-controls">
          <label htmlFor="sort-select">Sort By:</label>
          <select 
            id="sort-select"
            value={sortOption} 
            onChange={(e) => setSortOption(e.target.value)}
            className="sort-select"
          >
            <option value="abs_value">High Impact (Abs Value)</option>
            <option value="value_desc">Top Buyers (Highest Net)</option>
            <option value="value_asc">Top Sellers (Lowest Net)</option>
            <option value="date_desc">Most Recent</option>
            <option value="ticker_asc">Ticker (A-Z)</option>
          </select>
        </div>
      </div>

      {sortedGroups.length === 0 ? (
        <div className="no-trades">
          <p>No significant on-market director trades detected in the last 30 days.</p>
        </div>
      ) : (
        <div className="trades-list">
          {sortedGroups.map((group) => (
            <div 
              key={group.ticker} 
              className={`ticker-group ${expandedTickers.has(group.ticker) ? 'expanded' : ''}`}
            >
              <div className="group-summary" onClick={() => toggleExpand(group.ticker)}>
                <div className="group-ticker">{group.ticker}</div>
                <div className="group-name">{group.company_name}</div>
                <div className={`group-value ${group.net_value >= 0 ? 'value-buy' : 'value-sell'}`}>
                  {group.net_value >= 0 ? '+' : ''}{formatCurrency(group.net_value)}
                </div>
                <div className="group-trades-count">
                  {group.total_trades} {group.total_trades === 1 ? 'Trade' : 'Trades'}
                </div>
                <div className="expand-icon">▾</div>
              </div>

              {expandedTickers.has(group.ticker) && (
                <div className="trades-detail">
                  <table className="detail-table">
                    <thead>
                      <tr>
                        <th>Director</th>
                        <th>Type</th>
                        <th>Date</th>
                        <th>Amount</th>
                        <th>Price</th>
                        <th>Value</th>
                      </tr>
                    </thead>
                    <tbody>
                      {group.trades.map((trade) => (
                        <tr key={trade.id}>
                          <td>{trade.director}</td>
                          <td>
                            <span className={`type-badge ${trade.type.toLowerCase() === 'buy' ? 'type-buy' : 'type-sell'}`}>
                              {trade.type}
                            </span>
                          </td>
                          <td>{trade.date_formatted}</td>
                          <td>{trade.amount}</td>
                          <td>${trade.price.toFixed(3)}</td>
                          <td style={{ fontWeight: 'bold' }}>{formatCurrency(trade.value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <button 
                    className="analyze-btn"
                    onClick={() => onAnalyze(group.ticker)}
                  >
                    Quick Analysis for {group.ticker}
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default InsiderTrades;
