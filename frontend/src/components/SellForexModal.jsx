import React, { useState } from 'react';
import axios from 'axios';
import './AddStockModal.css';

const SellForexModal = ({ forex, onClose, onSold, onError }) => {
  const [sellDate, setSellDate] = useState(new Date().toISOString().split('T')[0]);
  const [sellPrice, setSellPrice] = useState(forex.current_price || forex.buy_price || '');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const token = localStorage.getItem('google_token');
      const payload = {
        quantity: forex.quantity,
        sell_price: parseFloat(sellPrice),
        sell_date: sellDate
      };

      const config = {
        headers: { Authorization: `Bearer ${token}` }
      };

      await axios.post(`/api/forex-portfolio/${forex.id}/sell`, payload, config);
      onSold(`${forex.symbol} position closed!`);
      onClose();
    } catch (err) {
      const msg = err.response?.data?.detail || "Failed to close position";
      if (onError) onError(msg);
      console.error(err);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="portfolio-overlay">
      <div className="portfolio-modal add-modal">
        <div className="portfolio-header">
          <h2>CLOSE {forex.symbol}</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit} className="add-form">
          <div className="form-info-box">
             <p>Direction: <strong className={forex.direction === 'BUY' ? 'positive' : 'negative'}>{forex.direction}</strong></p>
             <p>Quantity/Units: <strong>{forex.quantity}</strong></p>
             <p>Entry Price: <strong>{forex.buy_price.toFixed(5)}</strong></p>
          </div>

          <div className="form-row">
            <div className="form-group half">
              <label>Exit Date</label>
              <input type="date" value={sellDate} onChange={(e) => setSellDate(e.target.value)} required />
            </div>
            
            <div className="form-group half">
              <label>Exit Price</label>
              <input type="number" step="0.00001" value={sellPrice} onChange={(e) => setSellPrice(e.target.value)} required />
            </div>
          </div>

          <button type="submit" className="submit-btn" disabled={submitting}>
            {submitting ? 'Closing...' : 'Confirm Close Position'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default SellForexModal;
