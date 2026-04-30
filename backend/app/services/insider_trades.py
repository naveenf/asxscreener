"""
Insider Trades Service

Scrapes and processes director transactions from Market Index.
Filters for significant On-market trades (> $50,000).
"""

import json
import re
import html
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Dict, Optional
import logging

from curl_cffi import requests as cf_requests

from ..config import settings

logger = logging.getLogger(__name__)

class InsiderTradesService:
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.url = "https://www.marketindex.com.au/director-transactions"

    def scrape_and_update(self) -> Dict:
        """Fetch latest trades, deduplicate, filter, and save."""
        try:
            response = cf_requests.get(self.url, impersonate="chrome110", timeout=20)
            response.raise_for_status()
            
            # Extract JSON from Vue component attribute
            # Format: <directors-transactions-table :companies="[...]">
            pattern = r':companies="([^"]+)"'
            match = re.search(pattern, response.text)
            
            if not match:
                logger.error("Could not find director transactions data in HTML")
                return {"error": "Data not found"}

            # Decode HTML entities and parse JSON
            encoded_json = match.group(1)
            decoded_json = html.unescape(encoded_json)
            raw_data = json.loads(decoded_json)
            
            # Process and filter
            new_trades = self._process_raw_data(raw_data)
            
            # Merge with existing history
            history = self._load_history()
            updated_history = self._merge_trades(history, new_trades)
            
            # Clean old records (> 30 days)
            final_history = self._clean_old_records(updated_history)
            
            # Save
            self._save_history(final_history)
            
            return {
                "total_processed": len(raw_data),
                "significant_trades": len([t for t in new_trades if self._is_significant(t)]),
                "history_count": len(final_history)
            }

        except Exception as e:
            logger.error(f"Failed to update insider trades: {e}")
            return {"error": str(e)}

    def _process_raw_data(self, raw_data: List) -> List[Dict]:
        """Convert Market Index format to internal format."""
        processed = []
        for item in raw_data:
            try:
                # Extract fields safely
                data_field = item.get('data', {})
                company_field = item.get('company', {})
                
                # Market Index value is often a string with commas like "1,026,635"
                val_str = data_field.get('value', '0').replace(',', '')
                value = float(val_str) if val_str else 0.0
                
                # Normalize Ticker
                ticker = company_field.get('code', '')
                if ticker and not ticker.endswith('.AX'):
                    ticker = f"{ticker}.AX"

                trade_id = item.get('id')
                if not trade_id:
                    logger.warning(f"Skipping trade with no id: {item}")
                    continue

                processed.append({
                    "id": trade_id,
                    "ticker": ticker,
                    "company_name": company_field.get('title', ''),
                    "director": data_field.get('director', 'Unknown'),
                    "type": data_field.get('buy_sell', 'Unknown'),
                    "amount": data_field.get('amount', '0'),
                    "price": float(data_field.get('price', 0) or 0),
                    "value": value,
                    "notes": data_field.get('notes', ''),
                    "date": item.get('transaction_date', ''),
                    "date_formatted": item.get('transaction_date_formatted', '')
                })
            except Exception as e:
                logger.warning(f"Error processing individual trade: {e}")
                continue
        return processed

    def _is_significant(self, trade: Dict) -> bool:
        """Filter: On-market trade AND value > $50,000."""
        is_on_market = "on-market" in trade['notes'].lower()
        is_large = trade['value'] >= 50000
        is_buy_sell = trade['type'].lower() in ['buy', 'sell']
        return is_on_market and is_large and is_buy_sell

    def _load_history(self) -> List[Dict]:
        if self.storage_path.exists():
            try:
                with open(self.storage_path, 'r') as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save_history(self, history: List[Dict]):
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, 'w') as f:
            json.dump(history, f, indent=2)

    def _merge_trades(self, history: List[Dict], new_trades: List[Dict]) -> List[Dict]:
        """Deduplicate using the 'id' field."""
        existing_ids = {t['id'] for t in history}
        merged = list(history)
        for trade in new_trades:
            if trade['id'] not in existing_ids:
                merged.append(trade)
        return merged

    def _clean_old_records(self, history: List[Dict]) -> List[Dict]:
        """Keep only last 30 days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        cleaned = []
        for trade in history:
            try:
                trade_date = datetime.fromisoformat(trade['date'].replace('Z', '+00:00'))
                if trade_date > cutoff:
                    cleaned.append(trade)
            except Exception:
                cleaned.append(trade)
        return cleaned

    def get_grouped_trades(self) -> List[Dict]:
        """Return history grouped by ticker with net stats."""
        history = self._load_history()
        # Evict stale records on every read so startup always shows fresh data
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        recent = []
        for trade in history:
            try:
                trade_date = datetime.fromisoformat(trade['date'].replace('Z', '+00:00'))
                if trade_date > cutoff:
                    recent.append(trade)
            except Exception:
                recent.append(trade)
        significant = [t for t in recent if self._is_significant(t)]
        
        grouped = {}
        for trade in significant:
            ticker = trade['ticker']
            if ticker not in grouped:
                grouped[ticker] = {
                    "ticker": ticker,
                    "company_name": trade['company_name'],
                    "net_value": 0.0,
                    "buy_count": 0,
                    "sell_count": 0,
                    "total_trades": 0,
                    "trades": []
                }
            
            multiplier = 1.0 if trade['type'].lower() == 'buy' else -1.0
            grouped[ticker]["net_value"] += (trade['value'] * multiplier)
            grouped[ticker]["total_trades"] += 1
            if trade['type'].lower() == 'buy':
                grouped[ticker]["buy_count"] += 1
            else:
                grouped[ticker]["sell_count"] += 1
            
            grouped[ticker]["trades"].append(trade)

        # Sort by absolute net value descending
        result = list(grouped.values())
        result.sort(key=lambda x: abs(x['net_value']), reverse=True)
        return result
