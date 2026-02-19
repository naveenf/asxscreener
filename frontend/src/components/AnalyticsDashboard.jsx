import React, { useState, useEffect } from 'react';
import { fetchTradeAnalytics } from '../services/api';
import SummaryCard from './SummaryCard';
import EquityCurve from './Charts/EquityCurve';
import MonthlyReturns from './Charts/MonthlyReturns';
import WinLossDistribution from './Charts/WinLossDistribution';
import StrategyComparison from './Charts/StrategyComparison';
import '../styles/Analytics.css';

const AnalyticsDashboard = () => {
  const [analytics, setAnalytics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const loadAnalytics = async () => {
    setLoading(true);
    try {
      const params = {};
      if (startDate) params.start_date = startDate;
      if (endDate) params.end_date = endDate;
      
      const data = await fetchTradeAnalytics(params);
      setAnalytics(data);
      setError(null);
    } catch (err) {
      setError('Failed to load analytics data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAnalytics();
  }, []);

  if (loading) return <div className="loading-state">Loading analytics...</div>;
  if (error) return <div className="error-state">{error}</div>;
  if (!analytics || analytics.summary.total_trades === 0) {
    return <div className="empty-state">No trade data available for analytics.</div>;
  }

  const { summary, by_strategy, by_month, equity_curve } = analytics;

  return (
    <div className="analytics-dashboard">
      <div className="summary-cards">
        <SummaryCard
          title="Net P&L (AUD)"
          value={`$${summary.net_pnl_aud.toFixed(2)}`}
          subtext={`${summary.net_pnl_percent.toFixed(1)}% ROI`}
          className={summary.net_pnl_aud >= 0 ? 'positive' : 'negative'}
        />
        <SummaryCard
          title="Win Rate"
          value={`${summary.win_rate.toFixed(1)}%`}
          subtext={`${summary.total_trades} total trades`}
        />
        <SummaryCard
          title="Profit Factor"
          value={summary.profit_factor.toFixed(2)}
          subtext="Gross Win / Gross Loss"
        />
        <SummaryCard
          title="Best Trade"
          value={`$${summary.best_trade.toFixed(2)}`}
          className="positive"
        />
      </div>

      <div className="charts-grid">
        <EquityCurve 
          data={equity_curve} 
          title="Equity Curve (Cumulative P&L)" 
        />
        
        <MonthlyReturns 
          data={Object.entries(by_month).map(([month, data]) => ({
            month,
            pnl: data.pnl
          }))} 
          title="Monthly Returns" 
        />

        <WinLossDistribution 
          data={[
            { name: 'Wins', value: summary.total_trades * (summary.win_rate/100) },
            { name: 'Losses', value: summary.total_trades * (summary.loss_rate/100) }
          ]} 
          title="Win/Loss Distribution" 
        />

        <StrategyComparison 
          data={by_strategy} 
          title="Strategy Performance" 
        />
      </div>
    </div>
  );
};

export default AnalyticsDashboard;
