import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import Watchlist from './Watchlist';
import ConfirmModal from './ConfirmModal';
import './Portfolio.css';

const Portfolio = ({ onAddStock, onShowToast }) => {
  const { user } = useAuth();
  const [portfolio, setPortfolio] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [deleteConfirm, setDeleteConfirm] = useState(null); // stores {id, ticker}

  const fetchPortfolio = async () => {
    try {
      const token = localStorage.getItem('google_token');
      // No need to manually refresh periodically for now, but in a real app 
      // we might want polling or a refresh button.
      const response = await axios.get('/api/portfolio', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setPortfolio(response.data);
    } catch (err) {
      setError('Failed to fetch portfolio');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchPortfolio();
  }, []);

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
        onShowToast({ message: 'Stock removed from portfolio', type: 'success' });
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

  const calculateTotalValue = () => {
    return portfolio.reduce((acc, item) => acc + (item.current_value || 0), 0);
  };
  
  const calculateTotalGain = () => {
    return portfolio.reduce((acc, item) => acc + (item.gain_loss || 0), 0);
  };

  const calculateTotalGainPercent = () => {
    const totalCost = portfolio.reduce((acc, item) => acc + (item.buy_price * item.quantity), 0);
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
      ) : portfolio.length === 0 ? (
        <p className="empty-msg">No stocks in your portfolio yet. Add them from the screener or manually!</p>
      ) : (
        <div className="portfolio-table-container">
            <table className="portfolio-table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Strategy</th>
                  <th>Date</th>
                  <th>Buy Price</th>
                  <th>Current Price</th>
                  <th>Trend</th>
                  <th>Qty</th>
                  <th>Market Value</th>
                  <th>Gain/Loss</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.map(item => (
                  <tr key={item.id}>
                    <td className="ticker">{item.ticker}</td>
                    <td className="strategy-cell">
                      <span className={`strategy-badge ${item.strategy_type}`}>
                        {item.strategy_type === 'triple_trend' ? 'Trend' : 'Mean Rev'}
                      </span>
                    </td>
                    <td>{new Date(item.buy_date).toLocaleDateString()}</td>
                    <td>${item.buy_price.toFixed(2)}</td>
                    <td>
                      {item.current_price 
                        ? `$${item.current_price.toFixed(2)}` 
                        : <span className="loading-dots">...</span>
                      }
                    </td>
                    <td className="trend-cell">
                      <div className={`trend-signal ${item.trend_signal}`}>
                        {item.trend_signal}
                      </div>
                      {item.exit_reason && (
                        <div className="trend-reason">{item.exit_reason}</div>
                      )}
                    </td>
                    <td>{item.quantity}</td>
                    <td className="value">
                      {item.current_value 
                        ? formatCurrency(item.current_value)
                        : '-'
                      }
                    </td>
                    <td className={`gain-loss ${item.gain_loss >= 0 ? 'positive' : 'negative'}`}>
                      {item.gain_loss !== undefined && item.gain_loss !== null ? (
                        <>
                          <div>{formatCurrency(item.gain_loss)}</div>
                          <div className="percent">{item.gain_loss >= 0 ? '+' : ''}{formatPercent(item.gain_loss_percent)}</div>
                        </>
                      ) : '-'}
                    </td>
                    <td className="actions-cell">
                      <div className="actions-wrapper">
                        <button className="edit-btn" onClick={() => onAddStock(item)}>✏️</button>
                        <button className="bin-btn" onClick={() => handleDelete(item)}>🗑</button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      <Watchlist onShowToast={onShowToast} />

      {deleteConfirm && (
        <ConfirmModal 
          title="REMOVE STOCK"
          message={`Are you sure you want to remove ${deleteConfirm.ticker} from your portfolio?`}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteConfirm(null)}
        />
      )}
    </div>
  );
};

export default Portfolio;
