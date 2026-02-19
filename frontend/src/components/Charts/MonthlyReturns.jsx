import React from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts';

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
            <Tooltip 
              contentStyle={{backgroundColor: '#1a1a1a', border: '1px solid #333'}}
              formatter={(value) => [`$${value.toFixed(2)}`, 'P&L']}
            />
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
