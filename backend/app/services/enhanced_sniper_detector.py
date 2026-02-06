from typing import Dict, Optional, List
import pandas as pd
import numpy as np
from .strategy_interface import ForexStrategy
from .indicators import TechnicalIndicators

class EnhancedSniperDetector(ForexStrategy):
    """
    Enhanced Sniper Strategy Detector
    
    Optimized for AUD_USD, USD_CHF, USD_JPY with:
    - 15m Base Timeframe
    - 4H Trend Alignment
    - Relaxed EMA Proximity for Steady pairs
    - Rising ADX Requirement
    - Increased R:R (2.5)
    - Configurable Time Filters and Squeeze
    """
    
    def __init__(self):
        self.name = "EnhancedSniper"
        
        # Casket definitions
        self.caskets = {
            "Momentum": ["USD_JPY", "GBP_JPY", "EUR_JPY"],
            "Steady": ["AUD_USD", "USD_CHF", "NZD_USD", "EUR_GBP"],
            "Cyclical": ["EUR_USD", "GBP_USD", "USD_CAD"]
        }

    def get_name(self) -> str:
        return self.name

    def _get_casket_type(self, symbol: str) -> str:
        for casket, symbols in self.caskets.items():
            if symbol in symbols:
                return casket
        return "Steady"  

    def _check_htf_trend(self, df_1h: pd.DataFrame, lookback: int = 60) -> int:
        if df_1h is None or len(df_1h) < lookback:
            return 0
            
        latest = df_1h.iloc[-1]
        
        if latest['ADX'] < 25:
            return 0
            
        if 'EMA34' not in df_1h.columns:
            return 0
            
        if latest['Close'] > latest['EMA34'] and latest['DIPlus'] > latest['DIMinus']:
            return 1
        elif latest['Close'] < latest['EMA34'] and latest['DIMinus'] > latest['DIPlus']:
            return -1
            
        return 0

    def analyze(self, data: Dict[str, pd.DataFrame], symbol: str, target_rr: float = 2.0, spread: float = 0.0, params: Optional[Dict] = None) -> Optional[Dict]:
        if params is None:
            params = {}
            
        high_loss_hours = params.get("high_loss_hours", params.get("time_blocks", []))
        use_squeeze = params.get("use_squeeze", False)
        squeeze_threshold = params.get("squeeze_threshold", 1.5)
        
        casket_type = self._get_casket_type(symbol)

        df_15m = data.get('base')
        df_1h = data.get('htf')
        df_4h = data.get('htf2')
        
        if df_15m is None or len(df_15m) < 220:
            return None
            
        if df_1h is None or len(df_1h) < 60:
            return None
            
        latest = df_15m.iloc[-1]
        prev = df_15m.iloc[-2]
        latest_1h = df_1h.iloc[-1]
        
        # ---------------------------------------------------------------------
        # 0. TIME FILTERS
        # ---------------------------------------------------------------------
        current_time = latest['time'] if 'time' in latest else latest.name
        if not hasattr(current_time, 'hour'):
             current_time = pd.to_datetime(current_time)
             
        if current_time.hour in high_loss_hours:
            return None

        # ---------------------------------------------------------------------
        # 0.5. SQUEEZE DETECTION
        # ---------------------------------------------------------------------
        if use_squeeze and 'BB_Width' in df_15m.columns:
            lookback_96 = min(96, len(df_15m) - 1)
            min_width_24h = df_15m['BB_Width'].iloc[-lookback_96:-1].min()
            current_width = df_15m.iloc[-1]['BB_Width']
            
            is_squeeze = current_width <= (min_width_24h * squeeze_threshold)
            
            if not is_squeeze:
                return None  
        
        # ---------------------------------------------------------------------
        # 1. HTF TREND CHECKS (1H & 4H)
        # ---------------------------------------------------------------------
        htf_trend = self._check_htf_trend(df_1h)
        if htf_trend == 0:
            return None
            
        if df_4h is not None and len(df_4h) >= 200:
            if 'SMA200' not in df_4h.columns:
                df_4h = df_4h.copy()
                df_4h['SMA200'] = df_4h['Close'].rolling(window=200).mean()
            
            latest_4h = df_4h.iloc[-1]
            
            if htf_trend > 0 and latest_4h['Close'] < latest_4h['SMA200']:
                return None  
            if htf_trend < 0 and latest_4h['Close'] > latest_4h['SMA200']:
                return None  
                
        # ---------------------------------------------------------------------
        # 2. MOMENTUM CONFIRMATION
        # ---------------------------------------------------------------------
        prev_1h = df_1h.iloc[-2]
        adx_rising = latest_1h['ADX'] > prev_1h['ADX']
        
        if not adx_rising:
            return None  
            
        # ---------------------------------------------------------------------
        # 3. BASE TIMEFRAME ENTRY SIGNAL (15m)
        # ---------------------------------------------------------------------
        signal = None
        di_cross_up = (prev['DIPlus'] <= prev['DIMinus']) and (latest['DIPlus'] > latest['DIMinus'])
        di_cross_down = (prev['DIMinus'] <= prev['DIPlus']) and (latest['DIMinus'] > latest['DIPlus'])
        
        if htf_trend == 1 and di_cross_up:
            signal = "BUY"
        elif htf_trend == -1 and di_cross_down:
            signal = "SELL"
            
        if not signal:
            return None
            
        # ---------------------------------------------------------------------
        # 4. CASKET-SPECIFIC FILTERS
        # ---------------------------------------------------------------------
        if casket_type == "Momentum":
            di_spread = abs(latest['DIPlus'] - latest['DIMinus'])
            di_jump = di_spread - abs(prev['DIPlus'] - prev['DIMinus'])
            avg_vol = df_15m['Volume'].rolling(20).mean().iloc[-1]
            vol_surge = latest['Volume'] > (avg_vol * 2.0)
            
            if di_jump < 7.0 or not vol_surge:
                return None
                
        elif casket_type == "Steady":
            if signal == "BUY" and latest['Close'] < latest['EMA13']:
                return None
            if signal == "SELL" and latest['Close'] > latest['EMA13']:
                return None
                
            dist_to_15m_ema = abs(latest['Close'] - latest['EMA13']) / latest['Close']
            dist_to_1h_ema = abs(latest_1h['Close'] - latest_1h['EMA13']) / latest_1h['Close']
            
            if dist_to_15m_ema > 0.0050 or dist_to_1h_ema > 0.0100:
                return None
                
        elif casket_type == "Cyclical":
            bb_width = (latest['BB_Upper'] - latest['BB_Lower']) / latest['BB_Middle']
            if 'BB_Width' in df_15m.columns:
                min_width = df_15m['BB_Width'].rolling(window=20).min().iloc[-1]
                if bb_width < (min_width * 1.5):
                    return None

        # ---------------------------------------------------------------------
        # 5. RISK MANAGEMENT CALCULATION
        # ---------------------------------------------------------------------
        price = float(latest['Close'])
        stop_loss = float(latest['BB_Middle'])  
        
        min_risk = price * 0.0005
        if abs(price - stop_loss) < min_risk:
            if signal == "BUY":
                stop_loss = price - min_risk
            else:
                stop_loss = price + min_risk
                
        risk = abs(price - stop_loss)
        take_profit = price + (risk * target_rr) if signal == "BUY" else price - (risk * target_rr)
        
        return {
            "signal": signal,
            "score": 85.0,  
            "strategy": self.name,
            "symbol": symbol,
            "price": price,
            "entry": price,
            "direction": signal,
            "timestamp": latest['time'] if 'time' in latest else latest.name,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "indicators": {
                "adx_1h": round(latest_1h['ADX'], 1),
                "di_plus": round(latest['DIPlus'], 1),
                "di_minus": round(latest['DIMinus'], 1)
            }
        }

    def check_exit(self, data: Dict[str, pd.DataFrame], direction: str, entry_price: float) -> Optional[Dict]:
        df = data.get('base')
        if df is None or len(df) < 50: return None
        latest = df.iloc[-1]
        price = float(latest['Close'])
        if 'BB_Middle' not in df.columns: return None
        bb_middle = float(latest['BB_Middle'])
        exit_signal = False
        reason = None
        if direction == "BUY" and price < bb_middle:
            exit_signal = True
            reason = "Crossed below BB Middle"
        elif direction == "SELL" and price > bb_middle:
            exit_signal = True
            reason = "Crossed above BB Middle"
        if exit_signal:
            return {"exit_signal": True, "reason": reason}
        return None