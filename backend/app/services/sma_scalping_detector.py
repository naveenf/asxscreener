from typing import Dict, Optional
import pandas as pd
from .strategy_interface import ForexStrategy
from .indicators import TechnicalIndicators


class SmaScalpingDetector(ForexStrategy):
    """
    SMA stack + DMI scalping strategy.

    Entry requires full SMA alignment (20/50/100), DI dominance, and DI
    persistence — DI must have been above the threshold for di_persist
    consecutive candles to prevent single-candle spike entries.

    Timeframe is configured per-pair in best_strategies.json (5m or 15m).
    """

    def __init__(self, di_threshold: float = 35.0, rr: float = 5.0,
                 adx_min: float = 0.0, di_persist: int = 1):
        self.di_threshold = di_threshold
        self.rr = rr
        self.adx_min = adx_min
        self.di_persist = max(1, di_persist)

    def get_name(self) -> str:
        return "SmaScalping"

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str,
                target_rr: float = 5.0, spread: float = 0.0,
                params: Optional[Dict] = None) -> Optional[Dict]:

        df = data.get('base')
        if df is None or len(df) < 101:
            return None

        # Per-asset param overrides from best_strategies.json
        di_threshold = float(params.get('di_threshold', self.di_threshold)) if params else self.di_threshold
        adx_min      = float(params.get('adx_min',      self.adx_min))      if params else self.adx_min
        di_persist   = max(1, int(params.get('di_persist', self.di_persist))) if params else self.di_persist

        if len(df) < di_persist + 1:
            return None

        df = df.copy()
        df = TechnicalIndicators.add_all_indicators(df)
        for period, col in [(20, 'SMA20'), (50, 'SMA50'), (100, 'SMA100')]:
            if col not in df.columns:
                df[col] = df['Close'].rolling(period).mean()

        latest = df.iloc[-1]

        required = ['SMA20', 'SMA50', 'SMA100', 'DIPlus', 'DIMinus', 'ADX', 'Low', 'High']
        if not all(col in latest.index and pd.notna(latest[col]) for col in required):
            return None

        adx_ok = latest['ADX'] >= adx_min

        # DI persistence: last di_persist rows must all exceed the threshold
        recent_di_plus  = df['DIPlus'].iloc[-di_persist:].values
        recent_di_minus = df['DIMinus'].iloc[-di_persist:].values
        di_plus_pers  = bool((recent_di_plus  > di_threshold).all())
        di_minus_pers = bool((recent_di_minus > di_threshold).all())

        is_buy = (
            latest['Close'] > latest['SMA20'] and
            latest['Close'] > latest['SMA50'] and
            latest['Close'] > latest['SMA100'] and
            di_plus_pers and
            latest['DIPlus'] > latest['DIMinus'] and
            adx_ok
        )
        is_sell = (
            latest['Close'] < latest['SMA20'] and
            latest['Close'] < latest['SMA50'] and
            latest['Close'] < latest['SMA100'] and
            di_minus_pers and
            latest['DIMinus'] > latest['DIPlus'] and
            adx_ok
        )

        if not (is_buy or is_sell):
            return None

        signal_type = "BUY" if is_buy else "SELL"
        price = float(latest['Close'])

        # Structural validity: reject if price already past the 2-candle SL level
        prev = df.iloc[-3:-1]
        if signal_type == "BUY"  and price < prev['Low'].min():
            return None
        if signal_type == "SELL" and price > prev['High'].max():
            return None

        # ATR floor: SL is at least 1×ATR to avoid noise-triggered stops
        atr = float(latest['ATR']) if 'ATR' in latest.index and pd.notna(latest['ATR']) else None
        rr  = target_rr if target_rr > 0 else self.rr

        if signal_type == "BUY":
            structural  = price - prev['Low'].min()
            stop_dist   = max(structural, atr) if atr else structural
            stop_loss   = price - stop_dist - spread
            risk        = price - stop_loss
            take_profit = price + risk * rr
        else:
            structural  = prev['High'].max() - price
            stop_dist   = max(structural, atr) if atr else structural
            stop_loss   = price + stop_dist + spread
            risk        = stop_loss - price
            take_profit = price - risk * rr

        if risk <= 0:
            return None

        return {
            "signal":      signal_type,
            "score":       75.0,
            "strategy":    self.get_name(),
            "symbol":      symbol,
            "price":       price,
            "timestamp":   latest.name.isoformat() if hasattr(latest.name, 'isoformat') else str(latest.name),
            "stop_loss":   stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "SMA20":   round(float(latest['SMA20']),   5),
                "SMA50":   round(float(latest['SMA50']),   5),
                "SMA100":  round(float(latest['SMA100']),  5),
                "DIPlus":  round(float(latest['DIPlus']),  2),
                "DIMinus": round(float(latest['DIMinus']), 2),
                "ADX":     round(float(latest['ADX']),     2),
            },
        }

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str,
                   entry_price: float) -> Optional[Dict]:
        """Exit when price closes on the wrong side of SMA20."""
        df = data.get('base')
        if df is None or len(df) < 21:
            return None

        df = df.copy()
        df = TechnicalIndicators.add_all_indicators(df)
        if 'SMA20' not in df.columns:
            df['SMA20'] = df['Close'].rolling(20).mean()

        latest = df.iloc[-1]
        if pd.isna(latest['SMA20']):
            return None

        if direction == "BUY"  and latest['Close'] < latest['SMA20']:
            return {"exit_signal": True,
                    "reason": f"Close ({latest['Close']:.5f}) crossed below SMA20 ({latest['SMA20']:.5f})"}
        if direction == "SELL" and latest['Close'] > latest['SMA20']:
            return {"exit_signal": True,
                    "reason": f"Close ({latest['Close']:.5f}) crossed above SMA20 ({latest['SMA20']:.5f})"}
        return None
