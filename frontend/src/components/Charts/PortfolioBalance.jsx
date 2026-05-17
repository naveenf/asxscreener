import React from 'react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';

// Matches Python's strftime('%G-W%V') — ISO 8601 week, year derived from Thursday
function dateToIsoWeekKey(dateStr) {
  const d = new Date(dateStr + 'T12:00:00');
  const dow = d.getDay() || 7; // Mon=1 … Sun=7
  const thu = new Date(d);
  thu.setDate(d.getDate() + 4 - dow); // Thursday of this ISO week
  const isoYear = thu.getFullYear();
  const jan4 = new Date(isoYear, 0, 4);
  const jan4dow = jan4.getDay() || 7;
  const weekStart = new Date(jan4);
  weekStart.setDate(jan4.getDate() - jan4dow + 1); // Monday of week 1
  const weekNum = Math.floor((thu - weekStart) / (7 * 86400000)) + 1;
  return `${isoYear}-W${String(weekNum).padStart(2, '0')}`;
}

function dateToBucketKey(dateStr, period) {
  if (!dateStr) return null;
  if (period === 'daily')   return dateStr;
  if (period === 'monthly') return dateStr.slice(0, 7);
  if (period === 'yearly')  return dateStr.slice(0, 4);
  if (period === 'weekly')  return dateToIsoWeekKey(dateStr);
  return dateStr.slice(0, 7);
}

const formatBucket = (bucket, period) => {
  if (!bucket) return '';
  try {
    if (period === 'daily') {
      const [, m, d] = bucket.split('-');
      return `${d}/${m}`;
    }
    if (period === 'weekly')  return bucket.replace(/^\d{4}-/, '');
    if (period === 'monthly') {
      const [year, mon] = bucket.split('-');
      return new Date(+year, +mon - 1, 1)
        .toLocaleString('en-AU', { month: 'short', year: '2-digit' });
    }
    return bucket;
  } catch {
    return bucket;
  }
};

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  const { balance, depositAmount } = payload[0].payload;
  if (balance == null) return null;
  return (
    <div style={{
      background: '#2D2424', border: '1px solid #5C3D2E',
      padding: '8px 12px', borderRadius: 6, minWidth: 160,
    }}>
      <div style={{ color: '#A89B9B', fontSize: 11, marginBottom: 4 }}>{label}</div>
      <div style={{ color: '#E0C097', fontWeight: 600 }}>
        A${balance.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
      {depositAmount > 0 && (
        <div style={{ color: '#60A5FA', fontSize: 11, marginTop: 4 }}>
          +A${depositAmount.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} deposited
        </div>
      )}
      {depositAmount < 0 && (
        <div style={{ color: '#F87171', fontSize: 11, marginTop: 4 }}>
          −A${Math.abs(depositAmount).toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} withdrawn
        </div>
      )}
    </div>
  );
};

const CapitalFlowDot = (props) => {
  const { cx, cy, payload } = props;
  const amt = payload?.depositAmount;
  if (!amt) return <g />;
  const isDeposit = amt > 0;
  const fill   = isDeposit ? '#1D4ED8' : '#7F1D1D';
  const stroke = isDeposit ? '#60A5FA' : '#F87171';
  const sign   = isDeposit ? '+' : '−';
  const abs    = Math.abs(amt);
  const lbl    = abs >= 1000
    ? `${sign}$${(abs / 1000).toFixed(1)}k`
    : `${sign}$${Math.round(abs)}`;
  return (
    <g>
      <circle cx={cx} cy={cy} r={7} fill={fill} stroke={stroke} strokeWidth={2} opacity={0.9} />
      <text x={cx} y={cy - 12} textAnchor="middle" fill={stroke} fontSize={10} fontWeight={600}>
        {lbl}
      </text>
    </g>
  );
};

const PortfolioBalance = ({ periodData, startingBalance, deposits = [], period }) => {
  if (!periodData || Object.keys(periodData).length === 0) {
    return (
      <div className="chart-container">
        <div className="empty-state" style={{ padding: '60px 20px', textAlign: 'center', color: '#A89B9B' }}>
          No data — try a wider date range or switch period.
        </div>
      </div>
    );
  }

  // Map all transfers (deposits + withdrawals) to bucket keys
  const transferByBucket = {};
  for (const tf of deposits) {
    if (!tf.date || tf.amount === 0) continue;
    const key = dateToBucketKey(tf.date, period);
    if (key) transferByBucket[key] = (transferByBucket[key] || 0) + tf.amount;
  }

  // Union of trade buckets and transfer buckets, sorted chronologically
  const allBuckets = [...new Set([
    ...Object.keys(periodData),
    ...Object.keys(transferByBucket),
  ])].sort();

  // Single-pass build: __start__ anchor prepended, then all buckets in order
  const chartData = [];
  let running = startingBalance || 0;

  if (running > 0) {
    chartData.push({ bucket: 'start', label: 'Start', balance: running, depositAmount: 0 });
  }

  for (const bucket of allBuckets) {
    const pnl = periodData[bucket]?.pnl || 0;
    const dep = transferByBucket[bucket] || 0;
    running = +(running + pnl + dep).toFixed(2);
    chartData.push({
      bucket,
      label: formatBucket(bucket, period),
      balance: running,
      depositAmount: dep,
    });
  }

  const startBalance = chartData[0]?.balance ?? 0;
  const allBalances  = chartData.map(d => d.balance);
  const minVal = Math.min(...allBalances);
  const maxVal = Math.max(...allBalances);
  const padding = (maxVal - minVal) * 0.12 || 50;
  const yDomain = [Math.floor(minVal - padding), Math.ceil(maxVal + padding)];

  const isUp = (chartData[chartData.length - 1]?.balance ?? startBalance) >= startBalance;
  const lineColor = isUp ? '#4ADE80' : '#EF4444';
  const gradientId = isUp ? 'balanceGradientUp' : 'balanceGradientDown';

  const hasDeposits    = Object.values(transferByBucket).some(v => v > 0);
  const hasWithdrawals = Object.values(transferByBucket).some(v => v < 0);

  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={chartData} margin={{ top: 20, right: 16, bottom: 0, left: 8 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%"  stopColor={lineColor} stopOpacity={0.25} />
              <stop offset="95%" stopColor={lineColor} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.08)" />
          <XAxis
            dataKey="label"
            tick={{ fill: '#A89B9B', fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: 'rgba(255,255,255,0.1)' }}
          />
          <YAxis
            domain={yDomain}
            tick={{ fill: '#A89B9B', fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            tickFormatter={v => `$${(v / 1000).toFixed(1)}k`}
            width={52}
          />
          <Tooltip content={<CustomTooltip />} />
          <ReferenceLine y={startBalance} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 3" />
          <Area
            type="monotone"
            dataKey="balance"
            stroke={lineColor}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            dot={<CapitalFlowDot />}
            activeDot={{ r: 4, fill: lineColor, strokeWidth: 0 }}
            name="Balance"
          />
        </AreaChart>
      </ResponsiveContainer>

      {(hasDeposits || hasWithdrawals) && (
        <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: 11, flexWrap: 'wrap' }}>
          {hasDeposits && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#60A5FA' }}>
              <span style={{
                width: 10, height: 10, borderRadius: '50%',
                background: '#1D4ED8', border: '2px solid #60A5FA', flexShrink: 0,
              }} />
              Deposit
            </span>
          )}
          {hasWithdrawals && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: '#F87171' }}>
              <span style={{
                width: 10, height: 10, borderRadius: '50%',
                background: '#7F1D1D', border: '2px solid #F87171', flexShrink: 0,
              }} />
              Withdrawal
            </span>
          )}
          <span style={{ color: '#6B7280' }}>Balance includes capital flows</span>
        </div>
      )}
    </div>
  );
};

export default PortfolioBalance;
