import pandas as pd
import numpy as np
import sys
from pathlib import Path
from typing import List, Dict

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.append(str(PROJECT_ROOT))

from backend.app.services.indicators import TechnicalIndicators
from backend.app.services.heiken_ashi_detector import HeikenAshiDetector

# Configuration - Focus strictly on Gold as per Review requirements
SYMBOL = "XAU_USD"
TIMEFRAME = "1_Hour"
HTF_TIMEFRAME = "4_Hour"
SPREAD = 0.40
STARTING_BALANCE = 10000
RISK_PER_TRADE = 0.01
TARGET_RR = 3.0
SLIPPAGE_AVG = 0.15 
SLIPPAGE_STD = 0.05

class GoldStabilityTester:
    def __init__(self, detector: HeikenAshiDetector):
        self.detector = detector

    def get_slippage(self):
        return max(0, np.random.normal(SLIPPAGE_AVG, SLIPPAGE_STD))

    def run_simulation(self, df_base, df_htf):
        # Pre-calculate for speed
        df_base = TechnicalIndicators.add_all_indicators(df_base, sma_period=self.detector.sma_period)
        ha_df = TechnicalIndicators.calculate_heiken_ashi(df_base)
        bb_mid, _, _ = TechnicalIndicators.calculate_ha_bollinger_bands(ha_df, period=self.detector.bb_period)
        ha_df['HA_BB_Middle'] = bb_mid
        ha_df['SMA200'] = df_base[f'SMA{self.detector.sma_period}']
        ha_df['Close_Reg'] = df_base['Close']
        ha_df['High_Reg'] = df_base['High']
        ha_df['Low_Reg'] = df_base['Low']
        ha_df['Open_Reg'] = df_base['Open']
        ha_df['ADX'] = df_base['ADX']
        ha_df['is_above'] = ha_df['HA_Close'] > ha_df['HA_BB_Middle']
        ha_df['cross_up'] = (ha_df['is_above']) & (~ha_df['is_above'].shift(1, fill_value=False))
        ha_df['cross_down'] = (~ha_df['is_above']) & (ha_df['is_above'].shift(1, fill_value=True))

        if df_htf is not None:
            df_htf = TechnicalIndicators.add_all_indicators(df_htf, sma_period=self.detector.sma_period)

        balance = STARTING_BALANCE
        trades = []
        position = None
        records = ha_df.to_dict('records')
        timestamps = ha_df.index.tolist()

        for i in range(250, len(records)):
            current_row = records[i]
            current_time = timestamps[i]
            
            # HTF Filter
            htf_trend = 0
            if df_htf is not None:
                relevant_htf = df_htf[df_htf.index <= current_time]
                if not relevant_htf.empty:
                    latest_htf = relevant_htf.iloc[-1]
                    sma_htf = latest_htf[f'SMA{self.detector.sma_period}']
                    if latest_htf['Close'] > sma_htf: htf_trend = 1
                    elif latest_htf['Close'] < sma_htf: htf_trend = -1

            # 1. Check Exit
            if position:
                hit_sl = False
                hit_tp = False
                if position['type'] == "BUY":
                    if current_row['Low_Reg'] <= position['sl']: hit_sl = True
                    elif current_row['High_Reg'] >= position['tp']: hit_tp = True
                else:
                    if current_row['High_Reg'] >= position['sl']: hit_sl = True
                    elif current_row['Low_Reg'] <= position['tp']: hit_tp = True
                    
                if hit_sl or hit_tp:
                    exit_price_raw = position['sl'] if hit_sl else position['tp']
                    exit_price = exit_price_raw + ((-SPREAD - self.get_slippage()) if position['type'] == "BUY" else (SPREAD + self.get_slippage()))
                    pnl = (exit_price - position['entry_price']) * position['units'] if position['type'] == "BUY" else (position['entry_price'] - exit_price) * position['units']
                    balance += pnl
                    trades.append({"pnl": pnl, "r": pnl / position['dollar_risk']})
                    position = None
                    continue
                
                # Strategy Exit
                exit_signal = (position['type'] == "BUY" and current_row['HA_Close'] < current_row['HA_BB_Middle']) or \
                              (position['type'] == "SELL" and current_row['HA_Close'] > current_row['HA_BB_Middle'])
                
                if exit_signal and i + 1 < len(records):
                    exit_price_raw = records[i+1]['Open_Reg']
                    exit_price = exit_price_raw + ((-SPREAD - self.get_slippage()) if position['type'] == "BUY" else (SPREAD + self.get_slippage()))
                    pnl = (exit_price - position['entry_price']) * position['units'] if position['type'] == "BUY" else (position['entry_price'] - exit_price) * position['units']
                    balance += pnl
                    trades.append({"pnl": pnl, "r": pnl / position['dollar_risk']})
                    position = None
                    continue

            # 2. Check Entry
            if not position:
                if current_row['ADX'] < self.detector.adx_min: continue
                recent_rows = records[max(0, i-self.detector.freshness_window+1):i+1]
                
                # BUY
                if htf_trend >= 0 and current_row['HA_Close'] > current_row['HA_Open'] and \
                   current_row['HA_Close'] > current_row['HA_BB_Middle'] and \
                   current_row['Close_Reg'] > current_row['SMA200'] and any(r['cross_up'] for r in recent_rows):
                    
                    entry_price = current_row['Close_Reg'] + SPREAD + self.get_slippage()
                    sl = min(r['Low_Reg'] for r in records[i-2:i+1])
                    if entry_price - sl < SPREAD: sl = entry_price - (SPREAD*2)
                    risk = entry_price - sl
                    dollar_risk = balance * RISK_PER_TRADE
                    position = {"type": "BUY", "entry_price": entry_price, "sl": sl, "tp": entry_price + (risk * TARGET_RR),
                                "units": dollar_risk / risk, "entry_time": current_time, "dollar_risk": dollar_risk}
                
                # SELL
                elif htf_trend <= 0 and current_row['HA_Close'] < current_row['HA_Open'] and \
                     current_row['HA_Close'] < current_row['HA_BB_Middle'] and \
                     current_row['Close_Reg'] < current_row['SMA200'] and any(r['cross_down'] for r in recent_rows):
                    
                    entry_price = current_row['Close_Reg'] - SPREAD - self.get_slippage()
                    sl = max(r['High_Reg'] for r in records[i-2:i+1])
                    if sl - entry_price < SPREAD: sl = entry_price + (SPREAD*2)
                    risk = sl - entry_price
                    dollar_risk = balance * RISK_PER_TRADE
                    position = {"type": "SELL", "entry_price": entry_price, "sl": sl, "tp": entry_price - (risk * TARGET_RR),
                                "units": dollar_risk / risk, "entry_time": current_time, "dollar_risk": dollar_risk}

        return trades

    def walk_forward_analysis(self, windows=5):
        base_path = PROJECT_ROOT / "data" / "forex_raw" / f"{SYMBOL}_{TIMEFRAME}.csv"
        htf_path = PROJECT_ROOT / "data" / "forex_raw" / f"{SYMBOL}_{HTF_TIMEFRAME}.csv"
        
        df_base = pd.read_csv(base_path)
        df_base['Date'] = pd.to_datetime(df_base['Date'], utc=True)
        df_base.set_index('Date', inplace=True)
        
        df_htf = pd.read_csv(htf_path)
        df_htf['Date'] = pd.to_datetime(df_htf['Date'], utc=True)
        df_htf.set_index('Date', inplace=True)

        total_len = len(df_base)
        window_size = total_len // (windows + 1)
        
        print(f"Starting Walk-Forward Analysis for {SYMBOL} ({windows} windows)...")
        results = []
        
        for w in range(windows):
            train_start = w * (window_size // 2)
            train_end = train_start + (window_size * 2)
            test_start = train_end
            test_end = test_start + window_size
            
            if test_end > total_len: break
            
            train_df = df_base.iloc[train_start:train_end]
            test_df = df_base.iloc[test_start:test_end]
            
            train_trades = self.run_simulation(train_df, df_htf)
            test_trades = self.run_simulation(test_df, df_htf)
            
            train_r = np.mean([t['r'] for t in train_trades]) if train_trades else 0
            test_r = np.mean([t['r'] for t in test_trades]) if test_trades else 0
            
            stability = test_r / train_r if train_r > 0 else 0
            results.append({
                "window": w+1,
                "train_trades": len(train_trades),
                "test_trades": len(test_trades),
                "train_avg_r": train_r,
                "test_avg_r": test_r,
                "stability": stability
            })
            print(f"  Window {w+1}: Train R={train_r:.2f} ({len(train_trades)} trades), Test R={test_r:.2f} ({len(test_trades)} trades), Stability={stability:.2f}")

        avg_stability = np.mean([r['stability'] for r in results])
        print("\n" + "="*50)
        print(f"FINAL WALK-FORWARD RESULTS FOR {SYMBOL}")
        print("="*50)
        print(f"Average Stability Factor: {avg_stability:.2f}")
        print(f"Total Windows:           {len(results)}")
        print(f"Overall Recommendation:  {'✅ ROBUST' if avg_stability > 0.7 else '❌ OVERFIT/UNSTABLE'}")
        print("="*50)

if __name__ == "__main__":
    detector = HeikenAshiDetector(
        adx_min=22.0,        # Slightly relaxed to increase frequency
        freshness_window=4,  # Increased window to capture more setups
        bb_period=20,
        bb_std=2.0
    )
    tester = GoldStabilityTester(detector)
    tester.walk_forward_analysis(windows=6)