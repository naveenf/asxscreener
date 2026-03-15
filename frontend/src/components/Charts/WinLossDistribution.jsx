import React from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const WinLossDistribution = ({ data, title }) => {
  if (!data || data.length === 0) return null;

  const COLORS = ['#4caf50', '#f44336'];

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
              contentStyle={{backgroundColor: '#2D2424', border: '1px solid #5C3D2E'}}
              labelStyle={{color: '#E0C097'}}
              itemStyle={{color: '#E0C097'}}
            />
            <Legend formatter={(value) => <span style={{color: '#A89B9B'}}>{value}</span>} />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default WinLossDistribution;
