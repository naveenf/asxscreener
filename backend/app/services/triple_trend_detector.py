"""
Triple Confirmation Trend Detector

Logic:
- Anchor: Fibonacci Structure Trend (50-bar)
- Confirmation: Pivot Point Supertrend
- Trigger: Ehlers Instantaneous Trend Crossover

Screening is performed on T-1 (previous day's close) to ensure stability.
"""

import pandas as pd
import numpy as np
from typing import Dict, Optional
from .indicators import TechnicalIndicators
from .strategy_interface import ForexStrategy

class TripleTrendDetector(ForexStrategy):
    """Detect signals using Fibonacci, Supertrend, and Instant Trend alignment."""

    def __init__(
        self,
        fib_period: int = 50,
        st_factor: float = 3.0,
        it_alpha: float = 0.07,
        profit_target: float = 0.15,
        stop_loss: float = 0.10,
        time_limit: int = 90
    ):
        self.fib_period = fib_period
        self.st_factor = st_factor
        self.it_alpha = it_alpha
        self.profit_target = profit_target
        self.stop_loss = stop_loss
        self.time_limit = time_limit

    def get_name(self) -> str:
        return "TripleTrend"

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 2.0, spread: float = 0.0, params: Optional[Dict] = None) -> Optional[Dict]:
        """
        Analyze using MTF data.
        Primary analysis on 'base' timeframe.
        Optional confirmation from 'htf' if available.
        """
        df = data.get('base') 
        df_htf = data.get('htf')

        if df is None or len(df) < 50:
            return None

        # Add indicators to execution timeframe
        df = TechnicalIndicators.add_all_indicators(
            df, 
            fib_period=self.fib_period,
            st_factor=self.st_factor,
            it_alpha=self.it_alpha
        )

        latest = df.iloc[-1]
        prev = df.iloc[-2]

        # 1. Fibonacci Anchor (Long term)
        fib_bullish = latest['Fib_Pos'] > 0
        fib_bearish = latest['Fib_Pos'] < 0

        # 2. Supertrend Confirmation (Mid term)
        st_bullish = latest['PP_Trend'] == 1
        st_bearish = latest['PP_Trend'] == -1

        # 3. Instant Trend Trigger (Short term)
        # Crossover
        it_crossover_bull = (prev['IT_Trigger'] <= prev['IT_Trend']) and (latest['IT_Trigger'] > latest['IT_Trend'])
        it_crossover_bear = (prev['IT_Trigger'] >= prev['IT_Trend']) and (latest['IT_Trigger'] < latest['IT_Trend'])

        # 4. HTF Confirmation - Optional but powerful
        htf_confirmed = True
        if df_htf is not None and len(df_htf) > 20:
            df_htf = TechnicalIndicators.calculate_pivot_supertrend(df_htf, factor=3.0)
            latest_htf = df_htf.iloc[-1]
            if st_bullish and latest_htf['PP_Trend'] != 1: htf_confirmed = False
            if st_bearish and latest_htf['PP_Trend'] != -1: htf_confirmed = False

        # Signal Logic
        is_buy = fib_bullish and st_bullish and it_crossover_bull and htf_confirmed
        is_sell = fib_bearish and st_bearish and it_crossover_bear and htf_confirmed

        if not (is_buy or is_sell):
            return None

        # Calculate Score
        score = 50.0
        if is_buy:
             if latest['Fib_Pos'] > 0: score += 15
             if latest['PP_Trend'] == 1: score += 15
             if htf_confirmed: score += 20
        else:
             if latest['Fib_Pos'] < 0: score += 15
             if latest['PP_Trend'] == -1: score += 15
             if htf_confirmed: score += 20
        
        price = float(latest['Close'])
        stop_loss = float(latest['PP_TrailingSL']) if 'PP_TrailingSL' in latest else price * (0.99 if is_buy else 1.01)
        
        # Calculate TP
        risk = abs(price - stop_loss)
        signal_type = "BUY" if is_buy else "SELL"
        take_profit = price + (risk * target_rr if signal_type == "BUY" else -risk * target_rr)

        return {
            "signal": signal_type,
            "score": min(score, 100.0),
            "strategy": self.get_name(),
            "symbol": symbol,
            "price": price,
            "timestamp": latest.name.isoformat() if hasattr(latest.name, 'isoformat') else str(latest.name),
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "ADX": 0.0,
                "Fib_Pos": int(latest.get('Fib_Pos', 0)),
                "PP_Trend": int(latest.get('PP_Trend', 0)),
                "IT_Trend": round(float(latest.get('IT_Trend', 0)), 2),
                "vol_accel": 0.0,
                "di_momentum": 0.0,
                "DIPlus": 0.0,
                "DIMinus": 0.0,
                "is_power_volume": False,
                "is_power_momentum": False
            }
        }

    def detect_entry_signal(self, df: pd.DataFrame) -> Dict:
        """
        Backward compatibility for StockScreener and API.
        """
        if df is None or len(df) < 50:
            return {'has_signal': False}
            
        # Ensure indicators are present
        if 'Fib_Pos' not in df.columns:
            df = TechnicalIndicators.add_all_indicators(df, fib_period=self.fib_period, st_factor=self.st_factor, it_alpha=self.it_alpha)

        latest = df.iloc[-1]
        prev = df.iloc[-2]
        
        # Logic from analyze() - handling NaNs
        fib_pos = latest.get('Fib_Pos', 0)
        pp_trend = latest.get('PP_Trend', 0)
        it_trigger = latest.get('IT_Trigger', 0)
        it_trend = latest.get('IT_Trend', 0)
        
        fib_bullish = not pd.isna(fib_pos) and fib_pos > 0
        st_bullish = not pd.isna(pp_trend) and pp_trend == 1
        
        it_curr_trigger = latest.get('IT_Trigger', 0)
        it_curr_trend = latest.get('IT_Trend', 0)
        it_prev_trigger = prev.get('IT_Trigger', 0)
        it_prev_trend = prev.get('IT_Trend', 0)
        
        it_crossover_bull = (it_prev_trigger <= it_prev_trend) and (it_curr_trigger > it_curr_trend)
        
        has_signal = fib_bullish and st_bullish and it_crossover_bull
        
        return {
            'has_signal': has_signal,
            'is_bullish': fib_bullish or st_bullish,
            'fib_pos': 0 if pd.isna(fib_pos) else fib_pos,
            'st_trend': 0 if pd.isna(pp_trend) else pp_trend
        }

    def detect_exit_signal(self, df: pd.DataFrame, entry_price: float, current_index: int = -1, entry_index: int = None) -> Dict:
        """
        Backward compatibility for Portfolio API.
        """
        if df is None or len(df) < 2:
            return {'has_exit': False}
            
        data = {'base': df}
        res = self.check_exit(data, "BUY", entry_price) # Assume BUY for portfolio trend
        
        if res and res.get('exit_signal'):
            return {
                'has_exit': True,
                'exit_reason': res.get('reason')
            }
        return {'has_exit': False}

    def calculate_score(self, signal_info: Dict, df: pd.DataFrame) -> float:
        """
        Backward compatibility for scoring.
        """
        score = 50.0
        latest = df.iloc[-1]
        fib_pos = latest.get('Fib_Pos', 0)
        pp_trend = latest.get('PP_Trend', 0)
        it_trigger = latest.get('IT_Trigger', 0)
        it_trend = latest.get('IT_Trend', 0)
        
        if not pd.isna(fib_pos) and fib_pos > 0: score += 15
        if not pd.isna(pp_trend) and pp_trend == 1: score += 15
        if not pd.isna(it_trigger) and not pd.isna(it_trend) and it_trigger > it_trend: score += 20
        return min(score, 100.0)

    def analyze_stock(self, df: pd.DataFrame, ticker: str, name: str = None) -> Optional[Dict]:
        """
        Backward compatibility wrapper for StockScreener.
        """
        # Adapt single dataframe to the new interface expectations
        data = {'base': df, 'htf': None}
        
        result = self.analyze(data, ticker)
        
        if result and result.get('signal') == 'BUY':
            # Remap to the format StockScreener expects
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            return {
                'ticker': ticker,
                'name': name or ticker,
                'signal': 'BUY',
                'strategy': 'trend_following',
                'score': result['score'],
                'current_price': result['price'],
                'indicators': {
                    'Fib_Pos': int(latest.get('Fib_Pos', 0)),
                    'PP_Trend': int(latest.get('PP_Trend', 0)),
                    'IT_Trend': round(float(latest.get('IT_Trend', 0)), 2),
                    'IT_Trigger': round(float(latest.get('IT_Trigger', 0)), 2),
                    'SMA200': round(float(latest.get('SMA200', 0)), 2) if 'SMA200' in latest else None,
                    'above_sma200': bool(latest['Close'] > latest.get('SMA200', 999999)) if 'SMA200' in latest else False
                },
                'entry_conditions': {
                    'fib_structure_bullish': bool(latest.get('Fib_Pos', 0) > 0),
                    'supertrend_bullish': bool(latest.get('PP_Trend', 0) == 1),
                    'it_trend_bullish': bool(latest.get('IT_Trigger', 0) > latest.get('IT_Trend', 0))
                },
                'timestamp': result['timestamp']
            }
        return None

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        """
        Exit if Supertrend reverses.
        """
        df = data.get('base')
        if df is None or len(df) < 50: return None
        
        # Ensure indicators
        if 'PP_Trend' not in df.columns:
            df = TechnicalIndicators.add_all_indicators(df, st_factor=self.st_factor)
            
        latest = df.iloc[-1]
        pp_trend = int(latest.get('PP_Trend', 0))
        close = float(latest['Close'])
        
        exit_signal = False
        reason = None
        
        if direction == "BUY":
            if pp_trend == -1:
                exit_signal = True
                reason = f"Supertrend flipped Bearish (Close: {close:.4f})"
        elif direction == "SELL":
            if pp_trend == 1:
                exit_signal = True
                reason = f"Supertrend flipped Bullish (Close: {close:.4f})"
                
        if exit_signal:
            return {
                "exit_signal": True,
                "reason": reason
            }
        return None
