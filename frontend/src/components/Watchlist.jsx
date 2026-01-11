import React, { useState, useEffect } from 'react';
import axios from 'axios';
import AddWatchlistModal from './AddWatchlistModal';
import Toast from './Toast';
import ConfirmModal from './ConfirmModal';
import './Watchlist.css';

const Watchlist = ({ onShowToast }) => {
  const [watchlist, setWatchlist] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showAddModal, setShowAddModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [toast, setToast] = useState(null);

  const triggerToast = (msg, type = 'success') => {
    if (onShowToast) {
      onShowToast({ message: msg, type });
    } else {
      setToast({ message: msg, type });
    }
  };

  const fetchWatchlist = async () => {
    try {
      const token = localStorage.getItem('google_token');
      if (!token) return;
      
      const response = await axios.get('/api/watchlist', {
        headers: { Authorization: `Bearer ${token}` }
      });
      setWatchlist(response.data);
    } catch (err) {
      console.error('Failed to fetch watchlist', err);
      setError('Failed to load watchlist');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchWatchlist();
    
    // Listen for global refresh events
    const handleGlobalRefresh = () => {
        console.log("Global refresh detected, updating watchlist...");
        fetchWatchlist();
    };
    window.addEventListener('data-refreshed', handleGlobalRefresh);
    
    return () => {
        window.removeEventListener('data-refreshed', handleGlobalRefresh);
    };
  }, []);

  const handleRemove = (item) => {
    setDeleteConfirm(item);
  };

  const confirmDelete = async () => {
    const id = deleteConfirm.id;
    try {
      const token = localStorage.getItem('google_token');
      await axios.delete(`/api/watchlist/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setWatchlist(watchlist.filter(item => item.id !== id));
      triggerToast('Item removed from watchlist');
    } catch (err) {
      triggerToast('Failed to remove item', 'error');
    } finally {
      setDeleteConfirm(null);
    }
  };

  const handleAdded = (message) => {
    triggerToast(message);
    fetchWatchlist();
  };

  const formatCurrency = (val) => {
    if (val === null || val === undefined) return '-';
    return new Intl.NumberFormat('en-AU', { style: 'currency', currency: 'AUD' }).format(val);
  };

  const formatPercent = (val) => {
    if (val === null || val === undefined) return '-';
    return new Intl.NumberFormat('en-AU', { 
      style: 'percent', 
      minimumFractionDigits: 2,
      signDisplay: 'always'
    }).format(val / 100);
  };

  if (loading) return <div className="loading-state">Loading watchlist...</div>;

  return (
    <div className="watchlist-section">
      <div className="watchlist-header">
        <h2>WATCHLIST</h2>
        <button className="add-watchlist-btn" onClick={() => setShowAddModal(true)}>+ Add to Watchlist</button>
      </div>

      {error && <p className="error">{error}</p>}

      {watchlist.length === 0 ? (
        <div className="empty-watchlist">
          Your watchlist is empty.
        </div>
      ) : (
        <div className="watchlist-table-container">
          <table className="watchlist-table">
            <thead>
              <tr>
                <th>Ticker</th>
                <th>Added Date</th>
                <th>Added Price</th>
                <th>Current Price</th>
                <th>Change</th>
                <th>Days</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {watchlist.map(item => (
                <tr key={item.id}>
                  <td className="ticker">{item.ticker}</td>
                  <td>{new Date(item.added_at).toLocaleDateString()}</td>
                  <td>{formatCurrency(item.added_price)}</td>
                  <td>{formatCurrency(item.current_price)}</td>
                  <td className={`change-cell ${item.change_absolute >= 0 ? 'positive' : 'negative'}`}>
                    <div>{item.change_absolute >= 0 ? '+' : ''}{formatCurrency(item.change_absolute)}</div>
                    <div className="percent">{formatPercent(item.change_percent)}</div>
                  </td>
                  <td className="days-cell">{item.days_in_watchlist} days</td>
                  <td>
                    <button className="bin-btn" onClick={() => handleRemove(item)}>🗑</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showAddModal && (
        <AddWatchlistModal 
          onClose={() => setShowAddModal(false)} 
          onAdded={handleAdded} 
          onError={(msg) => triggerToast(msg, 'error')}
        />
      )}

      {deleteConfirm && (
        <ConfirmModal 
          title="REMOVE WATCHLIST"
          message={`Are you sure you want to remove ${deleteConfirm.ticker} from your watchlist?`}
          onConfirm={confirmDelete}
          onCancel={() => setDeleteConfirm(null)}
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
    </div>
  );
};

export default Watchlist;
