"""
Option Buying Strategies
===========================
These strategies are designed for BUYING options (CE/PE)

Key Characteristics:
- Limited risk (max loss = premium paid)
- Unlimited/high profit potential
- Require strong directional moves
- Time decay works AGAINST you
- Best in trending/volatile markets
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))
from config import NIFTY_LOT_SIZE, BANKNIFTY_LOT_SIZE


class OptionType(Enum):
    CE = "CE"
    PE = "PE"


@dataclass
class OptionBuySignal:
    """Signal for option buying strategy"""
    timestamp: pd.Timestamp
    option_type: OptionType
    strike: int
    entry_premium: float
    stop_loss_premium: float
    target_premium: float
    underlying_price: float
    reason: str
    strength: float  # 0-1
    expected_rr: float


class MomentumBreakoutBuy:
    """
    Strategy: Buy options on strong momentum breakouts
    
    Logic:
    - Buy CE when price breaks above resistance with volume
    - Buy PE when price breaks below support with volume
    
    Best for: Strong trending days, news-driven moves
    Risk: False breakouts
    """
    
    def __init__(self, features_df: pd.DataFrame, options_data: Dict = None,
                 config: Dict = None):
        self.df = features_df.copy()
        self.options = options_data or {}
        self.config = config or self._default_config()
        self.signals: List[OptionBuySignal] = []
    
    def _default_config(self) -> Dict:
        return {
            'breakout_atr_multiplier': 0.5,  # Price move > 0.5x ATR (relaxed)
            'volume_surge_threshold': 0.8,   # Volume > 0.8x average (relaxed)
            'min_rsi_for_ce': 50,            # RSI above this for CE (relaxed)
            'max_rsi_for_pe': 50,            # RSI below this for PE (relaxed)
            'stop_loss_pct': 30,             # SL at 30% of premium
            'target_pct': 100,               # Target at 100% gain
            'otm_strikes': 1,                # How many strikes OTM
        }
    
    def generate_signals(self) -> List[OptionBuySignal]:
        """Generate breakout buy signals"""
        if 'atr' not in self.df.columns:
            return []
        
        self.df['price_change'] = self.df['close'].diff()
        self.df['change_vs_atr'] = abs(self.df['price_change']) / self.df['atr']
        
        for idx, row in self.df.iterrows():
            if pd.isna(row.get('change_vs_atr')) or pd.isna(row.get('volume_ratio')):
                continue
            
            # Check for strong move with volume
            is_strong_move = row['change_vs_atr'] >= self.config['breakout_atr_multiplier']
            has_volume = row.get('volume_ratio', 0) >= self.config['volume_surge_threshold']
            
            if not (is_strong_move and has_volume):
                continue
            
            # Determine direction
            if row['price_change'] > 0 and row.get('rsi', 50) >= self.config['min_rsi_for_ce']:
                option_type = OptionType.CE
                reason = f"Bullish breakout: {row['change_vs_atr']:.1f}x ATR with {row['volume_ratio']:.1f}x volume"
            elif row['price_change'] < 0 and row.get('rsi', 50) <= self.config['max_rsi_for_pe']:
                option_type = OptionType.PE
                reason = f"Bearish breakdown: {row['change_vs_atr']:.1f}x ATR with {row['volume_ratio']:.1f}x volume"
            else:
                continue
            
            # Calculate strike (OTM)
            spot = row['close']
            strike = self._get_strike(spot, option_type)
            
            # Estimate premium (simplified)
            entry_premium = self._estimate_premium(spot, strike, option_type)
            stop_loss = entry_premium * (1 - self.config['stop_loss_pct'] / 100)
            target = entry_premium * (1 + self.config['target_pct'] / 100)
            
            signal = OptionBuySignal(
                timestamp=idx,
                option_type=option_type,
                strike=strike,
                entry_premium=entry_premium,
                stop_loss_premium=stop_loss,
                target_premium=target,
                underlying_price=spot,
                reason=reason,
                strength=min(row['change_vs_atr'] / 2, 1.0),
                expected_rr=self.config['target_pct'] / self.config['stop_loss_pct']
            )
            self.signals.append(signal)
        
        return self.signals
    
    def _get_strike(self, spot: float, option_type: OptionType) -> int:
        """Get OTM strike"""
        strike_gap = 50  # NIFTY strike gap
        atm = round(spot / strike_gap) * strike_gap
        
        if option_type == OptionType.CE:
            return int(atm + strike_gap * self.config['otm_strikes'])
        else:
            return int(atm - strike_gap * self.config['otm_strikes'])
    
    def _estimate_premium(self, spot: float, strike: int, option_type: OptionType) -> float:
        """Rough premium estimate (use real data in production)"""
        intrinsic = max(0, spot - strike) if option_type == OptionType.CE else max(0, strike - spot)
        time_value = abs(spot - strike) * 0.02  # Simplified
        return max(intrinsic + time_value, 5.0)
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert signals to DataFrame"""
        if not self.signals:
            return pd.DataFrame()
        
        return pd.DataFrame([
            {
                'timestamp': s.timestamp,
                'option_type': s.option_type.value,
                'strike': s.strike,
                'entry_premium': s.entry_premium,
                'stop_loss': s.stop_loss_premium,
                'target': s.target_premium,
                'spot': s.underlying_price,
                'reason': s.reason,
                'strength': s.strength,
                'rr': s.expected_rr,
            }
            for s in self.signals
        ])


class TrendFollowingBuy:
    """
    Strategy: Buy options in direction of trend on pullbacks
    
    Logic:
    - In uptrend: Buy CE on RSI pullback to 40-50
    - In downtrend: Buy PE on RSI bounce to 50-60
    
    Best for: Trending markets with healthy corrections
    """
    
    def __init__(self, features_df: pd.DataFrame, config: Dict = None):
        self.df = features_df.copy()
        self.config = config or self._default_config()
        self.signals: List[OptionBuySignal] = []
    
    def _default_config(self) -> Dict:
        return {
            'trend_ema_fast': 9,
            'trend_ema_slow': 20,
            'rsi_pullback_low': 35,            # Relaxed
            'rsi_pullback_high': 55,           # Relaxed
            'rsi_bounce_low': 45,              # Relaxed
            'rsi_bounce_high': 65,             # Relaxed
            'stop_loss_pct': 40,
            'target_pct': 80,
            'otm_strikes': 0,  # ATM for trend following
        }
    
    def generate_signals(self) -> List[OptionBuySignal]:
        """Generate trend following signals"""
        fast_col = f"ema_{self.config['trend_ema_fast']}"
        slow_col = f"ema_{self.config['trend_ema_slow']}"
        
        if fast_col not in self.df.columns or slow_col not in self.df.columns:
            return []
        
        for idx, row in self.df.iterrows():
            rsi = row.get('rsi', 50)
            is_uptrend = row.get(fast_col, 0) > row.get(slow_col, 0)
            is_downtrend = row.get(fast_col, 0) < row.get(slow_col, 0)
            
            # Uptrend + RSI pullback = Buy CE
            if is_uptrend and self.config['rsi_pullback_low'] <= rsi <= self.config['rsi_pullback_high']:
                option_type = OptionType.CE
                reason = f"Uptrend pullback: EMA{self.config['trend_ema_fast']} > EMA{self.config['trend_ema_slow']}, RSI={rsi:.0f}"
            # Downtrend + RSI bounce = Buy PE
            elif is_downtrend and self.config['rsi_bounce_low'] <= rsi <= self.config['rsi_bounce_high']:
                option_type = OptionType.PE
                reason = f"Downtrend bounce: EMA{self.config['trend_ema_fast']} < EMA{self.config['trend_ema_slow']}, RSI={rsi:.0f}"
            else:
                continue
            
            spot = row['close']
            strike = self._get_strike(spot, option_type)
            entry_premium = self._estimate_premium(spot, strike, option_type)
            
            signal = OptionBuySignal(
                timestamp=idx,
                option_type=option_type,
                strike=strike,
                entry_premium=entry_premium,
                stop_loss_premium=entry_premium * (1 - self.config['stop_loss_pct'] / 100),
                target_premium=entry_premium * (1 + self.config['target_pct'] / 100),
                underlying_price=spot,
                reason=reason,
                strength=abs(rsi - 50) / 50,
                expected_rr=self.config['target_pct'] / self.config['stop_loss_pct']
            )
            self.signals.append(signal)
        
        return self.signals
    
    def _get_strike(self, spot: float, option_type: OptionType) -> int:
        strike_gap = 50
        atm = round(spot / strike_gap) * strike_gap
        return int(atm + strike_gap * self.config['otm_strikes'] * (1 if option_type == OptionType.CE else -1))
    
    def _estimate_premium(self, spot: float, strike: int, option_type: OptionType) -> float:
        intrinsic = max(0, spot - strike) if option_type == OptionType.CE else max(0, strike - spot)
        time_value = abs(spot - strike) * 0.025
        return max(intrinsic + time_value, 10.0)
    
    def to_dataframe(self) -> pd.DataFrame:
        if not self.signals:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                'timestamp': s.timestamp,
                'option_type': s.option_type.value,
                'strike': s.strike,
                'entry_premium': s.entry_premium,
                'stop_loss': s.stop_loss_premium,
                'target': s.target_premium,
                'spot': s.underlying_price,
                'reason': s.reason,
                'rr': s.expected_rr,
            }
            for s in self.signals
        ])


class ORBOptionBuy:
    """
    Strategy: Opening Range Breakout Option Buy
    
    Logic:
    - Define opening range (first 15-30 mins)
    - Buy CE on breakout above range high
    - Buy PE on breakdown below range low
    
    Best for: Trending days, gap days
    """
    
    def __init__(self, features_df: pd.DataFrame, config: Dict = None):
        self.df = features_df.copy()
        self.config = config or self._default_config()
        self.signals: List[OptionBuySignal] = []
    
    def _default_config(self) -> Dict:
        return {
            'orb_minutes': 15,           # First 15 minutes
            'min_range_atr': 0.2,        # Min range as ATR multiple (relaxed)
            'max_range_atr': 3.0,        # Max range as ATR multiple (relaxed)
            'stop_loss_pct': 35,
            'target_pct': 70,
            'entry_buffer_pct': 0.05,    # Enter 0.05% beyond range (relaxed)
        }
    
    def generate_signals(self) -> List[OptionBuySignal]:
        """Generate ORB signals"""
        if self.df.empty:
            return []
        
        # Get opening range
        orb_df = self.df.head(self.config['orb_minutes'])
        if len(orb_df) < self.config['orb_minutes']:
            return []
        
        range_high = orb_df['high'].max()
        range_low = orb_df['low'].min()
        range_size = range_high - range_low
        
        # Get ATR for validation
        avg_atr = self.df['atr'].mean() if 'atr' in self.df.columns else range_size
        
        # Validate range size
        if not (self.config['min_range_atr'] * avg_atr <= range_size <= self.config['max_range_atr'] * avg_atr):
            return []
        
        # Look for breakouts after ORB period
        post_orb = self.df.iloc[self.config['orb_minutes']:]
        breakout_triggered = False
        
        for idx, row in post_orb.iterrows():
            if breakout_triggered:
                break  # Only take first breakout of the day
            
            buffer = row['close'] * (self.config['entry_buffer_pct'] / 100)
            
            # Bullish breakout
            if row['close'] > range_high + buffer:
                option_type = OptionType.CE
                reason = f"ORB Bullish breakout: Close {row['close']:.0f} > Range High {range_high:.0f}"
                breakout_triggered = True
            # Bearish breakdown
            elif row['close'] < range_low - buffer:
                option_type = OptionType.PE
                reason = f"ORB Bearish breakdown: Close {row['close']:.0f} < Range Low {range_low:.0f}"
                breakout_triggered = True
            else:
                continue
            
            spot = row['close']
            strike_gap = 50
            strike = round(spot / strike_gap) * strike_gap
            entry_premium = self._estimate_premium(spot, strike, option_type)
            
            signal = OptionBuySignal(
                timestamp=idx,
                option_type=option_type,
                strike=int(strike),
                entry_premium=entry_premium,
                stop_loss_premium=entry_premium * (1 - self.config['stop_loss_pct'] / 100),
                target_premium=entry_premium * (1 + self.config['target_pct'] / 100),
                underlying_price=spot,
                reason=reason,
                strength=min(range_size / avg_atr, 1.0) if avg_atr > 0 else 0.5,
                expected_rr=self.config['target_pct'] / self.config['stop_loss_pct']
            )
            self.signals.append(signal)
        
        return self.signals
    
    def _estimate_premium(self, spot: float, strike: int, option_type: OptionType) -> float:
        intrinsic = max(0, spot - strike) if option_type == OptionType.CE else max(0, strike - spot)
        return max(intrinsic + 20, 15.0)  # ATM premium estimate
    
    def to_dataframe(self) -> pd.DataFrame:
        if not self.signals:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                'timestamp': s.timestamp,
                'option_type': s.option_type.value,
                'strike': s.strike,
                'entry_premium': s.entry_premium,
                'stop_loss': s.stop_loss_premium,
                'target': s.target_premium,
                'spot': s.underlying_price,
                'reason': s.reason,
                'rr': s.expected_rr,
            }
            for s in self.signals
        ])
