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
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.15)" />
            <XAxis type="number" tick={{fill: '#A89B9B', fontSize: 12}} />
            <YAxis
              dataKey="name"
              type="category"
              tick={{fill: '#A89B9B', fontSize: 11}}
              width={100}
            />
            <Tooltip
              contentStyle={{backgroundColor: '#2D2424', border: '1px solid #5C3D2E'}}
              labelStyle={{color: '#E0C097'}}
              itemStyle={{color: '#E0C097'}}
            />
            <Legend formatter={(value) => <span style={{color: '#A89B9B'}}>{value}</span>} />
            <Bar dataKey="pnl" name="Net P&L ($)" fill="#8884d8" />
            <Bar dataKey="win_rate" name="Win Rate (%)" fill="#82ca9d" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default StrategyComparison;
