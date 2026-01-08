import React, { useState } from 'react';
import axios from 'axios';
import './StockSearchModal.css';

const StockSearchModal = ({ onClose, onAddStock }) => {
    const [ticker, setTicker] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);
    const [analysis, setAnalysis] = useState(null);

    const handleSearch = async (e) => {
        e.preventDefault();
        if (!ticker) return;
        
        // Ensure ticker has .AX suffix if it's purely letters and likely ASX
        let searchTicker = ticker.toUpperCase();
        if (/^[A-Z]{3,4}$/.test(searchTicker)) {
             // Optional: Assume .AX if not provided? 
             // Better to let user type it or just try both?
             // For now let's assume if user types 'CBA' they mean 'CBA.AX'
             searchTicker += '.AX'; 
        }

        setLoading(true);
        setError(null);
        setAnalysis(null);

        try {
            const token = localStorage.getItem('google_token');
            const response = await axios.get(`/api/analyze/${searchTicker}`, {
                 headers: token ? { Authorization: `Bearer ${token}` } : {}
            });
            setAnalysis(response.data);
        } catch (err) {
            setError(err.response?.data?.detail || "Failed to analyze stock. Check ticker symbol.");
        } finally {
            setLoading(false);
        }
    };

    const handleAddToPortfolio = (strategy) => {
        const item = {
            ticker: analysis.ticker,
            buy_price: analysis.current_price,
            strategy_type: strategy === 'trend' ? 'triple_trend' : 'mean_reversion',
            notes: `Added from Quick Analysis (${strategy === 'trend' ? 'Trend Following' : 'Mean Reversion'})`
        };
        onAddStock(item);
        onClose();
    };

    const hasConflict = analysis && 
        analysis.strategies.trend.signal === 'BUY' && 
        analysis.strategies.mean_reversion.signal === 'HOLD' &&
        analysis.strategies.mean_reversion.indicators.RSI > 70;

    return (
        <div className="modal-overlay" onClick={onClose}>
            <div className="modal-content search-modal" onClick={e => e.stopPropagation()}>
                <div className="modal-header">
                    <h2>Quick Stock Analysis</h2>
                    <button className="close-btn" onClick={onClose}>×</button>
                </div>
                
                <form onSubmit={handleSearch} className="search-form">
                    <div className="input-wrapper">
                        <input 
                            type="text" 
                            value={ticker}
                            onChange={(e) => setTicker(e.target.value)}
                            placeholder="Enter Ticker (e.g. CBA.AX, TSLA)"
                            autoFocus
                        />
                        <small className="input-hint">Tip: Use .AX for Australian stocks if not in ASX 300</small>
                    </div>
                    <button type="submit" disabled={loading}>
                        {loading ? 'Analyzing...' : 'Analyze'}
                    </button>
                </form>

                {error && <p className="error-msg">{error}</p>}

                {analysis && (
                    <div className="analysis-results">
                        <div className="stock-info">
                            <div className="name-box">
                                <h3>{analysis.name}</h3>
                                <span className="ticker-badge">{analysis.ticker}</span>
                            </div>
                            <div className="price-box">
                                <div className="price">${analysis.current_price}</div>
                                <div className="last-updated">Last Updated: {new Date(analysis.last_updated).toLocaleTimeString()}</div>
                            </div>
                        </div>

                        {hasConflict && (
                            <div className="conflict-warning">
                                ⚠️ <strong>Strategy Divergence:</strong> Trend is Bullish, but Mean Reversion shows Overbought (RSI {analysis.strategies.mean_reversion.indicators.RSI}). Select your primary strategy below.
                            </div>
                        )}

                        <div className="strategies-grid">
                            {/* Trend Strategy Card */}
                            <div className={`strategy-card ${analysis.strategies.trend.signal === 'BUY' ? 'buy' : (analysis.strategies.trend.signal === 'SELL' ? 'sell' : 'neutral')}`}>
                                <h4>Trend Following</h4>
                                <p className="strat-desc">Catch strong momentum moves with triple confirmation.</p>
                                <div className="score-circle">
                                    <span>{analysis.strategies.trend.score}</span>
                                    <small>SCORE</small>
                                </div>
                                <div className="signal-badge">{analysis.strategies.trend.signal}</div>
                                <div className="indicators-list">
                                    <div className="ind-item">
                                        <span>Fibonacci:</span>
                                        <span className={analysis.strategies.trend.indicators.Fib_Pos > 0 ? 'pos' : 'neg'}>
                                            {analysis.strategies.trend.indicators.Fib_Pos > 0 ? 'Bullish' : 'Bearish'}
                                        </span>
                                    </div>
                                    <div className="ind-item">
                                        <span>Supertrend:</span>
                                        <span className={analysis.strategies.trend.indicators.Supertrend === 1 ? 'pos' : 'neg'}>
                                            {analysis.strategies.trend.indicators.Supertrend === 1 ? 'Bullish' : 'Bearish'}
                                        </span>
                                    </div>
                                    <div className="ind-item">
                                        <span>Momentum:</span>
                                        <span>{analysis.strategies.trend.indicators.Instant_Trend}</span>
                                    </div>
                                </div>
                                <button 
                                    className="select-strategy-btn"
                                    onClick={() => handleAddToPortfolio('trend')}
                                >
                                    Trade Trend
                                </button>
                            </div>

                            {/* Mean Reversion Strategy Card */}
                            <div className={`strategy-card ${analysis.strategies.mean_reversion.signal === 'BUY' ? 'buy' : (analysis.strategies.mean_reversion.signal === 'SELL' ? 'sell' : 'neutral')}`}>
                                <h4>Mean Reversion</h4>
                                <p className="strat-desc">Buy extreme oversold dips for a return to the average.</p>
                                <div className="score-circle">
                                    <span>{analysis.strategies.mean_reversion.score}</span>
                                    <small>SCORE</small>
                                </div>
                                <div className="signal-badge">{analysis.strategies.mean_reversion.signal}</div>
                                <div className="indicators-list">
                                    <div className="ind-item">
                                        <span>RSI:</span>
                                        <span className={analysis.strategies.mean_reversion.indicators.RSI < 35 ? 'pos' : (analysis.strategies.mean_reversion.indicators.RSI > 70 ? 'neg' : '')}>
                                            {analysis.strategies.mean_reversion.indicators.RSI}
                                        </span>
                                    </div>
                                    <div className="ind-item">
                                        <span>BB Position:</span>
                                        <span className={analysis.strategies.mean_reversion.indicators.BB_Position === 'OVERSOLD' ? 'pos' : ''}>
                                            {analysis.strategies.mean_reversion.indicators.BB_Position}
                                        </span>
                                    </div>
                                    <div className="ind-item">
                                        <span>Lower Band:</span>
                                        <span>${analysis.strategies.mean_reversion.indicators.BB_Lower}</span>
                                    </div>
                                </div>
                                <button 
                                    className="select-strategy-btn"
                                    onClick={() => handleAddToPortfolio('mean_reversion')}
                                >
                                    Trade MR
                                </button>
                            </div>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default StockSearchModal;
