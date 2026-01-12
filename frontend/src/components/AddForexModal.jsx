import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './AddStockModal.css'; // Reuse same layout styles

const AddForexModal = ({ forex, onClose, onAdded, onError }) => {
  const isEditing = forex && forex.id;
  const isManual = !forex || (!forex.symbol && !forex.id);

  const [symbol, setSymbol] = useState('');
  const [direction, setDirection] = useState('BUY');
  const [buyDate, setBuyDate] = useState(new Date().toISOString().split('T')[0]);
  const [buyPrice, setBuyPrice] = useState('');
  const [quantity, setQuantity] = useState(1);
  const [notes, setNotes] = useState('');
  const [strategy, setStrategy] = useState(null);
  const [timeframe, setTimeframe] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (forex) {
      setSymbol(forex.symbol || '');
      setDirection(forex.direction || 'BUY');
      if (forex.id) {
        setBuyDate(forex.buy_date ? new Date(forex.buy_date).toISOString().split('T')[0] : new Date().toISOString().split('T')[0]);
        setBuyPrice(forex.buy_price || '');
        setQuantity(forex.quantity || 1);
        setNotes(forex.notes || '');
        setStrategy(forex.strategy || null);
        setTimeframe(forex.timeframe || null);
      } else {
        // Adding from screener
        setBuyPrice(forex.price || '');
        if (forex.signal === 'SELL') {
            setDirection('SELL');
        } else {
            setDirection('BUY');
        }
        setStrategy(forex.strategy || 'TrendFollowing');
        setTimeframe(forex.timeframe_used || '15m');
      }
    }
  }, [forex]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      const token = localStorage.getItem('google_token');
      const payload = {
        symbol: symbol.toUpperCase(),
        direction: direction,
        buy_date: buyDate,
        buy_price: parseFloat(buyPrice),
        quantity: parseFloat(quantity),
        notes: notes,
        strategy: strategy,
        timeframe: timeframe
      };

      const config = {
        headers: { Authorization: `Bearer ${token}` }
      };

      if (isEditing) {
        await axios.put(`/api/forex-portfolio/${forex.id}`, payload, config);
        onAdded(`${symbol.toUpperCase()} updated!`);
      } else {
        await axios.post('/api/forex-portfolio', payload, config);
        onAdded(`${symbol.toUpperCase()} added to portfolio!`);
      }
      
      onClose();
    } catch (err) {
      const msg = err.response?.data?.detail || `Failed to add forex position`;
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
          <h2>{isEditing ? `EDIT ${symbol}` : `ADD ${isManual ? 'POSITION' : symbol}`}</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit} className="add-form">
          {isManual && !isEditing && (
            <div className="form-group">
              <label>OANDA Symbol</label>
              <input 
                type="text" 
                value={symbol} 
                onChange={(e) => setSymbol(e.target.value.toUpperCase())} 
                placeholder="e.g. XAG_USD"
                required 
                autoFocus
              />
            </div>
          )}

          <div className="form-group">
            <label>Direction</label>
            <div className="direction-toggle" style={{ display: 'flex', gap: '10px' }}>
                <button 
                  type="button" 
                  className={`dir-btn ${direction === 'BUY' ? 'active buy' : ''}`}
                  onClick={() => setDirection('BUY')}
                  style={{ flex: 1, padding: '8px', borderRadius: '4px', cursor: 'pointer', border: direction === 'BUY' ? 'none' : '1px solid #444', background: direction === 'BUY' ? '#4cd964' : 'transparent', color: direction === 'BUY' ? 'black' : 'white', fontWeight: 'bold' }}
                >
                    BUY (Long)
                </button>
                <button 
                  type="button" 
                  className={`dir-btn ${direction === 'SELL' ? 'active sell' : ''}`}
                  onClick={() => setDirection('SELL')}
                  style={{ flex: 1, padding: '8px', borderRadius: '4px', cursor: 'pointer', border: direction === 'SELL' ? 'none' : '1px solid #444', background: direction === 'SELL' ? '#ff3b30' : 'transparent', color: direction === 'SELL' ? 'black' : 'white', fontWeight: 'bold' }}
                >
                    SELL (Short)
                </button>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group half">
              <label>Trade Date</label>
              <input type="date" value={buyDate} onChange={(e) => setBuyDate(e.target.value)} required />
            </div>
            
            <div className="form-group half">
              <label>Trade Price</label>
              <input type="number" step="0.00001" value={buyPrice} onChange={(e) => setBuyPrice(e.target.value)} required />
            </div>
          </div>

          <div className="form-group">
            <label>Quantity / Units</label>
            <input type="number" step="0.01" value={quantity} onChange={(e) => setQuantity(e.target.value)} required />
          </div>

          <div className="form-group">
            <label>Notes (Optional)</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="e.g. Real account trade" />
          </div>

          <button type="submit" className="submit-btn" disabled={submitting}>
            {submitting ? 'Saving...' : 'Add to Portfolio'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default AddForexModal;
