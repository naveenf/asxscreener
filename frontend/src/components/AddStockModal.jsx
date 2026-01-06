import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './AddStockModal.css';

const AddStockModal = ({ stock, onClose, onAdded, onError }) => {
  const isEditing = stock && stock.id; // Check if we are editing an existing item
  const isManual = !stock || (!stock.ticker && !stock.id); // Check if we are adding manually (no stock info passed)

  const [ticker, setTicker] = useState('');
  const [buyDate, setBuyDate] = useState(new Date().toISOString().split('T')[0]);
  const [buyPrice, setBuyPrice] = useState('');
  const [quantity, setQuantity] = useState(1);
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (stock) {
      setTicker(stock.ticker || '');
      // If editing, use the stock's existing data
      if (stock.id) {
        setBuyDate(stock.buy_date ? new Date(stock.buy_date).toISOString().split('T')[0] : new Date().toISOString().split('T')[0]);
        setBuyPrice(stock.buy_price || '');
        setQuantity(stock.quantity || 1);
        setNotes(stock.notes || '');
      } else {
        // Adding from screener (pre-fill price and ticker)
        setBuyPrice(stock.current_price || '');
      }
    }
  }, [stock]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const token = localStorage.getItem('google_token');
      const payload = {
        ticker: ticker.toUpperCase(),
        buy_date: buyDate,
        buy_price: parseFloat(buyPrice),
        quantity: parseFloat(quantity),
        notes: notes
      };

      const config = {
        headers: { Authorization: `Bearer ${token}` }
      };

      if (isEditing) {
        await axios.put(`/api/portfolio/${stock.id}`, payload, config);
        onAdded(`${ticker.toUpperCase()} updated!`);
      } else {
        await axios.post('/api/portfolio', payload, config);
        onAdded(`${ticker.toUpperCase()} added to portfolio!`);
      }
      
      onClose();
    } catch (err) {
      const msg = err.response?.data?.detail || `Failed to ${isEditing ? 'update' : 'add'} stock`;
      if (onError) {
        onError(msg);
      }
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="portfolio-overlay">
      <div className="portfolio-modal add-modal">
        <div className="portfolio-header">
          <h2>{isEditing ? `EDIT ${ticker}` : `ADD ${isManual ? 'STOCK' : ticker}`}</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit} className="add-form">
          {isManual && !isEditing && (
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
          )}

          <div className="form-group">
            <label>Buy Date</label>
            <input type="date" value={buyDate} onChange={(e) => setBuyDate(e.target.value)} required />
          </div>
          
          <div className="form-group">
            <label>Buy Price ($)</label>
            <input type="number" step="0.01" value={buyPrice} onChange={(e) => setBuyPrice(e.target.value)} required />
          </div>

          <div className="form-group">
            <label>Quantity</label>
            <input type="number" step="1" value={quantity} onChange={(e) => setQuantity(e.target.value)} required />
          </div>

          <div className="form-group">
            <label>Notes (Optional)</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Trend following entry" />
          </div>

          <button type="submit" className="submit-btn" disabled={submitting}>
            {submitting ? 'Saving...' : (isEditing ? 'Save Changes' : 'Add to Portfolio')}
          </button>
        </form>
      </div>
    </div>
  );
};

export default AddStockModal;
