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
                <stop offset="5%" stopColor="var(--pos-400)" stopOpacity={0.8}/>
                <stop offset="95%" stopColor="var(--pos-400)" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid-strong)" />
            <XAxis
              dataKey="date"
              tick={{fill: 'var(--chart-tick)', fontSize: 12, fontFamily: 'var(--font-mono)'}}
              tickFormatter={(str) => str.split('-').slice(1).join('/')}
            />
            <YAxis tick={{fill: 'var(--chart-tick)', fontSize: 12, fontFamily: 'var(--font-mono)'}} />
            <Tooltip
              contentStyle={{backgroundColor: 'var(--chart-tooltip-bg)', border: '1px solid var(--line-3)', fontFamily: 'var(--font-ui)'}}
              labelStyle={{color: 'var(--chart-value)', fontFamily: 'var(--font-ui)'}}
              itemStyle={{color: 'var(--chart-value)', fontFamily: 'var(--font-mono)'}}
            />
            <Area 
              type="monotone" 
              dataKey="cumulative_pnl" 
              stroke="var(--pos-400)" 
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
