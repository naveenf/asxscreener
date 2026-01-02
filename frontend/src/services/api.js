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
