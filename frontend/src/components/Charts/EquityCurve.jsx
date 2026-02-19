import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts';

const EquityCurve = ({ data, title }) => {
  if (!data || data.length === 0) return null;

  return (
    <div className="chart-container">
      <h3>{title}</h3>
      <div style={{ width: '100%', height: 300 }}>
        <ResponsiveContainer>
          <AreaChart data={data}>
            <defs>
              <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#82ca9d" stopOpacity={0.8}/>
                <stop offset="95%" stopColor="#82ca9d" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
            <XAxis 
              dataKey="date" 
              tick={{fill: 'rgba(255,255,255,0.5)', fontSize: 12}}
              tickFormatter={(str) => str.split('-').slice(1).join('/')}
            />
            <YAxis tick={{fill: 'rgba(255,255,255,0.5)', fontSize: 12}} />
            <Tooltip 
              contentStyle={{backgroundColor: '#1a1a1a', border: '1px solid #333'}}
              labelStyle={{color: '#999'}}
            />
            <Area 
              type="monotone" 
              dataKey="cumulative_pnl" 
              stroke="#82ca9d" 
              fillOpacity={1} 
              fill="url(#colorPnl)" 
              name="Cumulative P&L"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export default EquityCurve;
