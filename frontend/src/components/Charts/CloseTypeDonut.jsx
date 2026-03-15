import React from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const COLORS = { TP: '#4ADE80', SL: '#EF4444', MANUAL: '#F59E0B', UNKNOWN: '#5C3D2E' };

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
                <Cell key={entry.name} fill={COLORS[entry.name] || '#8884d8'} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{ backgroundColor: '#2D2424', border: '1px solid #5C3D2E' }}
              labelStyle={{ color: '#E0C097' }}
              itemStyle={{ color: '#E0C097' }}
            />
            <Legend formatter={(value) => <span style={{ color: '#A89B9B' }}>{value}</span>} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default CloseTypeDonut;
