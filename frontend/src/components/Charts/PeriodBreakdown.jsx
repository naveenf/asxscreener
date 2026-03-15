import React, { useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const PeriodBreakdown = ({ data, period, title }) => {
  const [selectedBucket, setSelectedBucket] = useState(null);

  if (!data || Object.keys(data).length === 0) {
    return (
      <div className="chart-container">
        {title && <h3>{title}</h3>}
        <div className="empty-state" style={{ padding: '60px 20px', textAlign: 'center', color: '#A89B9B' }}>
          No data — try a wider date range or switch period.
        </div>
      </div>
    );
  }

  const chartData = Object.entries(data)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([bucket, info]) => ({
      bucket,
      pnl: info.pnl,
      trades: info.trades,
      win_rate: info.win_rate,
      by_pair: info.by_pair,
    }));

  const handleBarClick = (entry) => {
    if (!entry) return;
    setSelectedBucket(selectedBucket === entry.bucket ? null : entry.bucket);
  };

  const selected = selectedBucket ? data[selectedBucket] : null;

  return (
    <div className="chart-container">
      {title && <h3>{title}</h3>}
      <div style={{ width: '100%', height: 300 }}>
        <ResponsiveContainer>
          <BarChart data={chartData} onClick={(e) => e && e.activePayload && e.activePayload.length > 0 && handleBarClick(e.activePayload[0].payload)}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.15)" />
            <XAxis dataKey="bucket" tick={{ fill: '#A89B9B', fontSize: 11 }} />
            <YAxis tick={{ fill: '#A89B9B', fontSize: 12 }} />
            <Tooltip
              contentStyle={{ backgroundColor: '#2D2424', border: '1px solid #5C3D2E' }}
              labelStyle={{ color: '#E0C097' }}
              itemStyle={{ color: '#E0C097' }}
              formatter={(value) => [`$${value.toFixed(2)}`, 'P&L']}
            />
            <Bar dataKey="pnl" cursor="pointer">
              {chartData.map((entry, index) => (
                <Cell
                  key={`cell-${index}`}
                  fill={entry.bucket === selectedBucket
                    ? (entry.pnl >= 0 ? '#86efac' : '#fca5a5')
                    : (entry.pnl >= 0 ? '#4ADE80' : '#EF4444')}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {selected && (
        <div className="period-detail">
          <h4>{selectedBucket} — Pair Breakdown</h4>
          <table className="period-detail-table">
            <thead>
              <tr>
                <th>Pair :: Strategy</th>
                <th>Trades</th>
                <th>P&amp;L</th>
                <th>Win Rate</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(selected.by_pair || {})
                .sort(([, a], [, b]) => b.pnl - a.pnl)
                .map(([key, info]) => (
                  <tr key={key}>
                    <td>{key}</td>
                    <td>{info.trades}</td>
                    <td className={info.pnl >= 0 ? 'positive' : 'negative'}>
                      ${info.pnl.toFixed(2)}
                    </td>
                    <td>{info.win_rate.toFixed(1)}%</td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default PeriodBreakdown;
