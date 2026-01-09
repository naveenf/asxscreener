import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './InsiderTrades.css';

function InsiderTrades({ onAnalyze }) {
  const [groups, setGroupedTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedTickers, setExpandedTickers] = useState(new Set());

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

  if (loading) {
    return <div className="loading">Loading significant insider trades...</div>;
  }

  return (
    <div className="insider-trades-container">
      <div className="insider-header">
        <h2>Significant Insider Trades</h2>
        <div className="insider-summary">
          Last 30 Days • On-market trades &gt; $50,000
        </div>
      </div>

      {groups.length === 0 ? (
        <div className="no-trades">
          <p>No significant on-market director trades detected in the last 30 days.</p>
        </div>
      ) : (
        <div className="trades-list">
          {groups.map((group) => (
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
