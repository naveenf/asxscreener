/**
 * API Service
 *
 * Client for communicating with the ASX Screener backend API.
 */

const API_BASE = '/api';

/**
 * Fetch all signals with optional filtering
 */
export async function fetchSignals(minScore = 0, sortBy = 'score') {
  const response = await fetch(
    `${API_BASE}/signals?min_score=${minScore}&sort_by=${sortBy}`
  );

  if (!response.ok) {
    throw new Error(`Failed to fetch signals: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch background refresh status
 */
export async function fetchRefreshStatus() {
  const response = await fetch(`${API_BASE}/status/refresh`);

  if (!response.ok) {
    throw new Error(`Failed to fetch refresh status: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch instant cached stock price
 */
export async function fetchInstantStockPrice(ticker) {
  const response = await fetch(`${API_BASE}/portfolio/price/${ticker}`);

  if (!response.ok) {
    throw new Error(`Failed to fetch instant price for ${ticker}`);
  }

  return response.json();
}

/**
 * Fetch details for a specific stock
 */
export async function fetchStockDetail(ticker) {
  const response = await fetch(`${API_BASE}/stocks/${ticker}`);

  if (!response.ok) {
    throw new Error(`Failed to fetch stock detail: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch screener status
 */
export async function fetchStatus() {
  const response = await fetch(`${API_BASE}/status`);

  if (!response.ok) {
    throw new Error(`Failed to fetch status: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Trigger data refresh
 */
export async function triggerRefresh() {
  const response = await fetch(`${API_BASE}/refresh`, {
    method: 'POST'
  });

  if (!response.ok) {
    throw new Error(`Failed to trigger refresh: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch all forex signals
 */
export async function fetchForexSignals() {
  const response = await fetch(`${API_BASE}/forex/signals`);

  if (!response.ok) {
    throw new Error(`Failed to fetch forex signals: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Trigger forex data refresh
 */
export async function triggerForexRefresh() {
  const response = await fetch(`${API_BASE}/forex/refresh`, {
    method: 'POST'
  });

  if (!response.ok) {
    throw new Error(`Failed to trigger forex refresh: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch real-time OANDA price
 */
export async function fetchForexPrice(symbol) {
  const response = await fetch(`${API_BASE}/forex/price/${symbol}`);
  
  if (!response.ok) {
    throw new Error(`Failed to fetch price for ${symbol}`);
  }
  
  return response.json();
}

/**
 * Trigger portfolio exit checks
 */
export async function checkPortfolioExits() {
  const token = localStorage.getItem('google_token');
  const response = await fetch(`${API_BASE}/forex-portfolio/check-exits`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok) {
    throw new Error(`Failed to check exits: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch trade history with filters
 */
export async function fetchTradeHistory(params = {}) {
  const token = localStorage.getItem('google_token');
  const query = new URLSearchParams(params).toString();
  const response = await fetch(`${API_BASE}/forex-portfolio/history?${query}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch trade history: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch trade analytics
 */
export async function fetchTradeAnalytics(params = {}) {
  const token = localStorage.getItem('google_token');
  const query = new URLSearchParams(params).toString();
  const response = await fetch(`${API_BASE}/forex-portfolio/analytics?${query}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch trade analytics: ${response.statusText}`);
  }

  return response.json();
}

/**
 * Fetch closed trades directly from Oanda (source of truth)
 */
export async function fetchOandaClosedTrades(params = {}) {
  const token = localStorage.getItem('google_token');
  const query = new URLSearchParams(params).toString();
  const response = await fetch(`${API_BASE}/forex-portfolio/oanda-trades?${query}`, {
    headers: {
      'Authorization': `Bearer ${token}`
    }
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch Oanda trades: ${response.statusText}`);
  }

  return response.json();
}

