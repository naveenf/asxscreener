import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload && payload.length) {
    const value = payload[0].value;
    const color = value >= 0 ? '#4caf50' : '#f44336';
    return (
      <div style={{ backgroundColor: '#1a1a1a', border: '1px solid #333', padding: '8px 12px', borderRadius: 4 }}>
        <p style={{ color: 'rgba(255,255,255,0.6)', margin: 0, fontSize: 12 }}>{label}</p>
        <p style={{ color, margin: '4px 0 0', fontWeight: 600 }}>${value.toFixed(2)}</p>
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
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis dataKey="month" tick={{fill: 'rgba(255,255,255,0.5)', fontSize: 12}} />
            <YAxis tick={{fill: 'rgba(255,255,255,0.5)', fontSize: 12}} />
            <Tooltip content={<CustomTooltip />} />
            <Bar dataKey="pnl">
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.pnl >= 0 ? '#4caf50' : '#f44336'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default MonthlyReturns;
