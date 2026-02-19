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
      <h3>{title}</h3>
      <div style={{ width: '100%', height: 300 }}>
        <ResponsiveContainer>
          <BarChart data={chartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis type="number" tick={{fill: 'rgba(255,255,255,0.5)', fontSize: 12}} />
            <YAxis 
              dataKey="name" 
              type="category" 
              tick={{fill: 'rgba(255,255,255,0.5)', fontSize: 11}} 
              width={100}
            />
            <Tooltip 
              contentStyle={{backgroundColor: '#1a1a1a', border: '1px solid #333'}}
            />
            <Legend />
            <Bar dataKey="pnl" name="Net P&L ($)" fill="#8884d8" />
            <Bar dataKey="win_rate" name="Win Rate (%)" fill="#82ca9d" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default StrategyComparison;
