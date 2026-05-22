import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    const value = payload[0].value;
    const color = value >= 0 ? 'var(--pos-400)' : 'var(--neg-400)';
    return (
      <div style={{ backgroundColor: 'var(--chart-tooltip-bg)', border: '1px solid var(--line-3)', padding: '8px 12px', borderRadius: 4, fontFamily: 'var(--font-ui)' }}>
        <p style={{ color: 'var(--chart-tick)', margin: 0, fontSize: 12, fontFamily: 'var(--font-ui)' }}>{label}</p>
        <p style={{ color, margin: '4px 0 0', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>${value.toFixed(2)}</p>
      </div>
    );
  }
  return null;
};

const MonthlyReturns = ({ data, title }) => {
  if (!data || data.length === 0) return null;

  return (
    <div className="chart-container">
      <h3>{title}</h3>
      <div style={{ width: '100%', height: 300 }}>
        <ResponsiveContainer>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid-strong)" />
            <XAxis dataKey="month" tick={{fill: 'var(--chart-tick)', fontSize: 12, fontFamily: 'var(--font-mono)'}} />
            <YAxis tick={{fill: 'var(--chart-tick)', fontSize: 12, fontFamily: 'var(--font-mono)'}} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="pnl">
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.pnl >= 0 ? 'var(--pos-400)' : 'var(--neg-400)'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default MonthlyReturns;
