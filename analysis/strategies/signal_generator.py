"""
Signal Generator
Converts features into actionable trading signals with filters
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import SIGNALS_OUTPUT, MARKET_OPEN, MARKET_CLOSE, FIRST_30_MIN_END, LAST_30_MIN_START


class SignalType(Enum):
    LONG = 1
    SHORT = -1
    NEUTRAL = 0


@dataclass
class Signal:
    """Represents a trading signal"""
    timestamp: pd.Timestamp
    signal_type: SignalType
    strength: float  # 0 to 1
    entry_price: float
    stop_loss: float
    target: float
    risk_reward: float
    reason: str
    filters_passed: Dict[str, bool]


class TradeFilter:
    """Collection of filters to validate trade setups"""
    
    @staticmethod
    def time_filter(timestamp: pd.Timestamp) -> bool:
        """
        Avoid first 30 mins and last 30 mins
        These are high volatility, low predictability periods
        """
        time_str = timestamp.strftime('%H:%M')
        return FIRST_30_MIN_END <= time_str <= LAST_30_MIN_START
    
    @staticmethod
    def trend_filter(features: pd.Series, direction: SignalType) -> bool:
        """
        Only trade with the trend
        Long only in uptrend, Short only in downtrend
        """
        if 'trend' not in features:
            return True
        
        if direction == SignalType.LONG:
            return features['trend'] >= 0
        elif direction == SignalType.SHORT:
            return features['trend'] <= 0
        return True
    
    @staticmethod
    def volatility_filter(features: pd.Series, min_atr: float = 0.2, max_atr: float = 1.5) -> bool:
        """
        Filter based on ATR percentage
        Too low = no movement, Too high = unpredictable
        """
        if 'atr_pct' not in features:
            return True
        return min_atr <= features['atr_pct'] <= max_atr
    
    @staticmethod
    def rsi_extreme_filter(features: pd.Series) -> bool:
        """
        Avoid trading at extreme RSI levels (mean reversion expected)
        """
        if 'rsi' not in features:
            return True
        return 25 <= features['rsi'] <= 75
    
    @staticmethod
    def volume_filter(features: pd.Series, min_ratio: float = 0.5) -> bool:
        """
        Require minimum volume relative to average
        Low volume = unreliable moves
        """
        if 'volume_ratio' not in features:
            return True
        return features['volume_ratio'] >= min_ratio


class SignalGenerator:
    """Generate trading signals with risk management"""
    
    def __init__(self, features_df: pd.DataFrame, config: Dict = None):
        """
        Initialize with features dataframe
        Expected: DataFrame with technical indicators
        """
        self.df = features_df.copy()
        self.config = config or self._default_config()
        self.signals: List[Signal] = []
    
    def _default_config(self) -> Dict:
        return {
            'min_rr_ratio': 2.0,
            'atr_stop_multiplier': 1.5,
            'atr_target_multiplier': 3.0,
            'use_time_filter': True,
            'use_trend_filter': True,
            'use_volatility_filter': True,
            'use_rsi_filter': True,
            'use_volume_filter': True,
        }
    
    def _apply_filters(self, row: pd.Series, direction: SignalType) -> Dict[str, bool]:
        """Apply all configured filters"""
        filters = {}
        
        if self.config['use_time_filter']:
            filters['time'] = TradeFilter.time_filter(row.name)
        
        if self.config['use_trend_filter']:
            filters['trend'] = TradeFilter.trend_filter(row, direction)
        
        if self.config['use_volatility_filter']:
            filters['volatility'] = TradeFilter.volatility_filter(row)
        
        if self.config['use_rsi_filter']:
            filters['rsi'] = TradeFilter.rsi_extreme_filter(row)
        
        if self.config['use_volume_filter']:
            filters['volume'] = TradeFilter.volume_filter(row)
        
        return filters
    
    def _calculate_levels(self, row: pd.Series, direction: SignalType) -> tuple:
        """Calculate stop loss and target based on ATR"""
        entry = row['close']
        atr = row.get('atr', entry * 0.01)  # Fallback to 1% if no ATR
        
        stop_distance = atr * self.config['atr_stop_multiplier']
        target_distance = atr * self.config['atr_target_multiplier']
        
        if direction == SignalType.LONG:
            stop_loss = entry - stop_distance
            target = entry + target_distance
        else:
            stop_loss = entry + stop_distance
            target = entry - target_distance
        
        rr_ratio = target_distance / stop_distance if stop_distance > 0 else 0
        
        return stop_loss, target, rr_ratio
    
    # ============== SIGNAL STRATEGIES ==============
    
    def ema_crossover_signal(self, fast: int = 9, slow: int = 21) -> 'SignalGenerator':
        """
        EMA Crossover Strategy
        Long: Fast EMA crosses above Slow EMA
        Short: Fast EMA crosses below Slow EMA
        """
        fast_col = f'ema_{fast}'
        slow_col = f'ema_{slow}'
        
        if fast_col not in self.df.columns or slow_col not in self.df.columns:
            return self
        
        self.df['ema_diff'] = self.df[fast_col] - self.df[slow_col]
        self.df['ema_diff_prev'] = self.df['ema_diff'].shift(1)
        
        for idx, row in self.df.iterrows():
            if pd.isna(row.get('ema_diff_prev')):
                continue
            
            # Bullish crossover
            if row['ema_diff'] > 0 and row['ema_diff_prev'] <= 0:
                direction = SignalType.LONG
                reason = f"EMA {fast}/{slow} bullish crossover"
            # Bearish crossover
            elif row['ema_diff'] < 0 and row['ema_diff_prev'] >= 0:
                direction = SignalType.SHORT
                reason = f"EMA {fast}/{slow} bearish crossover"
            else:
                continue
            
            # Apply filters
            filters = self._apply_filters(row, direction)
            if not all(filters.values()):
                continue
            
            # Calculate levels
            stop_loss, target, rr_ratio = self._calculate_levels(row, direction)
            
            # Check R:R requirement
            if rr_ratio < self.config['min_rr_ratio']:
                continue
            
            signal = Signal(
                timestamp=idx,
                signal_type=direction,
                strength=min(abs(row['ema_diff']) / row['atr'], 1.0) if 'atr' in row else 0.5,
                entry_price=row['close'],
                stop_loss=stop_loss,
                target=target,
                risk_reward=rr_ratio,
                reason=reason,
                filters_passed=filters
            )
            self.signals.append(signal)
        
        return self
    
    def rsi_reversal_signal(self, oversold: int = 30, overbought: int = 70) -> 'SignalGenerator':
        """
        RSI Reversal Strategy
        Long: RSI crosses above oversold level
        Short: RSI crosses below overbought level
        """
        if 'rsi' not in self.df.columns:
            return self
        
        self.df['rsi_prev'] = self.df['rsi'].shift(1)
        
        for idx, row in self.df.iterrows():
            if pd.isna(row.get('rsi_prev')):
                continue
            
            # Bullish reversal from oversold
            if row['rsi'] > oversold and row['rsi_prev'] <= oversold:
                direction = SignalType.LONG
                reason = f"RSI crossed above {oversold} (oversold recovery)"
            # Bearish reversal from overbought
            elif row['rsi'] < overbought and row['rsi_prev'] >= overbought:
                direction = SignalType.SHORT
                reason = f"RSI crossed below {overbought} (overbought rejection)"
            else:
                continue
            
            # Apply filters (skip RSI filter for this strategy)
            config_backup = self.config['use_rsi_filter']
            self.config['use_rsi_filter'] = False
            filters = self._apply_filters(row, direction)
            self.config['use_rsi_filter'] = config_backup
            
            if not all(filters.values()):
                continue
            
            stop_loss, target, rr_ratio = self._calculate_levels(row, direction)
            
            if rr_ratio < self.config['min_rr_ratio']:
                continue
            
            signal = Signal(
                timestamp=idx,
                signal_type=direction,
                strength=abs(row['rsi'] - 50) / 50,
                entry_price=row['close'],
                stop_loss=stop_loss,
                target=target,
                risk_reward=rr_ratio,
                reason=reason,
                filters_passed=filters
            )
            self.signals.append(signal)
        
        return self
    
    def bollinger_breakout_signal(self) -> 'SignalGenerator':
        """
        Bollinger Band Breakout Strategy
        Long: Price breaks above upper band with volume
        Short: Price breaks below lower band with volume
        """
        required_cols = ['bb_upper', 'bb_lower', 'volume_ratio']
        if not all(col in self.df.columns for col in required_cols):
            return self
        
        for idx, row in self.df.iterrows():
            volume_surge = row.get('volume_ratio', 0) > 1.5
            
            # Breakout above upper band
            if row['close'] > row['bb_upper'] and volume_surge:
                direction = SignalType.LONG
                reason = "Bollinger Band upper breakout with volume"
            # Breakout below lower band
            elif row['close'] < row['bb_lower'] and volume_surge:
                direction = SignalType.SHORT
                reason = "Bollinger Band lower breakout with volume"
            else:
                continue
            
            filters = self._apply_filters(row, direction)
            if not all(filters.values()):
                continue
            
            stop_loss, target, rr_ratio = self._calculate_levels(row, direction)
            
            if rr_ratio < self.config['min_rr_ratio']:
                continue
            
            signal = Signal(
                timestamp=idx,
                signal_type=direction,
                strength=min(row['volume_ratio'] / 2, 1.0),
                entry_price=row['close'],
                stop_loss=stop_loss,
                target=target,
                risk_reward=rr_ratio,
                reason=reason,
                filters_passed=filters
            )
            self.signals.append(signal)
        
        return self
    
    # ============== OUTPUT ==============
    
    def get_signals(self) -> List[Signal]:
        """Return all generated signals"""
        return self.signals
    
    def to_dataframe(self) -> pd.DataFrame:
        """Convert signals to DataFrame"""
        if not self.signals:
            return pd.DataFrame()
        
        return pd.DataFrame([
            {
                'timestamp': s.timestamp,
                'direction': s.signal_type.name,
                'strength': s.strength,
                'entry': s.entry_price,
                'stop_loss': s.stop_loss,
                'target': s.target,
                'rr_ratio': s.risk_reward,
                'reason': s.reason,
            }
            for s in self.signals
        ])
    
    def save_signals(self, filename: str):
        """Save signals to output directory"""
        df = self.to_dataframe()
        if not df.empty:
            output_path = SIGNALS_OUTPUT / filename
            df.to_csv(output_path, index=False)


if __name__ == "__main__":
    # Example usage with sample data
    from features.technical import process_date
    
    try:
        # Load features
        features_df = process_date('NIFTY', '2026-01-16')
        
        # Generate signals
        generator = SignalGenerator(features_df)
        generator.ema_crossover_signal(9, 21)
        generator.rsi_reversal_signal()
        generator.bollinger_breakout_signal()
        
        # Get results
        signals_df = generator.to_dataframe()
        print(f"Generated {len(signals_df)} signals")
        print(signals_df)
        
        # Save
        generator.save_signals('NIFTY_2026-01-16_signals.csv')
        
    except Exception as e:
        print(f"Error: {e}")
