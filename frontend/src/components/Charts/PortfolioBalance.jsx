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
      background: 'var(--chart-tooltip-bg)', border: '1px solid var(--line-3)',
      padding: '8px 12px', borderRadius: 6, minWidth: 160,
      fontFamily: 'var(--font-ui)',
    }}>
      <div style={{ color: 'var(--chart-tick)', fontSize: 11, marginBottom: 4, fontFamily: 'var(--font-ui)' }}>{label}</div>
      <div style={{ color: 'var(--chart-value)', fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
        A${balance.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </div>
      {depositAmount > 0 && (
        <div style={{ color: 'var(--chart-deposit)', fontSize: 11, marginTop: 4, fontFamily: 'var(--font-mono)' }}>
          +A${depositAmount.toLocaleString('en-AU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} deposited
        </div>
      )}
      {depositAmount < 0 && (
        <div style={{ color: 'var(--neg-400)', fontSize: 11, marginTop: 4, fontFamily: 'var(--font-mono)' }}>
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
  const fill   = isDeposit ? 'var(--chart-deposit-fill)' : 'var(--chart-withdraw-fill)';
  const stroke = isDeposit ? 'var(--chart-deposit)' : 'var(--neg-400)';
  const sign   = isDeposit ? '+' : '−';
  const abs    = Math.abs(amt);
  const lbl    = abs >= 1000
    ? `${sign}$${(abs / 1000).toFixed(1)}k`
    : `${sign}$${Math.round(abs)}`;
  return (
    <g>
      <circle cx={cx} cy={cy} r={7} fill={fill} stroke={stroke} strokeWidth={2} opacity={0.9} />
      <text x={cx} y={cy - 12} textAnchor="middle" fill={stroke} fontSize={10} fontWeight={600} fontFamily="var(--font-mono)">
        {lbl}
      </text>
    </g>
  );
};

const PortfolioBalance = ({ periodData, startingBalance, deposits = [], period }) => {
  if (!periodData || Object.keys(periodData).length === 0) {
    return (
      <div className="chart-container">
        <div className="empty-state" style={{ padding: '60px 20px', textAlign: 'center', color: 'var(--chart-tick)' }}>
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
  const lineColor = isUp ? 'var(--pos-400)' : 'var(--neg-400)';
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
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
          <XAxis
            dataKey="label"
            tick={{ fill: 'var(--chart-tick)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
            tickLine={false}
            axisLine={{ stroke: 'var(--chart-grid-strong)' }}
            interval={Math.max(0, Math.ceil(chartData.length / 7) - 1)}
          />
          <YAxis
            domain={yDomain}
            tick={{ fill: 'var(--chart-tick)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
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
        <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: 11, flexWrap: 'wrap', fontFamily: 'var(--font-ui)' }}>
          {hasDeposits && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: 'var(--chart-deposit)' }}>
              <span style={{
                width: 10, height: 10, borderRadius: '50%',
                background: 'var(--chart-deposit-fill)', border: '2px solid var(--chart-deposit)', flexShrink: 0,
              }} />
              Deposit
            </span>
          )}
          {hasWithdrawals && (
            <span style={{ display: 'flex', alignItems: 'center', gap: 5, color: 'var(--neg-400)' }}>
              <span style={{
                width: 10, height: 10, borderRadius: '50%',
                background: 'var(--chart-withdraw-fill)', border: '2px solid var(--neg-400)', flexShrink: 0,
              }} />
              Withdrawal
            </span>
          )}
          <span style={{ color: 'var(--fg-5)' }}>Balance includes capital flows</span>
        </div>
      )}
    </div>
  );
};

export default PortfolioBalance;
