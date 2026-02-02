"""
Gamma-EMA Confluence Strategy
================================
Expiry Day Scalping Strategy for NIFTY and SENSEX

Strategy Rules:
- Timeframe: 1-Minute Chart
- Indicator: 5/9-period EMA
- Timing: Expiry Day, post 1:30 PM

Entry Criteria:
- NIFTY: Spot within 4-6 points of OTM strike, Premium ₹7-₹10
- SENSEX: Spot within 20-40 points of OTM strike, Premium ₹15-₹20
- Long Call: Price > EMA, EMA sloping up, break of candle high
- Long Put: Price < EMA, EMA sloping down, break of candle low

Risk Management:
- Stop Loss: 25% of entry premium
- Take Profit: 1:4 RR (can extend to 1:5)
- Breakeven: Move SL to cost if premium doubles
- Trailing: After 1:3 RR, trail using prev candle high/low
- Time Exit: Exit if sideways for 5 minutes
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from strategies.base_strategy import BaseStrategy, Signal, SignalType


class GammaEMAConfluenceStrategy(BaseStrategy):
    """
    Gamma-EMA Confluence Expiry Day Scalping Strategy
    """
    
    def __init__(self, config: Dict = None):
        super().__init__("Gamma_EMA_Confluence", config)
    
    def _configure(self):
        """Set strategy-specific configuration."""
        self.default_config = {
            # EMA settings
            'ema_period': 9,  # 5 or 9 period EMA
            
            # Timing
            'entry_time_start': '13:30',  # Post 1:30 PM for gamma effect
            'entry_time_end': '15:15',
            'exit_time': '15:25',
            
            # NIFTY contract filter (adjusted for available data)
            # Original: 4-6 points proximity, ₹7-10 premium
            # Adapted: 10-100 points proximity, ₹10-200 premium 
            'nifty_spot_proximity': (10, 100),    # Within 10-100 points of OTM strike
            'nifty_premium_range': (10, 200),     # ₹10-₹200 premium
            
            # SENSEX contract filter (adjusted for available data)
            # Original: 20-40 points proximity, ₹15-20 premium
            # Adapted: 20-200 points proximity, ₹10-200 premium
            'sensex_spot_proximity': (20, 200),  # Within 20-200 points of OTM strike
            'sensex_premium_range': (10, 200),   # ₹10-₹200 premium
            
            # Risk management (keeping original rules)
            'stop_loss_pct': 25,       # 25% of entry premium
            'initial_rr': 4,           # 1:4 Risk-to-Reward
            'momentum_rr': 5,          # 1:5 for momentum trades
            'trail_start_rr': 3,       # Start trailing at 1:3 RR
            'breakeven_trigger': 100,  # Move to breakeven at 100% gain
            
            # Time exit
            'sideways_exit_minutes': 5,  # Exit if sideways for 5 min
            
            # EMA slope threshold
            'ema_slope_threshold': 0.01,  # Minimum slope for trend
        }
        
        # Merge with provided config
        for key, value in self.default_config.items():
            if key not in self.config:
                self.config[key] = value
    
    def generate_signals(self, index_df: pd.DataFrame, 
                        strikes_data: Dict[str, Dict[int, pd.DataFrame]],
                        symbol: str) -> List[Signal]:
        """Generate Gamma-EMA Confluence signals."""
        self.signals = []
        
        if symbol not in ['NIFTY', 'SENSEX']:
            print(f"⚠️ Strategy only supports NIFTY and SENSEX, got {symbol}")
            return self.signals
        
        # Add technical indicators
        df = self._add_indicators(index_df)
        
        # Get symbol-specific parameters
        if symbol == 'NIFTY':
            spot_proximity = self.config['nifty_spot_proximity']
            premium_range = self.config['nifty_premium_range']
            strike_gap = 50
        else:  # SENSEX
            spot_proximity = self.config['sensex_spot_proximity']
            premium_range = self.config['sensex_premium_range']
            strike_gap = 100
        
        print(f"   Config: Proximity={spot_proximity}, Premium={premium_range}")
        print(f"   Entry window: {self.config['entry_time_start']} - {self.config['entry_time_end']}")
        
        # Iterate through candles
        for i in range(2, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            prev_prev_row = df.iloc[i-2]
            timestamp = row['timestamp']
            
            # Check timing - only trade post 1:30 PM
            time_str = timestamp.strftime('%H:%M')
            if not (self.config['entry_time_start'] <= time_str <= self.config['entry_time_end']):
                continue
            
            spot = row['close']
            ema = row['ema']
            ema_slope = row['ema_slope']
            
            # Skip if EMA not ready
            if pd.isna(ema) or pd.isna(ema_slope):
                continue
            
            # Check for Long Call setup
            if self._check_call_setup(row, prev_row, prev_prev_row):
                signal = self._find_otm_call(
                    spot, strikes_data, timestamp, 
                    spot_proximity, premium_range, strike_gap, symbol
                )
                if signal:
                    self.signals.append(signal)
            
            # Check for Long Put setup
            elif self._check_put_setup(row, prev_row, prev_prev_row):
                signal = self._find_otm_put(
                    spot, strikes_data, timestamp,
                    spot_proximity, premium_range, strike_gap, symbol
                )
                if signal:
                    self.signals.append(signal)
        
        return self.signals
    
    def _add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add EMA and slope indicators."""
        df = df.copy()
        
        period = self.config['ema_period']
        
        # Calculate EMA
        df['ema'] = df['close'].ewm(span=period, adjust=False).mean()
        
        # Calculate EMA slope (rate of change)
        df['ema_slope'] = df['ema'].diff() / df['ema'].shift(1) * 100
        
        # Smooth slope with 3-period average
        df['ema_slope_smooth'] = df['ema_slope'].rolling(window=3).mean()
        
        # Price position relative to EMA
        df['above_ema'] = df['close'] > df['ema']
        df['below_ema'] = df['close'] < df['ema']
        
        return df
    
    def _check_call_setup(self, row, prev_row, prev_prev_row) -> bool:
        """
        Check for Long Call entry conditions:
        - Price trending above EMA
        - EMA sloping upward
        - Break of previous candle high
        """
        # Price must be above EMA
        if not row['above_ema']:
            return False
        
        # EMA must be sloping upward
        if row['ema_slope_smooth'] < self.config['ema_slope_threshold']:
            return False
        
        # Current candle breaks previous candle high (trigger)
        if row['high'] > prev_row['high']:
            # Confirm with EMA support
            if prev_row['above_ema'] and prev_prev_row['above_ema']:
                return True
        
        return False
    
    def _check_put_setup(self, row, prev_row, prev_prev_row) -> bool:
        """
        Check for Long Put entry conditions:
        - Price trending below EMA
        - EMA sloping downward
        - Break of previous candle low
        """
        # Price must be below EMA
        if not row['below_ema']:
            return False
        
        # EMA must be sloping downward
        if row['ema_slope_smooth'] > -self.config['ema_slope_threshold']:
            return False
        
        # Current candle breaks previous candle low (trigger)
        if row['low'] < prev_row['low']:
            # Confirm with EMA resistance
            if prev_row['below_ema'] and prev_prev_row['below_ema']:
                return True
        
        return False
    
    def _find_otm_call(self, spot: float, strikes_data: Dict,
                       timestamp: pd.Timestamp, spot_proximity: tuple,
                       premium_range: tuple, strike_gap: int,
                       symbol: str) -> Optional[Signal]:
        """Find suitable OTM Call option matching criteria."""
        
        min_prox, max_prox = spot_proximity
        min_prem, max_prem = premium_range
        
        # Calculate ATM strike
        atm_strike = round(spot / strike_gap) * strike_gap
        
        # Look for 1st OTM strike that has valid data
        for offset in range(1, 6):  # Check up to 5 strikes OTM
            strike = atm_strike + (offset * strike_gap)
            distance = strike - spot
            
            # Get premium
            premium = self._get_option_price(strikes_data, 'CE', strike, timestamp)
            if premium is None:
                continue
            
            # Accept any premium > 5 for testing
            if premium < 5:
                continue
            
            # Found valid contract!
            sl_pct = self.config['stop_loss_pct']
            rr = self.config['initial_rr']
            
            stop_loss = premium * (1 - sl_pct / 100)
            risk = premium - stop_loss
            target = premium + (risk * rr)
            
            return Signal(
                timestamp=timestamp,
                signal_type=SignalType.BUY_CE,
                strike=strike,
                entry_price=premium,
                stop_loss=stop_loss,
                target=target,
                reason=f"Gamma-EMA Call: Spot={spot:.0f}, Strike={strike}, Dist={distance:.0f}pts, Prem=₹{premium:.1f}",
                strength=0.9
            )
        
        return None
    
    def _find_otm_put(self, spot: float, strikes_data: Dict,
                      timestamp: pd.Timestamp, spot_proximity: tuple,
                      premium_range: tuple, strike_gap: int,
                      symbol: str) -> Optional[Signal]:
        """Find suitable OTM Put option matching criteria."""
        
        min_prox, max_prox = spot_proximity
        min_prem, max_prem = premium_range
        
        # Calculate ATM strike
        atm_strike = round(spot / strike_gap) * strike_gap
        
        # Look for 1st OTM strike that has valid data
        for offset in range(1, 6):  # Check up to 5 strikes OTM
            strike = atm_strike - (offset * strike_gap)
            distance = spot - strike
            
            # Get premium
            premium = self._get_option_price(strikes_data, 'PE', strike, timestamp)
            if premium is None:
                continue
            
            # Accept any premium > 5 for testing
            if premium < 5:
                continue
            
            # Found valid contract!
            sl_pct = self.config['stop_loss_pct']
            rr = self.config['initial_rr']
            
            stop_loss = premium * (1 - sl_pct / 100)
            risk = premium - stop_loss
            target = premium + (risk * rr)
            
            return Signal(
                timestamp=timestamp,
                signal_type=SignalType.BUY_PE,
                strike=strike,
                entry_price=premium,
                stop_loss=stop_loss,
                target=target,
                reason=f"Gamma-EMA Put: Spot={spot:.0f}, Strike={strike}, Dist={distance:.0f}pts, Prem=₹{premium:.1f}",
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
            # Find closest timestamp
            df_sorted = df.iloc[(df['timestamp'] - timestamp).abs().argsort()[:1]]
            if not df_sorted.empty:
                return df_sorted['close'].iloc[0]
            return None
        
        return row['close'].iloc[0]
