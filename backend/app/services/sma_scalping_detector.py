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
                 adx_min: float = 0.0, di_persist: int = 1,
                 adx_rising: bool = False, sma_ordered: bool = False,
                 di_spread_min: float = 0.0, rsi_filter: bool = False,
                 body_ratio_min: float = 0.0,
                 vol_ratio_min: float = 0.0, atr_ratio_min: float = 0.0,
                 di_slope: bool = False, avoid_hours: list = None):
        self.di_threshold   = di_threshold
        self.rr             = rr
        self.adx_min        = adx_min
        self.di_persist     = max(1, di_persist)
        self.adx_rising     = adx_rising
        self.sma_ordered    = sma_ordered
        self.di_spread_min  = di_spread_min
        self.rsi_filter     = rsi_filter
        self.body_ratio_min = body_ratio_min
        self.vol_ratio_min  = vol_ratio_min
        self.atr_ratio_min  = atr_ratio_min
        self.di_slope       = di_slope
        self.avoid_hours    = avoid_hours or []

    def get_name(self) -> str:
        return "SmaScalping"

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str,
                target_rr: float = 5.0, spread: float = 0.0,
                params: Optional[Dict] = None) -> Optional[Dict]:

        df = data.get('base')
        if df is None or len(df) < 101:
            return None

        # Per-asset param overrides from best_strategies.json
        di_threshold   = float(params.get('di_threshold',   self.di_threshold))   if params else self.di_threshold
        adx_min        = float(params.get('adx_min',        self.adx_min))        if params else self.adx_min
        di_persist     = max(1, int(params.get('di_persist', self.di_persist)))    if params else self.di_persist
        adx_rising     = bool(params.get('adx_rising',      self.adx_rising))     if params else self.adx_rising
        sma_ordered    = bool(params.get('sma_ordered',     self.sma_ordered))    if params else self.sma_ordered
        di_spread_min  = float(params.get('di_spread_min',  self.di_spread_min))  if params else self.di_spread_min
        rsi_filter     = bool(params.get('rsi_filter',      self.rsi_filter))     if params else self.rsi_filter
        body_ratio_min = float(params.get('body_ratio_min', self.body_ratio_min)) if params else self.body_ratio_min
        vol_ratio_min  = float(params.get('vol_ratio_min',  self.vol_ratio_min))  if params else self.vol_ratio_min
        atr_ratio_min  = float(params.get('atr_ratio_min',  self.atr_ratio_min))  if params else self.atr_ratio_min
        di_slope       = bool(params.get('di_slope',        self.di_slope))       if params else self.di_slope
        avoid_hours    = list(params.get('avoid_hours',     self.avoid_hours))    if params else self.avoid_hours

        if len(df) < di_persist + 1:
            return None

        df = df.copy()
        df = TechnicalIndicators.add_all_indicators(df)
        for period, col in [(20, 'SMA20'), (50, 'SMA50'), (100, 'SMA100')]:
            if col not in df.columns:
                df[col] = df['Close'].rolling(period).mean()

        latest = df.iloc[-1]

        required = ['SMA20', 'SMA50', 'SMA100', 'DIPlus', 'DIMinus', 'ADX', 'Low', 'High', 'Open']
        if not all(col in latest.index and pd.notna(latest[col]) for col in required):
            return None

        adx_ok = latest['ADX'] >= adx_min

        # DI persistence: last di_persist rows must all exceed the threshold
        recent_di_plus  = df['DIPlus'].iloc[-di_persist:].values
        recent_di_minus = df['DIMinus'].iloc[-di_persist:].values
        di_plus_pers  = bool((recent_di_plus  > di_threshold).all())
        di_minus_pers = bool((recent_di_minus > di_threshold).all())

        # Filter 1: ADX Rising — momentum must be building, not fading
        if adx_rising and len(df) >= 2:
            adx_rising_ok = bool(latest['ADX'] > df['ADX'].iloc[-2])
        else:
            adx_rising_ok = True

        # Filter 2: SMA Ordered — SMAs must be properly stacked (not just price above them)
        sma_ordered_buy  = (latest['SMA20'] > latest['SMA50'] > latest['SMA100']) if sma_ordered else True
        sma_ordered_sell = (latest['SMA20'] < latest['SMA50'] < latest['SMA100']) if sma_ordered else True

        # Filter 3: DI Spread — minimum directional conviction gap
        di_spread_buy  = (latest['DIPlus']  - latest['DIMinus']) >= di_spread_min
        di_spread_sell = (latest['DIMinus'] - latest['DIPlus'])  >= di_spread_min

        # Filter 4: RSI mid-level — momentum zone, not extreme
        if rsi_filter and 'RSI' in latest.index and pd.notna(latest['RSI']):
            rsi_buy  = 50.0 < float(latest['RSI']) < 75.0
            rsi_sell = 25.0 < float(latest['RSI']) < 50.0
        else:
            rsi_buy = rsi_sell = True

        # Filter 5: Candle body ratio — reject doji/indecision candles
        if body_ratio_min > 0.0:
            candle_range = float(latest['High']) - float(latest['Low'])
            if candle_range > 0:
                body_buy  = (float(latest['Close']) - float(latest['Open'])) / candle_range >= body_ratio_min
                body_sell = (float(latest['Open']) - float(latest['Close'])) / candle_range >= body_ratio_min
            else:
                body_buy = body_sell = False
        else:
            body_buy = body_sell = True

        # Filter 6: Volume expansion — entry volume must exceed N × 20-bar average
        if vol_ratio_min > 0.0 and 'Volume' in df.columns:
            vol_avg = df['Volume'].iloc[-21:-1].mean()
            vol_ok  = (vol_avg > 0) and (float(latest['Volume']) >= vol_ratio_min * vol_avg)
        else:
            vol_ok = True

        # Filter 7: ATR expansion — ATR must be expanding vs its 20-bar average
        if atr_ratio_min > 0.0 and 'ATR' in df.columns:
            atr_avg    = df['ATR'].iloc[-21:-1].mean()
            atr_exp_ok = (atr_avg > 0) and (float(latest['ATR']) >= atr_ratio_min * atr_avg)
        else:
            atr_exp_ok = True

        # Filter 8: DI slope — DI+ must be rising over last 2 candles (not just sustained)
        if di_slope and len(df) >= 3:
            di_slope_buy  = bool(df['DIPlus'].iloc[-1]  > df['DIPlus'].iloc[-3])
            di_slope_sell = bool(df['DIMinus'].iloc[-1] > df['DIMinus'].iloc[-3])
        else:
            di_slope_buy = di_slope_sell = True

        # Filter 9: Session filter — block entries during specified UTC hours
        if avoid_hours and hasattr(latest.name, 'hour'):
            session_ok = latest.name.hour not in avoid_hours
        else:
            session_ok = True

        is_buy = (
            latest['Close'] > latest['SMA20'] and
            latest['Close'] > latest['SMA50'] and
            latest['Close'] > latest['SMA100'] and
            di_plus_pers and
            latest['DIPlus'] > latest['DIMinus'] and
            adx_ok and
            adx_rising_ok and
            sma_ordered_buy and
            di_spread_buy and
            rsi_buy and
            body_buy and
            vol_ok and
            atr_exp_ok and
            di_slope_buy and
            session_ok
        )
        is_sell = (
            latest['Close'] < latest['SMA20'] and
            latest['Close'] < latest['SMA50'] and
            latest['Close'] < latest['SMA100'] and
            di_minus_pers and
            latest['DIMinus'] > latest['DIPlus'] and
            adx_ok and
            adx_rising_ok and
            sma_ordered_sell and
            di_spread_sell and
            rsi_sell and
            body_sell and
            vol_ok and
            atr_exp_ok and
            di_slope_sell and
            session_ok
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
                "RSI":     round(float(latest['RSI']), 1) if 'RSI' in latest.index and pd.notna(latest['RSI']) else None,
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
