import React, { useState } from 'react';
import axios from 'axios';
import './AddStockModal.css'; // Reuse common modal styles

const AddWatchlistModal = ({ onClose, onAdded, onError }) => {
  const [ticker, setTicker] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const token = localStorage.getItem('google_token');
      await axios.post('/api/watchlist', { 
        ticker: ticker.toUpperCase(),
        notes: notes
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      onAdded(`${ticker.toUpperCase()} added to watchlist!`);
      onClose();
    } catch (err) {
      const msg = err.response?.data?.detail || 'Failed to add stock';
      if (onError) {
        onError(msg);
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="portfolio-overlay">
      <div className="portfolio-modal add-modal">
        <div className="portfolio-header">
          <h2>ADD TO WATCHLIST</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit} className="add-form">
          <div className="form-group">
            <label>Ticker Symbol</label>
            <input 
              type="text" 
              value={ticker} 
              onChange={(e) => setTicker(e.target.value.toUpperCase())} 
              placeholder="e.g. BHP"
              required 
              autoFocus
            />
          </div>

          <div className="form-group">
            <label>Notes (Optional)</label>
            <textarea 
              value={notes} 
              onChange={(e) => setNotes(e.target.value)} 
              placeholder="e.g. Watching for dip" 
            />
          </div>

          <button type="submit" className="submit-btn" disabled={submitting}>
            {submitting ? 'Saving...' : 'Add to Watchlist'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default AddWatchlistModal;
