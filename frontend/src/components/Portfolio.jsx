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
  
  // Tax Summary State
  const [activeView, setActiveView] = useState('portfolio'); // 'portfolio' | 'tax'
  const [taxSummary, setTaxSummary] = useState(null);
  const [loadingTax, setLoadingTax] = useState(false);
  const [expandedFY, setExpandedFY] = useState({}); // { fy: boolean }

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
  
  const fetchTaxSummary = async () => {
      setLoadingTax(true);
      try {
          const token = localStorage.getItem('google_token');
          const response = await axios.get('/api/portfolio/tax-summary', {
              headers: { Authorization: `Bearer ${token}` }
          });
          setTaxSummary(response.data);
      } catch (err) {
          console.error("Failed to fetch tax summary", err);
          if (onShowToast) onShowToast({message: "Failed to load tax report", type: 'error'});
      } finally {
          setLoadingTax(false);
      }
  };

  useEffect(() => {
    fetchPortfolio();
    
    // Listen for global refresh events
    const handleGlobalRefresh = () => {
        console.log("Global refresh detected, updating portfolio...");
        fetchPortfolio();
        if (activeView === 'tax') {
            fetchTaxSummary();
        }
    };
    window.addEventListener('data-refreshed', handleGlobalRefresh);
    
    return () => {
        window.removeEventListener('data-refreshed', handleGlobalRefresh);
    };
  }, [activeView]);
  
  useEffect(() => {
      if (activeView === 'tax' && !taxSummary) {
          fetchTaxSummary();
      }
  }, [activeView]);

  // Grouping Logic
  const groupedPortfolio = useMemo(() => {
    const groups = {};
    
    portfolio.forEach(item => {
        // Skip closed items for the main portfolio view
        if (item.status === 'CLOSED') {
            return;
        }

        const ticker = item.ticker;
        if (!groups[ticker]) {
            groups[ticker] = {
                ticker,
                active_items: [],
                total_qty: 0,
                total_cost_basis: 0,
                total_market_value: 0,
                total_gain_loss: 0,
                current_price: item.current_price, // Assumes all items with same ticker have same current price
                trend_signal: null,
                strategy_type: item.strategy_type
            };
        }
        
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
    });
    
    // Sort groups by ticker
    return Object.values(groups).sort((a, b) => a.ticker.localeCompare(b.ticker));
  }, [portfolio]);

  const toggleGroup = (ticker) => {
    setExpandedGroups(prev => ({
        ...prev,
        [ticker]: !prev[ticker]
    }));
  };
  
  const toggleFY = (fy) => {
      setExpandedFY(prev => ({ ...prev, [fy]: !prev[fy] }));
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
      // If we are in tax view, refresh it too because a closed item might have been deleted
      if (activeView === 'tax') {
          fetchTaxSummary();
      }
      
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
          <div className="view-toggle">
              <button 
                className={`view-btn ${activeView === 'portfolio' ? 'active' : ''}`}
                onClick={() => setActiveView('portfolio')}
              >
                  Holdings
              </button>
              <button 
                className={`view-btn ${activeView === 'tax' ? 'active' : ''}`}
                onClick={() => setActiveView('tax')}
              >
                  Tax Reports
              </button>
          </div>
        </div>
        <button className="add-stock-btn" onClick={() => onAddStock({})}>+ Add Stock</button>
      </div>

      {activeView === 'portfolio' && (
          loading ? (
            <div className="loading-state">Loading market data...</div>
          ) : error ? (
            <p className="error">{error}</p>
          ) : (
            <>
                {portfolio.length > 0 && groupedPortfolio.length > 0 && (
                    <div className="summary-cards-container">
                      <div className="summary-card">
                        <h3>Total Market Value</h3>
                        <div className="card-value">
                            {formatCurrency(calculateTotalValue())}
                        </div>
                      </div>
                      <div className="summary-card">
                        <h3>Total Unrealized Gain</h3>
                        <div className={`card-value ${calculateTotalGain() >= 0 ? 'positive' : 'negative'}`}>
                          {formatCurrency(calculateTotalGain())}
                          <span className="card-sub">
                             ({calculateTotalGain() >= 0 ? '+' : ''}{formatPercent(calculateTotalGainPercent())})
                          </span>
                        </div>
                      </div>
                    </div>
                )}
            
                {groupedPortfolio.length === 0 ? (
                    <p className="empty-msg">No active stocks in your portfolio. Check "Tax Reports" for closed positions.</p>
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
                                    <td>{group.total_qty}</td>
                                    <td>
                                        {formatCurrency(group.total_cost_basis / group.total_qty)}
                                    </td>
                                    <td>
                                        {group.current_price 
                                            ? `$${group.current_price.toFixed(2)}` 
                                            : <span className="loading-dots">...</span>
                                        }
                                    </td>
                                    <td className="trend-cell">
                                        <>
                                            <div className={`trend-signal ${group.trend_signal}`}>
                                                {group.trend_signal}
                                            </div>
                                            {group.exit_reason && (
                                                <div className="trend-reason">{group.exit_reason}</div>
                                            )}
                                        </>
                                    </td>
                                    <td className="value">
                                        {formatCurrency(group.total_market_value)}
                                    </td>
                                    <td className={`gain-loss ${group.total_gain_loss >= 0 ? 'positive' : 'negative'}`}>
                                        <>
                                            <div>{formatCurrency(group.total_gain_loss)}</div>
                                            <div className="percent">
                                                {group.total_gain_loss >= 0 ? '+' : ''}
                                                {formatPercent(group.total_gain_loss / group.total_cost_basis * 100)}
                                            </div>
                                        </>
                                    </td>
                                  </tr>

                                  {/* Expanded Details Row - ACTIVE ONLY */}
                                  {expandedGroups[group.ticker] && (
                                      <tr className="details-row">
                                          <td colSpan="8" className="details-cell">
                                              <div className="details-container">
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
                                                          {group.active_items.map(item => (
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
                                                          ))}
                                                      </tbody>
                                                  </table>
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
            </>
          )
      )}
      
      {activeView === 'tax' && (
          loadingTax ? (
              <div className="loading-state">Loading tax reports...</div>
          ) : !taxSummary || taxSummary.summary.length === 0 ? (
              <p className="empty-msg">No closed positions found for tax reporting.</p>
          ) : (
              <div className="tax-report-container">
                  <div className="summary-cards-container">
                      <div className="summary-card">
                          <h3>Lifetime Realized Profit</h3>
                          <div className={`card-value ${taxSummary.lifetime_profit >= 0 ? 'positive' : 'negative'}`}>
                              {formatCurrency(taxSummary.lifetime_profit)}
                          </div>
                          <div className="tax-disclaimer" style={{marginTop:'8px', marginBottom:0}}>* Net of Brokerage</div>
                      </div>
                      <div className="summary-card">
                          <h3>Total Brokerage Paid</h3>
                          <div className="card-value neutral">
                              {formatCurrency(taxSummary.lifetime_brokerage)}
                          </div>
                      </div>
                  </div>
                  
                  <div className="portfolio-table-container">
                      <table className="portfolio-table">
                          <thead>
                              <tr>
                                  <th>Financial Year</th>
                                  <th>Realized Gain (Net)</th>
                                  <th>Total Brokerage</th>
                                  <th>Assessable Gain/(Loss)</th>
                              </tr>
                          </thead>
                          <tbody>
                              {taxSummary.summary.map(fyGroup => (
                                  <React.Fragment key={fyGroup.financial_year}>
                                      <tr 
                                        className={`group-row ${expandedFY[fyGroup.financial_year] ? 'expanded' : ''}`}
                                        onClick={() => toggleFY(fyGroup.financial_year)}
                                      >
                                          <td className="ticker">
                                              <span className="toggle-icon">▶</span>
                                              {fyGroup.financial_year}
                                          </td>
                                          <td className={`gain-loss ${fyGroup.total_profit >= 0 ? 'positive' : 'negative'}`}>
                                              {formatCurrency(fyGroup.total_profit)}
                                          </td>
                                          <td>{formatCurrency(fyGroup.total_brokerage)}</td>
                                          <td style={{fontWeight: 'bold'}}>
                                              {formatCurrency(fyGroup.total_taxable_gain)}
                                          </td>
                                      </tr>
                                      
                                      {expandedFY[fyGroup.financial_year] && (
                                          <tr className="details-row">
                                              <td colSpan="4" className="details-cell">
                                                  <div className="details-container">
                                                      <div className="tax-disclaimer">
                                                          * Realized Gain is net of brokerage fees. Assessable Gain includes 50% CGT discount for assets held > 12 months.
                                                      </div>
                                                      <table className="details-table">
                                                          <thead>
                                                              <tr>
                                                                  <th>Ticker</th>
                                                                  <th>Buy Date</th>
                                                                  <th>Sell Date</th>
                                                                  <th>Days Held</th>
                                                                  <th>Type</th>
                                                                  <th>Realized Gain (Net)</th>
                                                                  <th>Assessable Gain</th>
                                                              </tr>
                                                          </thead>
                                                          <tbody>
                                                              {fyGroup.items.map(item => (
                                                                  <tr key={item.id}>
                                                                      <td style={{color: 'var(--color-primary)', fontWeight:'bold'}}>{item.ticker}</td>
                                                                      <td>{new Date(item.buy_date).toLocaleDateString()}</td>
                                                                      <td>{new Date(item.sell_date).toLocaleDateString()}</td>
                                                                      <td>{item.holding_period_days}</td>
                                                                      <td>
                                                                          <span className={`strategy-badge ${item.is_long_term ? 'triple_trend' : 'mean_reversion'}`}>
                                                                              {item.is_long_term ? 'LONG TERM' : 'SHORT TERM'}
                                                                          </span>
                                                                      </td>
                                                                      <td className={item.realized_gain >= 0 ? 'positive' : 'negative'}>
                                                                          {formatCurrency(item.realized_gain)}
                                                                      </td>
                                                                      <td style={{fontWeight:'bold'}}>
                                                                          {formatCurrency(item.taxable_gain)}
                                                                      </td>
                                                                  </tr>
                                                              ))}
                                                          </tbody>
                                                      </table>
                                                  </div>
                                              </td>
                                          </tr>
                                      )}
                                  </React.Fragment>
                              ))}
                          </tbody>
                      </table>
                  </div>
              </div>
          )
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
