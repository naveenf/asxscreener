import React from 'react';
import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer } from 'recharts';

const BUCKETS = [
  { label: '< -1R',    min: -Infinity, max: -1,       color: 'var(--neg-400)' },
  { label: '-1R → 0',  min: -1,        max: 0,        color: 'rgba(248,113,113,0.5)' },
  { label: '0 → +1R',  min: 0,         max: 1,        color: 'rgba(74,222,128,0.5)' },
  { label: '+1R → +2R',min: 1,         max: 2,        color: 'var(--pos-400)' },
  { label: '+2R → +4R',min: 2,         max: 4,        color: 'rgba(74,222,128,0.85)' },
  { label: '+4R+',     min: 4,         max: Infinity,  color: '#86efac' },
];

const CustomTooltip = ({ active, payload }) => {
  if (!active || !payload?.length) return null;
  const { label, count } = payload[0].payload;
  return (
    <div style={{ background: 'var(--bg-2)', border: 'var(--border-card)', borderRadius: 4, padding: '6px 10px', fontSize: '0.72rem', color: 'var(--fg-3)' }}>
      <div style={{ color: 'var(--fg-5)', marginBottom: 2 }}>{label}</div>
      <div><strong style={{ color: 'var(--fg-2)' }}>{count}</strong> trade{count !== 1 ? 's' : ''}</div>
    </div>
  );
};

const RMultipleHistogram = ({ rMultiples }) => {
  if (!rMultiples || rMultiples.length < 3) {
    return (
      <div className="bt-hist-empty">Not enough closed trades for distribution</div>
    );
  }

  const bucketData = BUCKETS.map(b => ({
    label: b.label,
    count: rMultiples.filter(r => r >= b.min && r < b.max).length,
    color: b.color,
  }));

  return (
    <div className="bt-histogram">
      <div className="bt-hist-title">R-Multiple Distribution</div>
      <ResponsiveContainer width="100%" height={148}>
        <BarChart data={bucketData} margin={{ top: 4, right: 4, left: -28, bottom: 0 }} barCategoryGap="20%">
          <XAxis
            dataKey="label"
            tick={{ fontSize: 9, fill: 'var(--fg-5)', fontFamily: 'var(--font-mono)' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 9, fill: 'var(--fg-5)' }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.04)' }} />
          <Bar dataKey="count" radius={[3, 3, 0, 0]}>
            {bucketData.map((entry, i) => (
              <Cell key={i} fill={entry.color} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
};

export default RMultipleHistogram;
