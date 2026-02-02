"""
Gamma-EMA Confluence Strategy V2 - OPTIMIZED
===============================================
Optimized version based on backtest analysis.

Key Improvements:
1. Entry window: 11:00 - 15:15 (was 13:30 - 15:15) ➜ 2.4x more time
2. Stop Loss: 35% (was 25%) ➜ Fewer SL hits
3. Target: 1:2 RR (50%) instead of 1:4 (100%) ➜ More target hits
4. Sideways exit: 10 mins (was 5 mins)
5. Best entry focus: 14:00-15:00 hour prioritized
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from strategies.base_strategy import BaseStrategy, Signal, SignalType


class GammaEMAConfluenceV2(BaseStrategy):
    """
    Gamma-EMA Confluence Strategy V2 - Optimized Parameters
    """
    
    def __init__(self, config: Dict = None):
        super().__init__("Gamma_EMA_V2", config)
    
    def _configure(self):
        """Set optimized configuration."""
        self.default_config = {
            # EMA settings
            'ema_period': 9,
            
            # OPTIMIZED: Wider entry window (11:00 - 15:15)
            'entry_time_start': '11:00',  # Was 13:30
            'entry_time_end': '15:15',
            'exit_time': '15:25',
            
            # OPTIMIZED: Risk management
            'stop_loss_pct': 35,      # Was 25% - gives more room
            'initial_rr': 2,          # Was 4 - more achievable target
            'target_pct': 70,         # 35% SL × 2 RR = 70% target
            'trail_start_rr': 1.5,    # Start trailing at 1:1.5 RR
            'breakeven_trigger': 50,  # Move to breakeven at 50% gain (was 100%)
            
            # OPTIMIZED: Time exit
            'sideways_exit_minutes': 10,  # Was 5
            
            # EMA slope threshold
            'ema_slope_threshold': 0.01,
            
            # Contract filter (keep flexible)
            'min_premium': 5,
            'max_premium': 500,
        }
        
        for key, value in self.default_config.items():
            if key not in self.config:
                self.config[key] = value
    
    def generate_signals(self, index_df: pd.DataFrame, 
                        strikes_data: Dict[str, Dict[int, pd.DataFrame]],
                        symbol: str) -> List[Signal]:
        """Generate optimized Gamma-EMA signals."""
        self.signals = []
        
        if symbol not in ['NIFTY', 'SENSEX', 'BANKNIFTY']:
            print(f"⚠️ Strategy supports NIFTY/SENSEX/BANKNIFTY, got {symbol}")
            return self.signals
        
        # Add technical indicators
        df = self._add_indicators(index_df)
        
        # Get symbol-specific parameters
        strike_gap = {'NIFTY': 50, 'BANKNIFTY': 100, 'SENSEX': 100}.get(symbol, 50)
        
        print(f"   V2 Config: SL={self.config['stop_loss_pct']}%, Target={self.config['target_pct']}%, Entry={self.config['entry_time_start']}-{self.config['entry_time_end']}")
        
        # Track last signal time to avoid duplicate signals
        last_signal_time = None
        min_signal_gap = 3  # Minimum 3 minutes between signals
        
        # Iterate through candles
        for i in range(2, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            prev_prev_row = df.iloc[i-2]
            timestamp = row['timestamp']
            
            # Check timing
            time_str = timestamp.strftime('%H:%M')
            if not (self.config['entry_time_start'] <= time_str <= self.config['entry_time_end']):
                continue
            
            # Skip if too close to last signal
            if last_signal_time:
                mins_since_last = (timestamp - last_signal_time).total_seconds() / 60
                if mins_since_last < min_signal_gap:
                    continue
            
            spot = row['close']
            
            # Skip if EMA not ready
            if pd.isna(row.get('ema')) or pd.isna(row.get('ema_slope_smooth')):
                continue
            
            # Check for Call setup
            if self._check_call_setup(row, prev_row, prev_prev_row):
                signal = self._find_option(spot, strikes_data, timestamp, strike_gap, symbol, 'CE')
                if signal:
                    self.signals.append(signal)
                    last_signal_time = timestamp
            
            # Check for Put setup
            elif self._check_put_setup(row, prev_row, prev_prev_row):
                signal = self._find_option(spot, strikes_data, timestamp, strike_gap, symbol, 'PE')
                if signal:
                    self.signals.append(signal)
                    last_signal_time = timestamp
        
        return self.signals
    
    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add EMA and slope indicators."""
        df = df.copy()
        
        period = self.config['ema_period']
        
        df['ema'] = df['close'].ewm(span=period, adjust=False).mean()
        df['ema_slope'] = df['ema'].diff() / df['ema'].shift(1) * 100
        df['ema_slope_smooth'] = df['ema_slope'].rolling(window=3).mean()
        df['above_ema'] = df['close'] > df['ema']
        df['below_ema'] = df['close'] < df['ema']
        
        return df
    
    def _check_call_setup(self, row, prev_row, prev_prev_row) -> bool:
        """Check for Long Call entry conditions."""
        if not row['above_ema']:
            return False
        
        if row['ema_slope_smooth'] < self.config['ema_slope_threshold']:
            return False
        
        if row['high'] > prev_row['high']:
            if prev_row['above_ema'] and prev_prev_row['above_ema']:
                return True
        
        return False
    
    def _check_put_setup(self, row, prev_row, prev_prev_row) -> bool:
        """Check for Long Put entry conditions."""
        if not row['below_ema']:
            return False
        
        if row['ema_slope_smooth'] > -self.config['ema_slope_threshold']:
            return False
        
        if row['low'] < prev_row['low']:
            if prev_row['below_ema'] and prev_prev_row['below_ema']:
                return True
        
        return False
    
    def _find_option(self, spot: float, strikes_data: Dict,
                     timestamp: pd.Timestamp, strike_gap: int,
                     symbol: str, option_type: str) -> Optional[Signal]:
        """Find suitable option."""
        atm_strike = round(spot / strike_gap) * strike_gap
        
        # Search direction based on option type
        offsets = range(1, 6) if option_type == 'CE' else range(1, 6)
        
        for offset in offsets:
            if option_type == 'CE':
                strike = atm_strike + (offset * strike_gap)
            else:
                strike = atm_strike - (offset * strike_gap)
            
            premium = self._get_option_price(strikes_data, option_type, strike, timestamp)
            if premium is None:
                continue
            
            if premium < self.config['min_premium'] or premium > self.config['max_premium']:
                continue
            
            # Calculate targets with optimized RR
            sl_pct = self.config['stop_loss_pct']
            target_pct = self.config['target_pct']
            
            stop_loss = premium * (1 - sl_pct / 100)
            target = premium * (1 + target_pct / 100)
            
            signal_type = SignalType.BUY_CE if option_type == 'CE' else SignalType.BUY_PE
            distance = abs(strike - spot)
            
            return Signal(
                timestamp=timestamp,
                signal_type=signal_type,
                strike=strike,
                entry_price=premium,
                stop_loss=stop_loss,
                target=target,
                reason=f"V2 {option_type}: Spot={spot:.0f}, Strike={strike}, Prem=₹{premium:.1f}, SL={sl_pct}%, TGT={target_pct}%",
                strength=0.9
            )
        
        return None
    
    def _get_option_price(self, strikes_data: Dict, option_type: str,
                          strike: int, timestamp: pd.Timestamp) -> Optional[float]:
        """Get option price at a specific timestamp."""
        if strike not in strikes_data.get(option_type, {}):
            return None
        
        df = strikes_data[option_type][strike]
        row = df[df['timestamp'] == timestamp]
        
        if row.empty:
            df_sorted = df.iloc[(df['timestamp'] - timestamp).abs().argsort()[:1]]
            if not df_sorted.empty:
                return df_sorted['close'].iloc[0]
            return None
        
        return row['close'].iloc[0]
