import React from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const WinLossDistribution = ({ data, title }) => {
  if (!data || data.length === 0) return null;

  const COLORS = ['var(--pos-400)', 'var(--neg-400)'];

  return (
    <div className="chart-container">
      {title && <h3>{title}</h3>}
      <div style={{ width: '100%', height: 300 }}>
        <ResponsiveContainer>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={80}
              paddingAngle={5}
              dataKey="value"
            >
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{backgroundColor: 'var(--chart-tooltip-bg)', border: '1px solid var(--line-3)', fontFamily: 'var(--font-ui)'}}
              labelStyle={{color: 'var(--chart-value)', fontFamily: 'var(--font-ui)'}}
              itemStyle={{color: 'var(--chart-value)', fontFamily: 'var(--font-mono)'}}
            />
            <Legend formatter={(value) => <span style={{color: 'var(--chart-tick)', fontFamily: 'var(--font-ui)'}}>{value}</span>} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default WinLossDistribution;
