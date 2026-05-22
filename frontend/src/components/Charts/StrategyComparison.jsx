import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const StrategyComparison = ({ data, title }) => {
  if (!data || Object.keys(data).length === 0) return null;

  const chartData = Object.entries(data).map(([name, metrics]) => ({
    name,
    pnl: metrics.pnl,
    win_rate: metrics.win_rate,
    trades: metrics.trades
  }));

  return (
    <div className="chart-container">
      {title && <h3>{title}</h3>}
      <div style={{ width: '100%', height: 300 }}>
        <ResponsiveContainer>
          <BarChart data={chartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid-strong)" />
            <XAxis type="number" tick={{fill: 'var(--chart-tick)', fontSize: 12, fontFamily: 'var(--font-mono)'}} />
            <YAxis
              dataKey="name"
              type="category"
              tick={{fill: 'var(--chart-tick)', fontSize: 11, fontFamily: 'var(--font-ui)'}}
              width={100}
            />
            <Tooltip
              contentStyle={{backgroundColor: 'var(--chart-tooltip-bg)', border: '1px solid var(--line-3)', fontFamily: 'var(--font-ui)'}}
              labelStyle={{color: 'var(--chart-value)', fontFamily: 'var(--font-ui)'}}
              itemStyle={{color: 'var(--chart-value)', fontFamily: 'var(--font-mono)'}}
            />
            <Legend formatter={(value) => <span style={{color: 'var(--chart-tick)', fontFamily: 'var(--font-ui)'}}>{value}</span>} />
            <Bar dataKey="pnl" name="Net P&L ($)" fill="var(--rust-400)" />
            <Bar dataKey="win_rate" name="Win Rate (%)" fill="var(--pos-400)" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default StrategyComparison;
