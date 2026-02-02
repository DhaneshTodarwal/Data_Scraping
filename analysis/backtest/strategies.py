"""
All Option Selling Strategies
==============================
Complete collection of option selling strategies for backtesting
"""
import pandas as pd
import numpy as np
from typing import Dict, Optional
from dataclasses import dataclass


class BaseStrategy:
    """Base class for all strategies"""
    
    def __init__(self, name: str, config: Dict = None):
        self.name = name
        self.config = config or {}
    
    def get_entry_signal(self, spot_price: float, strikes_data: Dict,
                         timestamp: pd.Timestamp) -> Optional[Dict]:
        raise NotImplementedError
    
    def get_exit_signal(self, trade: Dict, current_pnl_pct: float,
                        timestamp: pd.Timestamp) -> Optional[str]:
        raise NotImplementedError
    
    def _get_strike_gap(self, spot: float) -> int:
        """Determine strike gap based on spot price"""
        if spot < 10000:
            return 25
        elif spot < 25000:
            return 50
        elif spot < 50000:
            return 100
        else:
            return 100
    
    def _get_atm(self, spot: float) -> int:
        """Get ATM strike"""
        gap = self._get_strike_gap(spot)
        return int(round(spot / gap) * gap)


# ============== CORE OPTION SELLING STRATEGIES ==============

class ShortStraddleStrategy(BaseStrategy):
    """
    Short Straddle: Sell ATM CE + Sell ATM PE
    Max profit when spot stays at ATM
    Risk: Unlimited on both sides
    """
    
    def __init__(self, entry_time: str = '09:45', sl_pct: float = 30, 
                 target_pct: float = 50, exit_time: str = '15:20'):
        super().__init__("Short Straddle", {
            'entry_time': entry_time,
            'stoploss_pct': sl_pct,
            'target_pct': target_pct,
            'exit_time': exit_time,
        })
    
    def get_entry_signal(self, spot_price: float, strikes_data: Dict,
                         timestamp: pd.Timestamp) -> Optional[Dict]:
        time_str = timestamp.strftime('%H:%M')
        if time_str != self.config['entry_time']:
            return None
        
        atm = self._get_atm(spot_price)
        
        if atm in strikes_data.get('CE', {}) and atm in strikes_data.get('PE', {}):
            return {
                'type': 'STRADDLE',
                'strike': atm,
                'direction': 'SELL',
            }
        return None
    
    def get_exit_signal(self, trade: Dict, current_pnl_pct: float,
                        timestamp: pd.Timestamp) -> Optional[str]:
        time_str = timestamp.strftime('%H:%M')
        
        if time_str >= self.config['exit_time']:
            return 'time'
        if current_pnl_pct <= -self.config['stoploss_pct']:
            return 'stoploss'
        if current_pnl_pct >= self.config['target_pct']:
            return 'target'
        return None


class ShortStrangleStrategy(BaseStrategy):
    """
    Short Strangle: Sell OTM CE + Sell OTM PE
    Wider profit zone than straddle
    Risk: Unlimited on both sides
    """
    
    def __init__(self, entry_time: str = '09:45', otm_distance: int = 2,
                 sl_pct: float = 40, target_pct: float = 40, exit_time: str = '15:20'):
        super().__init__("Short Strangle", {
            'entry_time': entry_time,
            'otm_distance': otm_distance,
            'stoploss_pct': sl_pct,
            'target_pct': target_pct,
            'exit_time': exit_time,
        })
    
    def get_entry_signal(self, spot_price: float, strikes_data: Dict,
                         timestamp: pd.Timestamp) -> Optional[Dict]:
        time_str = timestamp.strftime('%H:%M')
        if time_str != self.config['entry_time']:
            return None
        
        gap = self._get_strike_gap(spot_price)
        atm = self._get_atm(spot_price)
        
        ce_strike = atm + gap * self.config['otm_distance']
        pe_strike = atm - gap * self.config['otm_distance']
        
        if ce_strike in strikes_data.get('CE', {}) and pe_strike in strikes_data.get('PE', {}):
            return {
                'type': 'STRANGLE',
                'ce_strike': int(ce_strike),
                'pe_strike': int(pe_strike),
                'direction': 'SELL',
            }
        return None
    
    def get_exit_signal(self, trade: Dict, current_pnl_pct: float,
                        timestamp: pd.Timestamp) -> Optional[str]:
        time_str = timestamp.strftime('%H:%M')
        
        if time_str >= self.config['exit_time']:
            return 'time'
        if current_pnl_pct <= -self.config['stoploss_pct']:
            return 'stoploss'
        if current_pnl_pct >= self.config['target_pct']:
            return 'target'
        return None


class IronCondorStrategy(BaseStrategy):
    """
    Iron Condor: Limited risk version of strangle
    Sell OTM CE + Buy further OTM CE + Sell OTM PE + Buy further OTM PE
    Max profit: Net premium received
    Max loss: Width of spread - Premium
    """
    
    def __init__(self, entry_time: str = '09:45', short_distance: int = 2,
                 long_distance: int = 4, sl_pct: float = 50, target_pct: float = 50,
                 exit_time: str = '15:20'):
        super().__init__("Iron Condor", {
            'entry_time': entry_time,
            'short_distance': short_distance,
            'long_distance': long_distance,
            'stoploss_pct': sl_pct,
            'target_pct': target_pct,
            'exit_time': exit_time,
        })
    
    def get_entry_signal(self, spot_price: float, strikes_data: Dict,
                         timestamp: pd.Timestamp) -> Optional[Dict]:
        time_str = timestamp.strftime('%H:%M')
        if time_str != self.config['entry_time']:
            return None
        
        gap = self._get_strike_gap(spot_price)
        atm = self._get_atm(spot_price)
        
        short_ce = atm + gap * self.config['short_distance']
        long_ce = atm + gap * self.config['long_distance']
        short_pe = atm - gap * self.config['short_distance']
        long_pe = atm - gap * self.config['long_distance']
        
        # Check all strikes available
        ce_ok = short_ce in strikes_data.get('CE', {}) and long_ce in strikes_data.get('CE', {})
        pe_ok = short_pe in strikes_data.get('PE', {}) and long_pe in strikes_data.get('PE', {})
        
        if ce_ok and pe_ok:
            return {
                'type': 'IRON_CONDOR',
                'short_ce': int(short_ce),
                'long_ce': int(long_ce),
                'short_pe': int(short_pe),
                'long_pe': int(long_pe),
                'direction': 'SELL',
            }
        return None
    
    def get_exit_signal(self, trade: Dict, current_pnl_pct: float,
                        timestamp: pd.Timestamp) -> Optional[str]:
        time_str = timestamp.strftime('%H:%M')
        
        if time_str >= self.config['exit_time']:
            return 'time'
        if current_pnl_pct <= -self.config['stoploss_pct']:
            return 'stoploss'
        if current_pnl_pct >= self.config['target_pct']:
            return 'target'
        return None


class IronButterflyStrategy(BaseStrategy):
    """
    Iron Butterfly: Sell ATM Straddle + Buy OTM Wings
    Sell ATM CE + Sell ATM PE + Buy OTM CE + Buy OTM PE
    Limited risk version of straddle
    """
    
    def __init__(self, entry_time: str = '09:45', wing_distance: int = 3,
                 sl_pct: float = 40, target_pct: float = 50, exit_time: str = '15:20'):
        super().__init__("Iron Butterfly", {
            'entry_time': entry_time,
            'wing_distance': wing_distance,
            'stoploss_pct': sl_pct,
            'target_pct': target_pct,
            'exit_time': exit_time,
        })
    
    def get_entry_signal(self, spot_price: float, strikes_data: Dict,
                         timestamp: pd.Timestamp) -> Optional[Dict]:
        time_str = timestamp.strftime('%H:%M')
        if time_str != self.config['entry_time']:
            return None
        
        gap = self._get_strike_gap(spot_price)
        atm = self._get_atm(spot_price)
        
        wing_ce = atm + gap * self.config['wing_distance']
        wing_pe = atm - gap * self.config['wing_distance']
        
        # Check all strikes
        atm_ok = atm in strikes_data.get('CE', {}) and atm in strikes_data.get('PE', {})
        wings_ok = wing_ce in strikes_data.get('CE', {}) and wing_pe in strikes_data.get('PE', {})
        
        if atm_ok and wings_ok:
            return {
                'type': 'IRON_BUTTERFLY',
                'atm_strike': int(atm),
                'wing_ce': int(wing_ce),
                'wing_pe': int(wing_pe),
                'direction': 'SELL',
            }
        return None
    
    def get_exit_signal(self, trade: Dict, current_pnl_pct: float,
                        timestamp: pd.Timestamp) -> Optional[str]:
        time_str = timestamp.strftime('%H:%M')
        
        if time_str >= self.config['exit_time']:
            return 'time'
        if current_pnl_pct <= -self.config['stoploss_pct']:
            return 'stoploss'
        if current_pnl_pct >= self.config['target_pct']:
            return 'target'
        return None


class BullPutSpreadStrategy(BaseStrategy):
    """
    Bull Put Spread (Credit Put Spread): Bullish bias
    Sell OTM PE + Buy further OTM PE
    Profit if spot stays above short strike
    """
    
    def __init__(self, entry_time: str = '09:45', short_distance: int = 2,
                 spread_width: int = 2, sl_pct: float = 50, target_pct: float = 50,
                 exit_time: str = '15:20'):
        super().__init__("Bull Put Spread", {
            'entry_time': entry_time,
            'short_distance': short_distance,
            'spread_width': spread_width,
            'stoploss_pct': sl_pct,
            'target_pct': target_pct,
            'exit_time': exit_time,
        })
    
    def get_entry_signal(self, spot_price: float, strikes_data: Dict,
                         timestamp: pd.Timestamp) -> Optional[Dict]:
        time_str = timestamp.strftime('%H:%M')
        if time_str != self.config['entry_time']:
            return None
        
        gap = self._get_strike_gap(spot_price)
        atm = self._get_atm(spot_price)
        
        short_pe = atm - gap * self.config['short_distance']
        long_pe = short_pe - gap * self.config['spread_width']
        
        if short_pe in strikes_data.get('PE', {}) and long_pe in strikes_data.get('PE', {}):
            return {
                'type': 'BULL_PUT_SPREAD',
                'short_pe': int(short_pe),
                'long_pe': int(long_pe),
                'direction': 'SELL',
            }
        return None
    
    def get_exit_signal(self, trade: Dict, current_pnl_pct: float,
                        timestamp: pd.Timestamp) -> Optional[str]:
        time_str = timestamp.strftime('%H:%M')
        
        if time_str >= self.config['exit_time']:
            return 'time'
        if current_pnl_pct <= -self.config['stoploss_pct']:
            return 'stoploss'
        if current_pnl_pct >= self.config['target_pct']:
            return 'target'
        return None


class BearCallSpreadStrategy(BaseStrategy):
    """
    Bear Call Spread (Credit Call Spread): Bearish bias
    Sell OTM CE + Buy further OTM CE
    Profit if spot stays below short strike
    """
    
    def __init__(self, entry_time: str = '09:45', short_distance: int = 2,
                 spread_width: int = 2, sl_pct: float = 50, target_pct: float = 50,
                 exit_time: str = '15:20'):
        super().__init__("Bear Call Spread", {
            'entry_time': entry_time,
            'short_distance': short_distance,
            'spread_width': spread_width,
            'stoploss_pct': sl_pct,
            'target_pct': target_pct,
            'exit_time': exit_time,
        })
    
    def get_entry_signal(self, spot_price: float, strikes_data: Dict,
                         timestamp: pd.Timestamp) -> Optional[Dict]:
        time_str = timestamp.strftime('%H:%M')
        if time_str != self.config['entry_time']:
            return None
        
        gap = self._get_strike_gap(spot_price)
        atm = self._get_atm(spot_price)
        
        short_ce = atm + gap * self.config['short_distance']
        long_ce = short_ce + gap * self.config['spread_width']
        
        if short_ce in strikes_data.get('CE', {}) and long_ce in strikes_data.get('CE', {}):
            return {
                'type': 'BEAR_CALL_SPREAD',
                'short_ce': int(short_ce),
                'long_ce': int(long_ce),
                'direction': 'SELL',
            }
        return None
    
    def get_exit_signal(self, trade: Dict, current_pnl_pct: float,
                        timestamp: pd.Timestamp) -> Optional[str]:
        time_str = timestamp.strftime('%H:%M')
        
        if time_str >= self.config['exit_time']:
            return 'time'
        if current_pnl_pct <= -self.config['stoploss_pct']:
            return 'stoploss'
        if current_pnl_pct >= self.config['target_pct']:
            return 'target'
        return None


# ============== STRATEGY VARIANTS ==============

class Morning930StraddleStrategy(ShortStraddleStrategy):
    """Short Straddle at 9:30 AM - Capture early volatility crush"""
    def __init__(self):
        super().__init__(entry_time='09:30', sl_pct=25, target_pct=40, exit_time='15:20')
        self.name = "9:30 Straddle"


class Morning1015StraddleStrategy(ShortStraddleStrategy):
    """Short Straddle at 10:15 AM - After initial volatility settles"""
    def __init__(self):
        super().__init__(entry_time='10:15', sl_pct=25, target_pct=40, exit_time='15:20')
        self.name = "10:15 Straddle"


class WideStrangleStrategy(ShortStrangleStrategy):
    """Short Strangle 3 strikes OTM - Higher probability"""
    def __init__(self):
        super().__init__(entry_time='09:45', otm_distance=3, sl_pct=50, target_pct=35, exit_time='15:20')
        self.name = "Wide Strangle (3 OTM)"


class NarrowIronCondorStrategy(IronCondorStrategy):
    """Iron Condor with narrow wings - Higher premium, lower probability"""
    def __init__(self):
        super().__init__(entry_time='09:45', short_distance=1, long_distance=3, 
                        sl_pct=40, target_pct=50, exit_time='15:20')
        self.name = "Narrow Iron Condor"


# ============== STRATEGY REGISTRY ==============

ALL_STRATEGIES = {
    # Core strategies
    'short_straddle': ShortStraddleStrategy(),
    'short_strangle': ShortStrangleStrategy(),
    'iron_condor': IronCondorStrategy(),
    'iron_butterfly': IronButterflyStrategy(),
    'bull_put_spread': BullPutSpreadStrategy(),
    'bear_call_spread': BearCallSpreadStrategy(),
    
    # Variants
    '930_straddle': Morning930StraddleStrategy(),
    '1015_straddle': Morning1015StraddleStrategy(),
    'wide_strangle': WideStrangleStrategy(),
    'narrow_iron_condor': NarrowIronCondorStrategy(),
}


def get_strategy(name: str) -> BaseStrategy:
    """Get strategy by name"""
    if name not in ALL_STRATEGIES:
        available = list(ALL_STRATEGIES.keys())
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")
    return ALL_STRATEGIES[name]


def list_strategies() -> list:
    """List all available strategies"""
    return [(name, strategy.name) for name, strategy in ALL_STRATEGIES.items()]
