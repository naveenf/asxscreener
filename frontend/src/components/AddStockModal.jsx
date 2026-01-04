import React, { useState } from 'react';
import axios from 'axios';
import './AddStockModal.css';

const AddStockModal = ({ stock, onClose, onAdded }) => {
  const [buyDate, setBuyDate] = useState(new Date().toISOString().split('T')[0]);
  const [buyPrice, setBuyPrice] = useState(stock.current_price || 0);
  const [quantity, setQuantity] = useState(1);
  const [notes, setNotes] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const token = localStorage.getItem('google_token');
      await axios.post('http://localhost:8000/api/portfolio', {
        ticker: stock.ticker,
        buy_date: buyDate,
        buy_price: parseFloat(buyPrice),
        quantity: parseFloat(quantity),
        notes: notes
      }, {
        headers: { Authorization: `Bearer ${token}` }
      });
      onAdded();
      onClose();
    } catch (err) {
      alert('Failed to add stock');
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="portfolio-overlay">
      <div className="portfolio-modal add-modal">
        <div className="portfolio-header">
          <h2>ADD {stock.ticker} TO PORTFOLIO</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit} className="add-form">
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
            {submitting ? 'Adding...' : 'Add to Portfolio'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default AddStockModal;
