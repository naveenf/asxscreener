import React, { useState, useEffect } from 'react';
import { TrendingUp, TrendingDown } from 'lucide-react';
import { fetchLivePrices } from '../services/api';
import './TickerTape.css';

const REFRESH_MS = 30000;

function formatPrice(price, symbol) {
  if (price > 500) return price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (price > 50)  return price.toFixed(3);
  return price.toFixed(5);
}

function TickerItem({ item }) {
  const up = item.change_pct >= 0;
  return (
    <span className="ticker-item">
      <span className="ticker-name">{item.name}</span>
      <span className="ticker-price">{formatPrice(item.price, item.symbol)}</span>
      <span className={`ticker-change ${up ? 'up' : 'down'}`}>
        {up ? <TrendingUp size={10} /> : <TrendingDown size={10} />}
        {Math.abs(item.change_pct).toFixed(2)}%
      </span>
    </span>
  );
}

function TickerTape() {
  const [prices, setPrices] = useState([]);

  useEffect(() => {
    let mounted = true;
    const load = async () => {
      try {
        const data = await fetchLivePrices();
        if (mounted && data.prices?.length) setPrices(data.prices);
      } catch {
        // Fail silently — ticker is non-critical UI
      }
    };
    load();
    const interval = setInterval(load, REFRESH_MS);
    return () => { mounted = false; clearInterval(interval); };
  }, []);

  if (!prices.length) return null;

  const items = [...prices, ...prices]; // duplicate for seamless loop

  return (
    <div className="ticker-tape" aria-hidden="true">
      <div className="ticker-track">
        {items.map((item, i) => (
          <TickerItem key={`${item.symbol}-${i}`} item={item} />
        ))}
      </div>
    </div>
  );
}

export default TickerTape;
