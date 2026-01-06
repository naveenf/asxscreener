import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import './Portfolio.css';

const Portfolio = ({ onClose }) => {
  const { user } = useAuth();
  const [portfolio, setPortfolio] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchPortfolio = async () => {
    try {
      const token = localStorage.getItem('google_token');
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

  const handleDelete = async (id) => {
    try {
      const token = localStorage.getItem('google_token');
      await axios.delete(`/api/portfolio/${id}`, {
        headers: { Authorization: `Bearer ${token}` }
      });
      setPortfolio(portfolio.filter(item => item.id !== id));
    } catch (err) {
      alert('Delete failed');
    }
  };

  return (
    <div className="portfolio-overlay">
      <div className="portfolio-modal">
        <div className="portfolio-header">
          <h2>MY PORTFOLIO</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        {loading ? (
          <p>Loading...</p>
        ) : error ? (
          <p className="error">{error}</p>
        ) : portfolio.length === 0 ? (
          <p className="empty-msg">No stocks in your portfolio yet. Add them from the screener!</p>
        ) : (
          <div className="portfolio-table-container">
            <table className="portfolio-table">
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Date</th>
                  <th>Price</th>
                  <th>Qty</th>
                  <th>Value</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.map(item => (
                  <tr key={item.id}>
                    <td className="ticker">{item.ticker}</td>
                    <td>{new Date(item.buy_date).toLocaleDateString()}</td>
                    <td>${item.buy_price.toFixed(2)}</td>
                    <td>{item.quantity}</td>
                    <td className="value">${(item.buy_price * item.quantity).toFixed(2)}</td>
                    <td>
                      <button className="delete-btn" onClick={() => handleDelete(item.id)}>Remove</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

export default Portfolio;
