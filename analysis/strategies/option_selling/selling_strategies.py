"""
Option Selling Strategies
============================
These strategies are designed for SELLING options (CE/PE)

Key Characteristics:
- Limited profit (max = premium received)
- Unlimited/high risk potential
- Time decay works FOR you
- Require range-bound or slow-moving markets
- Higher win rate, lower reward-to-risk

IMPORTANT: Option selling requires significant capital for margin
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


class StrategyType(Enum):
    NAKED = "naked"
    STRADDLE = "straddle"
    STRANGLE = "strangle"
    IRON_CONDOR = "iron_condor"
    CREDIT_SPREAD = "credit_spread"


@dataclass
class OptionSellSignal:
    """Signal for option selling strategy"""
    timestamp: pd.Timestamp
    strategy_type: StrategyType
    legs: List[Dict]  # Each leg: {type, strike, action, premium}
    max_profit: float
    max_loss: float
    breakeven_points: List[float]
    underlying_price: float
    reason: str
    probability_of_profit: float  # Estimated PoP
    iv_percentile: float


class ShortStraddleSell:
    """
    Strategy: Sell ATM Straddle
    
    Logic:
    - Sell ATM CE + Sell ATM PE
    - Profit if price stays near ATM
    - Loss if big move in either direction
    
    Best for: Range-bound days, after big moves, low IV expansion expected
    Risk: Unlimited on both sides
    """
    
    def __init__(self, features_df: pd.DataFrame, options_features_df: pd.DataFrame = None,
                 config: Dict = None):
        self.df = features_df.copy()
        self.options_df = options_features_df
        self.config = config or self._default_config()
        self.signals: List[OptionSellSignal] = []
    
    def _default_config(self) -> Dict:
        return {
            'min_iv_percentile': 40,       # Only sell when IV is decent
            'max_atr_percent': 0.8,        # Low volatility day
            'avoid_first_mins': 30,        # Skip first 30 mins
            'avoid_last_mins': 60,         # Skip last 60 mins
            'stop_loss_multiplier': 1.5,   # Exit at 1.5x premium received
            'target_percent': 50,          # Target 50% of premium
        }
    
    def generate_signals(self) -> List[OptionSellSignal]:
        """Generate short straddle signals"""
        if self.df.empty:
            return []
        
        # Skip first N minutes
        start_idx = self.config['avoid_first_mins']
        end_idx = len(self.df) - self.config['avoid_last_mins']
        
        if start_idx >= end_idx:
            return []
        
        analysis_df = self.df.iloc[start_idx:end_idx]
        
        for idx, row in analysis_df.iterrows():
            # Check conditions
            atr_pct = row.get('atr_pct', 1.0)
            
            # Low volatility condition
            if atr_pct > self.config['max_atr_percent']:
                continue
            
            # RSI near 50 (range-bound)
            rsi = row.get('rsi', 50)
            if not (40 <= rsi <= 60):
                continue
            
            # Price near VWAP (fair value)
            vwap = row.get('vwap', row['close'])
            vwap_deviation = abs(row['close'] - vwap) / vwap * 100
            if vwap_deviation > 0.3:  # Within 0.3% of VWAP
                continue
            
            spot = row['close']
            atm_strike = round(spot / 50) * 50
            
            # Estimate premiums
            ce_premium = self._estimate_premium(spot, atm_strike, 'CE')
            pe_premium = self._estimate_premium(spot, atm_strike, 'PE')
            total_premium = ce_premium + pe_premium
            
            legs = [
                {'type': 'CE', 'strike': atm_strike, 'action': 'SELL', 'premium': ce_premium},
                {'type': 'PE', 'strike': atm_strike, 'action': 'SELL', 'premium': pe_premium},
            ]
            
            signal = OptionSellSignal(
                timestamp=idx,
                strategy_type=StrategyType.STRADDLE,
                legs=legs,
                max_profit=total_premium,
                max_loss=float('inf'),  # Unlimited
                breakeven_points=[atm_strike - total_premium, atm_strike + total_premium],
                underlying_price=spot,
                reason=f"Range-bound: RSI={rsi:.0f}, ATR%={atr_pct:.2f}, VWAP dev={vwap_deviation:.2f}%",
                probability_of_profit=0.68,  # ~1 SD
                iv_percentile=50.0  # Placeholder
            )
            self.signals.append(signal)
            break  # Only one signal per day
        
        return self.signals
    
    def _estimate_premium(self, spot: float, strike: int, option_type: str) -> float:
        intrinsic = max(0, spot - strike) if option_type == 'CE' else max(0, strike - spot)
        time_value = 25  # Rough estimate for ATM
        return intrinsic + time_value
    
    def to_dataframe(self) -> pd.DataFrame:
        if not self.signals:
            return pd.DataFrame()
        
        rows = []
        for s in self.signals:
            rows.append({
                'timestamp': s.timestamp,
                'strategy': s.strategy_type.value,
                'spot': s.underlying_price,
                'max_profit': s.max_profit,
                'breakeven_low': s.breakeven_points[0],
                'breakeven_high': s.breakeven_points[1],
                'pop': s.probability_of_profit,
                'reason': s.reason,
                'legs': str(s.legs),
            })
        return pd.DataFrame(rows)


class ShortStrangleSell:
    """
    Strategy: Sell OTM Strangle
    
    Logic:
    - Sell OTM CE + Sell OTM PE
    - Wider profit range than straddle
    - Lower premium but higher PoP
    
    Best for: Range-bound days, mean reversion expected
    """
    
    def __init__(self, features_df: pd.DataFrame, config: Dict = None):
        self.df = features_df.copy()
        self.config = config or self._default_config()
        self.signals: List[OptionSellSignal] = []
    
    def _default_config(self) -> Dict:
        return {
            'otm_strikes': 2,              # 2 strikes OTM
            'min_rsi': 35,                 # Avoid extreme moves
            'max_rsi': 65,
            'max_bb_width': 0.03,          # Bollinger Band width
            'avoid_first_mins': 30,
            'stop_loss_multiplier': 2.0,   # 2x premium
            'target_percent': 40,
        }
    
    def generate_signals(self) -> List[OptionSellSignal]:
        """Generate short strangle signals"""
        if self.df.empty:
            return []
        
        start_idx = self.config['avoid_first_mins']
        
        for idx, row in self.df.iloc[start_idx:].iterrows():
            # RSI in range
            rsi = row.get('rsi', 50)
            if not (self.config['min_rsi'] <= rsi <= self.config['max_rsi']):
                continue
            
            # Low Bollinger Band width (consolidation)
            bb_width = row.get('bb_width', 0.05)
            if bb_width > self.config['max_bb_width']:
                continue
            
            spot = row['close']
            strike_gap = 50
            atm = round(spot / strike_gap) * strike_gap
            
            ce_strike = int(atm + strike_gap * self.config['otm_strikes'])
            pe_strike = int(atm - strike_gap * self.config['otm_strikes'])
            
            ce_premium = self._estimate_otm_premium(spot, ce_strike, 'CE')
            pe_premium = self._estimate_otm_premium(spot, pe_strike, 'PE')
            total_premium = ce_premium + pe_premium
            
            legs = [
                {'type': 'CE', 'strike': ce_strike, 'action': 'SELL', 'premium': ce_premium},
                {'type': 'PE', 'strike': pe_strike, 'action': 'SELL', 'premium': pe_premium},
            ]
            
            signal = OptionSellSignal(
                timestamp=idx,
                strategy_type=StrategyType.STRANGLE,
                legs=legs,
                max_profit=total_premium,
                max_loss=float('inf'),
                breakeven_points=[pe_strike - total_premium, ce_strike + total_premium],
                underlying_price=spot,
                reason=f"Consolidation: RSI={rsi:.0f}, BB Width={bb_width:.3f}",
                probability_of_profit=0.75,  # Higher than straddle
                iv_percentile=50.0
            )
            self.signals.append(signal)
            break
        
        return self.signals
    
    def _estimate_otm_premium(self, spot: float, strike: int, option_type: str) -> float:
        distance = abs(spot - strike)
        # OTM premium decays with distance
        return max(5, 30 - (distance / 50) * 5)
    
    def to_dataframe(self) -> pd.DataFrame:
        if not self.signals:
            return pd.DataFrame()
        
        rows = []
        for s in self.signals:
            rows.append({
                'timestamp': s.timestamp,
                'strategy': s.strategy_type.value,
                'spot': s.underlying_price,
                'max_profit': s.max_profit,
                'breakeven_low': s.breakeven_points[0],
                'breakeven_high': s.breakeven_points[1],
                'pop': s.probability_of_profit,
                'reason': s.reason,
            })
        return pd.DataFrame(rows)


class IronCondorSell:
    """
    Strategy: Iron Condor (defined risk strangle)
    
    Logic:
    - Sell OTM CE + Buy further OTM CE (credit spread)
    - Sell OTM PE + Buy further OTM PE (credit spread)
    - Limited profit AND limited risk
    
    Best for: Range-bound markets, high IV
    """
    
    def __init__(self, features_df: pd.DataFrame, config: Dict = None):
        self.df = features_df.copy()
        self.config = config or self._default_config()
        self.signals: List[OptionSellSignal] = []
    
    def _default_config(self) -> Dict:
        return {
            'short_otm_strikes': 2,        # Short strikes 2 OTM
            'long_otm_strikes': 4,         # Long strikes 4 OTM (wing)
            'min_credit_pct': 30,          # Min credit as % of width
            'max_atr_pct': 0.7,
            'avoid_first_mins': 45,
            'target_percent': 50,          # Close at 50% profit
        }
    
    def generate_signals(self) -> List[OptionSellSignal]:
        """Generate iron condor signals"""
        if self.df.empty:
            return []
        
        start_idx = self.config['avoid_first_mins']
        
        for idx, row in self.df.iloc[start_idx:].iterrows():
            # Low volatility
            atr_pct = row.get('atr_pct', 1.0)
            if atr_pct > self.config['max_atr_pct']:
                continue
            
            # RSI near neutral
            rsi = row.get('rsi', 50)
            if not (40 <= rsi <= 60):
                continue
            
            spot = row['close']
            strike_gap = 50
            atm = round(spot / strike_gap) * strike_gap
            
            # Calculate strikes
            short_ce = int(atm + strike_gap * self.config['short_otm_strikes'])
            long_ce = int(atm + strike_gap * self.config['long_otm_strikes'])
            short_pe = int(atm - strike_gap * self.config['short_otm_strikes'])
            long_pe = int(atm - strike_gap * self.config['long_otm_strikes'])
            
            # Estimate premiums
            short_ce_prem = self._estimate_premium(spot, short_ce, 'CE')
            long_ce_prem = self._estimate_premium(spot, long_ce, 'CE')
            short_pe_prem = self._estimate_premium(spot, short_pe, 'PE')
            long_pe_prem = self._estimate_premium(spot, long_pe, 'PE')
            
            # Net credit
            ce_spread_credit = short_ce_prem - long_ce_prem
            pe_spread_credit = short_pe_prem - long_pe_prem
            total_credit = ce_spread_credit + pe_spread_credit
            
            # Width of spread
            spread_width = (long_ce - short_ce)  # Same as short_pe - long_pe
            
            # Max loss = width - credit
            max_loss = spread_width - total_credit
            
            legs = [
                {'type': 'CE', 'strike': short_ce, 'action': 'SELL', 'premium': short_ce_prem},
                {'type': 'CE', 'strike': long_ce, 'action': 'BUY', 'premium': long_ce_prem},
                {'type': 'PE', 'strike': short_pe, 'action': 'SELL', 'premium': short_pe_prem},
                {'type': 'PE', 'strike': long_pe, 'action': 'BUY', 'premium': long_pe_prem},
            ]
            
            signal = OptionSellSignal(
                timestamp=idx,
                strategy_type=StrategyType.IRON_CONDOR,
                legs=legs,
                max_profit=total_credit,
                max_loss=max_loss,
                breakeven_points=[short_pe - total_credit, short_ce + total_credit],
                underlying_price=spot,
                reason=f"Range-bound IC: RSI={rsi:.0f}, ATR%={atr_pct:.2f}",
                probability_of_profit=0.65,
                iv_percentile=50.0
            )
            self.signals.append(signal)
            break
        
        return self.signals
    
    def _estimate_premium(self, spot: float, strike: int, option_type: str) -> float:
        distance = abs(spot - strike)
        if option_type == 'CE':
            intrinsic = max(0, spot - strike)
        else:
            intrinsic = max(0, strike - spot)
        time_value = max(3, 25 - (distance / 50) * 4)
        return intrinsic + time_value
    
    def to_dataframe(self) -> pd.DataFrame:
        if not self.signals:
            return pd.DataFrame()
        
        rows = []
        for s in self.signals:
            rows.append({
                'timestamp': s.timestamp,
                'strategy': s.strategy_type.value,
                'spot': s.underlying_price,
                'max_profit': s.max_profit,
                'max_loss': s.max_loss,
                'rr': s.max_profit / s.max_loss if s.max_loss > 0 else 0,
                'breakeven_low': s.breakeven_points[0],
                'breakeven_high': s.breakeven_points[1],
                'pop': s.probability_of_profit,
                'reason': s.reason,
            })
        return pd.DataFrame(rows)


class CreditSpreadSell:
    """
    Strategy: Directional Credit Spread
    
    Logic:
    - Bull Put Spread: Sell OTM PE, Buy further OTM PE (bullish)
    - Bear Call Spread: Sell OTM CE, Buy further OTM CE (bearish)
    
    Best for: Mild directional bias with defined risk
    """
    
    def __init__(self, features_df: pd.DataFrame, config: Dict = None):
        self.df = features_df.copy()
        self.config = config or self._default_config()
        self.signals: List[OptionSellSignal] = []
    
    def _default_config(self) -> Dict:
        return {
            'short_otm_strikes': 2,
            'spread_width_strikes': 2,
            'trend_threshold': 0.5,        # Trend strength
            'avoid_first_mins': 30,
        }
    
    def generate_signals(self) -> List[OptionSellSignal]:
        """Generate credit spread signals"""
        if self.df.empty:
            return []
        
        start_idx = self.config['avoid_first_mins']
        
        for idx, row in self.df.iloc[start_idx:].iterrows():
            trend = row.get('trend', 0)
            rsi = row.get('rsi', 50)
            
            spot = row['close']
            strike_gap = 50
            atm = round(spot / strike_gap) * strike_gap
            
            # Bullish trend -> Bull Put Spread
            if trend > 0 and rsi > 50:
                short_strike = int(atm - strike_gap * self.config['short_otm_strikes'])
                long_strike = int(short_strike - strike_gap * self.config['spread_width_strikes'])
                option_type = 'PE'
                strategy_name = "Bull Put Spread"
            # Bearish trend -> Bear Call Spread
            elif trend < 0 and rsi < 50:
                short_strike = int(atm + strike_gap * self.config['short_otm_strikes'])
                long_strike = int(short_strike + strike_gap * self.config['spread_width_strikes'])
                option_type = 'CE'
                strategy_name = "Bear Call Spread"
            else:
                continue
            
            short_prem = self._estimate_premium(spot, short_strike, option_type)
            long_prem = self._estimate_premium(spot, long_strike, option_type)
            credit = short_prem - long_prem
            max_loss = abs(short_strike - long_strike) - credit
            
            legs = [
                {'type': option_type, 'strike': short_strike, 'action': 'SELL', 'premium': short_prem},
                {'type': option_type, 'strike': long_strike, 'action': 'BUY', 'premium': long_prem},
            ]
            
            if option_type == 'PE':
                be = short_strike - credit
            else:
                be = short_strike + credit
            
            signal = OptionSellSignal(
                timestamp=idx,
                strategy_type=StrategyType.CREDIT_SPREAD,
                legs=legs,
                max_profit=credit,
                max_loss=max_loss,
                breakeven_points=[be],
                underlying_price=spot,
                reason=f"{strategy_name}: Trend={trend:.1f}, RSI={rsi:.0f}",
                probability_of_profit=0.60,
                iv_percentile=50.0
            )
            self.signals.append(signal)
            break
        
        return self.signals
    
    def _estimate_premium(self, spot: float, strike: int, option_type: str) -> float:
        distance = abs(spot - strike)
        if option_type == 'CE':
            intrinsic = max(0, spot - strike)
        else:
            intrinsic = max(0, strike - spot)
        time_value = max(3, 20 - (distance / 50) * 3)
        return intrinsic + time_value
    
    def to_dataframe(self) -> pd.DataFrame:
        if not self.signals:
            return pd.DataFrame()
        
        rows = []
        for s in self.signals:
            rows.append({
                'timestamp': s.timestamp,
                'strategy': s.strategy_type.value,
                'spot': s.underlying_price,
                'max_profit': s.max_profit,
                'max_loss': s.max_loss,
                'rr': s.max_profit / s.max_loss if s.max_loss > 0 else 0,
                'breakeven': s.breakeven_points[0],
                'pop': s.probability_of_profit,
                'reason': s.reason,
            })
        return pd.DataFrame(rows)
