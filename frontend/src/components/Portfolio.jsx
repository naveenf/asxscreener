import React, { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import Watchlist from './Watchlist';
import ConfirmModal from './ConfirmModal';
import SellStockModal from './SellStockModal';
import './Portfolio.css';

const Portfolio = ({ onAddStock, onShowToast }) => {
  const { user, logout } = useAuth();
  const [portfolio, setPortfolio] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [sellingStock, setSellingStock] = useState(null);
  
  // UI State for grouping
  const [expandedGroups, setExpandedGroups] = useState({}); // { ticker: boolean }
  const [groupTabs, setGroupTabs] = useState({}); // { ticker: 'active' | 'history' }

  const fetchPortfolio = async () => {
    try {
      const token = localStorage.getItem('google_token');
      const response = await axios.get('/api/portfolio', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setPortfolio(response.data);
    } catch (err) {
      if (err.response && err.response.status === 401) {
        logout();
        if (onShowToast) {
          onShowToast({ message: 'Session expired. Please login again.', type: 'error' });
        }
      } else {
        setError('Failed to fetch portfolio');
        console.error(err);
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPortfolio();
  }, []);

  // Grouping Logic
  const groupedPortfolio = useMemo(() => {
    const groups = {};
    
    portfolio.forEach(item => {
        const ticker = item.ticker;
        if (!groups[ticker]) {
            groups[ticker] = {
                ticker,
                active_items: [],
                history_items: [],
                total_qty: 0,
                total_cost_basis: 0,
                total_market_value: 0,
                total_gain_loss: 0,
                current_price: item.current_price, // Assumes all items with same ticker have same current price
                trend_signal: null,
                strategy_type: item.strategy_type
            };
        }
        
        if (item.status === 'CLOSED') {
            groups[ticker].history_items.push(item);
        } else {
            groups[ticker].active_items.push(item);
            groups[ticker].total_qty += item.quantity;
            // Cost basis for group summary (Buy Price * Qty + Brokerage)
            const itemCost = (item.buy_price * item.quantity) + (item.brokerage || 0);
            groups[ticker].total_cost_basis += itemCost;
            groups[ticker].total_market_value += (item.current_value || 0);
            groups[ticker].total_gain_loss += (item.gain_loss || 0);
            
            // Use signal from first active item
            if (!groups[ticker].trend_signal) {
                groups[ticker].trend_signal = item.trend_signal;
                groups[ticker].exit_reason = item.exit_reason;
            }
        }
    });
    
    // Sort groups by ticker
    return Object.values(groups).sort((a, b) => a.ticker.localeCompare(b.ticker));
  }, [portfolio]);

  const toggleGroup = (ticker) => {
    setExpandedGroups(prev => ({
        ...prev,
        [ticker]: !prev[ticker]
    }));
    // Set default tab if opening
    if (!expandedGroups[ticker]) {
        setGroupTabs(prev => ({ ...prev, [ticker]: 'active' }));
    }
  };

  const setTab = (ticker, tab) => {
      setGroupTabs(prev => ({ ...prev, [ticker]: tab }));
  };

  const handleDelete = (item) => {
    setDeleteConfirm(item);
  };

  const confirmDelete = async () => {
    const id = deleteConfirm.id;
    try {
      const token = localStorage.getItem('google_token');
      await axios.delete(`/api/portfolio/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setPortfolio(portfolio.filter(item => item.id !== id));
      if (onShowToast) {
        onShowToast({ message: 'Record removed', type: 'success' });
      }
    } catch (err) {
      if (onShowToast) {
        onShowToast({ message: 'Delete failed', type: 'error' });
      }
    } finally {
      setDeleteConfirm(null);
    }
  };

  const formatCurrency = (val) => {
    return new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD' }).format(val);
  };

  const formatPercent = (val) => {
    return new Intl.NumberFormat('en-AU', { style: 'percent', minimumFractionDigits: 2 }).format(val / 100);
  };

  // Portfolio Totals
  const calculateTotalValue = () => {
    return groupedPortfolio.reduce((acc, group) => acc + group.total_market_value, 0);
  };
  
  const calculateTotalGain = () => {
    return groupedPortfolio.reduce((acc, group) => acc + group.total_gain_loss, 0);
  };

  const calculateTotalGainPercent = () => {
    const totalCost = groupedPortfolio.reduce((acc, group) => acc + group.total_cost_basis, 0);
    const totalGain = calculateTotalGain();
    if (totalCost === 0) return 0;
    return (totalGain / totalCost) * 100;
  };

  return (
    <div className="portfolio-page">
      <div className="portfolio-header">
        <div className="header-title">
          <h2>MY PORTFOLIO</h2>
          {!loading && portfolio.length > 0 && (
            <div className="portfolio-summary">
              <span className="summary-item">
                Total Value: <span className="val">{formatCurrency(calculateTotalValue())}</span>
              </span>
              <span className="summary-item">
                Total Gain: <span className={`val ${calculateTotalGain() >= 0 ? 'positive' : 'negative'}`}>
                  {formatCurrency(calculateTotalGain())}
                </span>
                <span className={`val-percent ${calculateTotalGainPercent() >= 0 ? 'positive' : 'negative'}`}>
                  ({formatPercent(calculateTotalGainPercent())})
                </span>
              </span>
            </div>
          )}
        </div>
        <button className="add-stock-btn" onClick={() => onAddStock({})}>+ Add Stock</button>
      </div>

      {loading ? (
        <div className="loading-state">Loading market data...</div>
      ) : error ? (
        <p className="error">{error}</p>
      ) : groupedPortfolio.length === 0 ? (
        <p className="empty-msg">No stocks in your portfolio yet. Add them from the screener or manually!</p>
      ) : (
        <div className="portfolio-table-container">
            <table className="portfolio-table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Strategy</th>
                  <th>Total Qty</th>
                  <th>Avg Cost</th>
                  <th>Current Price</th>
                  <th>Trend</th>
                  <th>Market Value</th>
                  <th>Unrealized G/L</th>
                </tr>
              </thead>
              <tbody>
                {groupedPortfolio.map(group => (
                  <React.Fragment key={group.ticker}>
                      {/* Group Summary Row */}
                      <tr 
                        className={`group-row ${expandedGroups[group.ticker] ? 'expanded' : ''}`}
                        onClick={() => toggleGroup(group.ticker)}
                      >
                        <td className="ticker">
                            <span className="toggle-icon">▶</span>
                            {group.ticker}
                        </td>
                        <td className="strategy-cell">
                            <span className={`strategy-badge ${group.strategy_type}`}>
                                {group.strategy_type === 'triple_trend' ? 'Trend' : 'Mean Rev'}
                            </span>
                        </td>
                        <td>{group.total_qty > 0 ? group.total_qty : '-'}</td>
                        <td>
                            {group.total_qty > 0 
                                ? formatCurrency(group.total_cost_basis / group.total_qty) 
                                : '-'}
                        </td>
                        <td>
                            {group.current_price 
                                ? `$${group.current_price.toFixed(2)}` 
                                : <span className="loading-dots">...</span>
                            }
                        </td>
                        <td className="trend-cell">
                          {group.total_qty > 0 ? (
                            <>
                                <div className={`trend-signal ${group.trend_signal}`}>
                                    {group.trend_signal}
                                </div>
                                {group.exit_reason && (
                                    <div className="trend-reason">{group.exit_reason}</div>
                                )}
                            </>
                          ) : (
                              <span style={{opacity:0.5}}>Closed</span>
                          )}
                        </td>
                        <td className="value">
                            {group.total_qty > 0 ? formatCurrency(group.total_market_value) : '-'}
                        </td>
                        <td className={`gain-loss ${group.total_gain_loss >= 0 ? 'positive' : 'negative'}`}>
                            {group.total_qty > 0 ? (
                                <>
                                    <div>{formatCurrency(group.total_gain_loss)}</div>
                                    <div className="percent">
                                        {group.total_gain_loss >= 0 ? '+' : ''}
                                        {formatPercent(group.total_gain_loss / group.total_cost_basis * 100)}
                                    </div>
                                </>
                            ) : '-'}
                        </td>
                      </tr>

                      {/* Expanded Details Row */}
                      {expandedGroups[group.ticker] && (
                          <tr className="details-row">
                              <td colSpan="8" className="details-cell">
                                  <div className="details-container">
                                      <div className="details-tabs">
                                          <button 
                                            className={`details-tab ${groupTabs[group.ticker] !== 'history' ? 'active' : ''}`}
                                            onClick={(e) => { e.stopPropagation(); setTab(group.ticker, 'active'); }}
                                          >
                                              Active Holdings ({group.active_items.length})
                                          </button>
                                          <button 
                                            className={`details-tab ${groupTabs[group.ticker] === 'history' ? 'active' : ''}`}
                                            onClick={(e) => { e.stopPropagation(); setTab(group.ticker, 'history'); }}
                                          >
                                              Transaction History ({group.history_items.length})
                                          </button>
                                      </div>

                                      {/* ACTIVE HOLDINGS TABLE */}
                                      {groupTabs[group.ticker] !== 'history' && (
                                          <table className="details-table">
                                              <thead>
                                                  <tr>
                                                      <th>Buy Date</th>
                                                      <th>Qty</th>
                                                      <th>Buy Price</th>
                                                      <th>Brokerage</th>
                                                      <th>Cost Basis</th>
                                                      <th>Market Value</th>
                                                      <th>Gain/Loss</th>
                                                      <th>Actions</th>
                                                  </tr>
                                              </thead>
                                              <tbody>
                                                  {group.active_items.length === 0 ? (
                                                      <tr><td colSpan="8" style={{textAlign:'center', padding:'20px'}}>No active holdings</td></tr>
                                                  ) : (
                                                      group.active_items.map(item => (
                                                          <tr key={item.id}>
                                                              <td>{new Date(item.buy_date).toLocaleDateString()}</td>
                                                              <td>{item.quantity}</td>
                                                              <td>{formatCurrency(item.buy_price)}</td>
                                                              <td>{formatCurrency(item.brokerage)}</td>
                                                              <td>{formatCurrency((item.buy_price * item.quantity) + (item.brokerage || 0))}</td>
                                                              <td>{formatCurrency(item.current_value)}</td>
                                                              <td className={item.gain_loss >= 0 ? 'positive' : 'negative'} style={{fontWeight:'bold'}}>
                                                                  {formatCurrency(item.gain_loss)} ({formatPercent(item.gain_loss_percent)})
                                                              </td>
                                                              <td>
                                                                <div className="actions-wrapper">
                                                                    <button className="sell-btn" onClick={() => setSellingStock(item)}>Sell</button>
                                                                    <button className="edit-btn" onClick={() => onAddStock(item)}>✏️</button>
                                                                    <button className="bin-btn" onClick={() => handleDelete(item)}>🗑</button>
                                                                </div>
                                                              </td>
                                                          </tr>
                                                      ))
                                                  )}
                                              </tbody>
                                          </table>
                                      )}

                                      {/* HISTORY TABLE */}
                                      {groupTabs[group.ticker] === 'history' && (
                                          <table className="details-table">
                                              <thead>
                                                  <tr>
                                                      <th>Buy Date</th>
                                                      <th>Sell Date</th>
                                                      <th>Qty</th>
                                                      <th>Buy Price</th>
                                                      <th>Sell Price</th>
                                                      <th>Realized Gain</th>
                                                      <th>Actions</th>
                                                  </tr>
                                              </thead>
                                              <tbody>
                                                  {group.history_items.length === 0 ? (
                                                      <tr><td colSpan="7" style={{textAlign:'center', padding:'20px'}}>No transaction history</td></tr>
                                                  ) : (
                                                      group.history_items.map(item => (
                                                          <tr key={item.id}>
                                                              <td>{new Date(item.buy_date).toLocaleDateString()}</td>
                                                              <td>{item.sell_date ? new Date(item.sell_date).toLocaleDateString() : '-'}</td>
                                                              <td>{item.quantity}</td>
                                                              <td>{formatCurrency(item.buy_price)}</td>
                                                              <td>{formatCurrency(item.sell_price)}</td>
                                                              <td className={item.realized_gain >= 0 ? 'positive' : 'negative'} style={{fontWeight:'bold'}}>
                                                                  {formatCurrency(item.realized_gain)}
                                                              </td>
                                                              <td>
                                                                <div className="actions-wrapper">
                                                                    <button className="bin-btn" onClick={() => handleDelete(item)}>🗑</button>
                                                                </div>
                                                              </td>
                                                          </tr>
                                                      ))
                                                  )}
                                              </tbody>
                                          </table>
                                      )}
                                  </div>
                              </td>
                          </tr>
                      )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      <Watchlist onShowToast={onShowToast} />

      {deleteConfirm && (
        <ConfirmModal 
          title="REMOVE RECORD"
          message={`Are you sure you want to delete this record for ${deleteConfirm.ticker}? This cannot be undone.`}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteConfirm(null)}
        />
      )}

      {sellingStock && (
          <SellStockModal 
            stock={sellingStock}
            onClose={() => setSellingStock(null)}
            onSold={(msg) => {
                if(onShowToast) onShowToast({message: msg, type: 'success'});
                fetchPortfolio(); // Refresh data
            }}
            onError={(msg) => {
                if(onShowToast) onShowToast({message: msg, type: 'error'});
            }}
          />
      )}
    </div>
  );
};

export default Portfolio;
