import React, { useState, useEffect, useCallback } from 'react';
import { fetchTradeAnalytics } from '../services/api';
import WinLossDistribution from './Charts/WinLossDistribution';
import StrategyComparison from './Charts/StrategyComparison';
import BacktestComparison from './Charts/BacktestComparison';
import PeriodBreakdown from './Charts/PeriodBreakdown';
import '../styles/Analytics.css';

const PERIODS = [
  { key: 'daily',   label: 'Daily' },
  { key: 'weekly',  label: 'Weekly' },
  { key: 'monthly', label: 'Monthly' },
  { key: 'yearly',  label: 'Yearly' },
];

const CT_COLORS  = { TP: '#4ADE80', SL: '#EF4444', MANUAL: '#F59E0B', UNKNOWN: '#6B7280' };
const CT_ORDER   = ['TP', 'SL', 'MANUAL', 'UNKNOWN'];

const SYNC_START_DATE = '2026-03-10';
const getTodayDate    = () => new Date().toISOString().split('T')[0];

/* ── Inline KPI card ── */
const KpiCard = ({ label, value, subtext, variant }) => (
  <div className={`kpi-card${variant ? ` kpi-${variant}` : ''}`}>
    <span className="kpi-label">{label}</span>
    <span className="kpi-value">{value}</span>
    {subtext && <span className="kpi-sub">{subtext}</span>}
  </div>
);

/* ── Section header ── */
const SectionHead = ({ children, aside }) => (
  <div className="section-head">
    <span className="section-title">{children}</span>
    {aside && <span className="section-aside">{aside}</span>}
  </div>
);

/* ── Main Dashboard ── */
const AnalyticsDashboard = () => {
  const [analytics, setAnalytics]       = useState(null);
  const [loading, setLoading]           = useState(true);
  const [error, setError]               = useState(null);
  const [startDate, setStartDate]       = useState(SYNC_START_DATE);
  const [endDate, setEndDate]           = useState(getTodayDate());
  const [activePeriod, setActivePeriod] = useState('daily');

  const loadAnalytics = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (startDate) params.start_date = startDate;
      if (endDate)   params.end_date   = endDate;
      const data = await fetchTradeAnalytics(params);
      setAnalytics(data);
      setError(null);
    } catch (err) {
      setError('Failed to load analytics');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate]);

  // Fetch on mount only; period switching is client-side
  useEffect(() => { loadAnalytics(); }, []); // eslint-disable-line

  const { summary, by_strategy, period_breakdowns, backtest_comparison } = analytics || {};

  const activePeriodData = period_breakdowns?.[activePeriod] ?? {};
  const bucketCount      = Object.keys(activePeriodData).length;

  const winLossData = summary
    ? [
        { name: 'Wins',   value: Math.round(summary.total_trades * (summary.win_rate  / 100)) },
        { name: 'Losses', value: Math.round(summary.total_trades * (summary.loss_rate / 100)) },
      ]
    : [];

  const closeTypes = summary?.close_types ?? {};
  const hasCloseTypes = CT_ORDER.slice(0, 3).some(k => (closeTypes[k] ?? 0) > 0); // any TP/SL/Manual > 0

  return (
    <div className="analytics-dashboard">

      {/* ── Controls bar ── */}
      <div className="analytics-bar">
        <div className="date-range">
          <div className="date-field">
            <label className="date-label">FROM</label>
            <input
              type="date"
              className="date-input"
              value={startDate}
              onChange={e => setStartDate(e.target.value)}
            />
          </div>
          <span className="date-sep">→</span>
          <div className="date-field">
            <label className="date-label">TO</label>
            <input
              type="date"
              className="date-input"
              value={endDate}
              onChange={e => setEndDate(e.target.value)}
            />
          </div>
          <button className="apply-btn" onClick={loadAnalytics}>Apply</button>
        </div>

        <div className="period-switcher">
          <span className="period-label-hint">P&amp;L view</span>
          {PERIODS.map(p => (
            <button
              key={p.key}
              className={`period-pill${activePeriod === p.key ? ' active' : ''}`}
              onClick={() => setActivePeriod(p.key)}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── States ── */}
      {loading && <div className="dash-state">Loading analytics…</div>}
      {error   && <div className="dash-state dash-error">{error}</div>}
      {!loading && !error && analytics && summary.total_trades === 0 && (
        <div className="dash-state">No trade data in selected range.</div>
      )}

      {!loading && !error && analytics && summary.total_trades > 0 && (
        <>
          {/* ── KPI grid ── */}
          <div className="kpi-grid">
            <KpiCard
              label="Net P&L"
              value={`$${summary.net_pnl_aud.toFixed(2)}`}
              subtext={summary.starting_balance_aud ? `${summary.net_pnl_percent.toFixed(1)}% ROI` : null}
              variant={summary.net_pnl_aud >= 0 ? 'pos' : 'neg'}
            />
            <KpiCard
              label="Win Rate"
              value={`${summary.win_rate.toFixed(1)}%`}
              subtext={`${summary.total_trades} trades`}
            />
            <KpiCard
              label="Profit Factor"
              value={summary.profit_factor.toFixed(2)}
              subtext="Gross Win / Loss"
            />
            <KpiCard
              label="Avg R:R"
              value={summary.avg_rr != null && summary.avg_rr !== 0 ? summary.avg_rr.toFixed(2) : '—'}
              subtext="Per trade"
            />
            <KpiCard
              label="Best Trade"
              value={`$${summary.best_trade.toFixed(2)}`}
              variant="pos"
            />
            <KpiCard
              label="Worst Trade"
              value={`$${summary.worst_trade.toFixed(2)}`}
              variant="neg"
            />
            <KpiCard
              label="Max Drawdown"
              value={`${summary.max_drawdown_pct.toFixed(1)}%`}
              variant="neg"
              subtext="Peak-to-trough"
            />
            {summary.current_balance_aud > 0 && (
              <KpiCard
                label="Balance"
                value={`$${summary.current_balance_aud.toFixed(0)}`}
                subtext="Oanda AUD"
              />
            )}
          </div>

          {/* ── Exit classification strip ── */}
          {Object.keys(closeTypes).length > 0 && (
            <div className="exit-strip">
              <span className="exit-strip-head">Exit types</span>
              {CT_ORDER.map(ct =>
                closeTypes[ct] != null ? (
                  <span key={ct} className="exit-chip">
                    <span className="exit-dot" style={{ background: CT_COLORS[ct] }} />
                    <span className="exit-name">{ct}</span>
                    <span className="exit-count">{closeTypes[ct]}</span>
                  </span>
                ) : null
              )}
              {!hasCloseTypes && (
                <span className="exit-note">All UNKNOWN — run backfill to classify</span>
              )}
            </div>
          )}

          {/* ── Period breakdown (primary chart) ── */}
          <div className="dash-section">
            <SectionHead aside={bucketCount > 0 ? `${bucketCount} ${activePeriod === 'daily' ? 'days' : activePeriod === 'weekly' ? 'weeks' : activePeriod === 'monthly' ? 'months' : 'years'}` : ''}>
              P&amp;L Breakdown
            </SectionHead>
            <PeriodBreakdown
              data={activePeriodData}
              period={activePeriod}
              title=""
            />
          </div>

          {/* ── Two-column: Win/Loss + Strategy ── */}
          <div className="dash-two-col">
            <div className="dash-section">
              <SectionHead>Win / Loss</SectionHead>
              <WinLossDistribution data={winLossData} title="" />
            </div>
            <div className="dash-section">
              <SectionHead>Strategy Performance</SectionHead>
              <StrategyComparison data={by_strategy} title="" />
            </div>
          </div>

          {/* ── Backtest comparison (full width, most important) ── */}
          <div className="dash-section">
            <SectionHead aside="live vs backtest win rate per pair">
              Pair Performance
            </SectionHead>
            <BacktestComparison data={backtest_comparison} title="" />
          </div>
        </>
      )}
    </div>
  );
};

export default AnalyticsDashboard;
