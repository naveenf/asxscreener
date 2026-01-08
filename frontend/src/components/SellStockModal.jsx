import React, { useState } from 'react';
import axios from 'axios';
import './AddStockModal.css'; // Reuse styles

const SellStockModal = ({ stock, onClose, onSold, onError }) => {
  const [sellDate, setSellDate] = useState(new Date().toISOString().split('T')[0]);
  const [sellPrice, setSellPrice] = useState(stock.current_price || stock.buy_price || '');
  const [quantity, setQuantity] = useState(stock.quantity);
  const [brokerage, setBrokerage] = useState(0);
  const [submitting, setSubmitting] = useState(false);

  const maxQuantity = stock.quantity;

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (parseFloat(quantity) > maxQuantity) {
        if(onError) onError("Cannot sell more than you own.");
        return;
    }
    
    setSubmitting(true);
    try {
      const token = localStorage.getItem('google_token');
      const payload = {
        quantity: parseFloat(quantity),
        sell_price: parseFloat(sellPrice),
        sell_date: sellDate,
        brokerage: parseFloat(brokerage)
      };

      const config = {
        headers: { Authorization: `Bearer ${token}` }
      };

      await axios.post(`/api/portfolio/${stock.id}/sell`, payload, config);
      onSold(`${stock.ticker} sold successfully!`);
      onClose();
    } catch (err) {
      const msg = err.response?.data?.detail || "Failed to process sale";
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
          <h2>SELL {stock.ticker}</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit} className="add-form">
          <div className="form-info-box">
             <p>Owned Quantity: <strong>{maxQuantity}</strong></p>
             <p>Avg Buy Price: <strong>${stock.buy_price.toFixed(2)}</strong></p>
          </div>

          <div className="form-row">
            <div className="form-group half">
              <label>Sell Date</label>
              <input type="date" value={sellDate} onChange={(e) => setSellDate(e.target.value)} required />
            </div>
            
            <div className="form-group half">
              <label>Sell Price ($)</label>
              <input type="number" step="0.01" value={sellPrice} onChange={(e) => setSellPrice(e.target.value)} required />
            </div>
          </div>

          <div className="form-row">
            <div className="form-group half">
              <label>Quantity to Sell</label>
              <input 
                type="number" 
                step="1" 
                max={maxQuantity}
                value={quantity} 
                onChange={(e) => setQuantity(e.target.value)} 
                required 
              />
            </div>
            
            <div className="form-group half">
              <label>Brokerage ($)</label>
              <input type="number" step="0.01" value={brokerage} onChange={(e) => setBrokerage(e.target.value)} />
            </div>
          </div>

          <button type="submit" className="submit-btn" disabled={submitting}>
            {submitting ? 'Processing...' : 'Confirm Sale'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default SellStockModal;
