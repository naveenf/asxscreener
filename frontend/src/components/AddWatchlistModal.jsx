import React, { useState, useEffect, useRef } from 'react';
import axios from 'axios';
import './AddStockModal.css';

const AddWatchlistModal = ({ onClose, onAdded, onError }) => {
  const [ticker, setTicker] = useState('');
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [suggestions, setSuggestions] = useState([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const wrapperRef = useRef(null);

  useEffect(() => {
    const timer = setTimeout(async () => {
      if (ticker && ticker.length >= 1) {
        try {
          const response = await axios.get(`/api/stocks/search?q=${ticker}`);
          setSuggestions(response.data);
          setShowSuggestions(response.data.length > 0);
        } catch (err) {
          console.error('Failed to fetch suggestions:', err);
        }
      } else {
        setSuggestions([]);
        setShowSuggestions(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [ticker]);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectSuggestion = (suggestion) => {
    setTicker(suggestion.ticker);
    setSuggestions([]);
    setShowSuggestions(false);
  };

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
            <div className="ticker-input-wrapper" ref={wrapperRef}>
              <input
                type="text"
                value={ticker}
                onChange={(e) => setTicker(e.target.value.toUpperCase())}
                placeholder="e.g. BHP"
                required
                autoFocus
                autoComplete="off"
                onFocus={() => suggestions.length > 0 && setShowSuggestions(true)}
              />
              {showSuggestions && (
                <ul className="suggestions-list">
                  {suggestions.map((s) => (
                    <li
                      key={s.ticker}
                      className="suggestion-item"
                      onMouseDown={() => handleSelectSuggestion(s)}
                    >
                      <span className="suggestion-ticker">{s.ticker}</span>
                      <span className="suggestion-name">{s.name}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
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
