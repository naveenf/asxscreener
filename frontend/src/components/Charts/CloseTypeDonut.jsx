import React from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const COLORS = { TP: 'var(--pos-400)', SL: 'var(--neg-400)', MANUAL: 'var(--warn-400)', UNKNOWN: 'var(--line-3)' };

const CloseTypeDonut = ({ closeTypes, title }) => {
  if (!closeTypes || Object.keys(closeTypes).length === 0) return null;

  const data = Object.entries(closeTypes).map(([name, value]) => ({ name, value }));

  return (
    <div className="chart-container">
      <h3>{title}</h3>
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
              {data.map((entry) => (
                <Cell key={entry.name} fill={COLORS[entry.name] || 'var(--rust-400)'} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ backgroundColor: 'var(--chart-tooltip-bg)', border: '1px solid var(--line-3)', fontFamily: 'var(--font-ui)' }}
              labelStyle={{ color: 'var(--chart-value)', fontFamily: 'var(--font-ui)' }}
              itemStyle={{ color: 'var(--chart-value)', fontFamily: 'var(--font-mono)' }}
            />
            <Legend formatter={(value) => <span style={{ color: 'var(--chart-tick)', fontFamily: 'var(--font-ui)' }}>{value}</span>} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default CloseTypeDonut;
