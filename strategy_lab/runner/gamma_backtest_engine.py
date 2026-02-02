"""
Advanced Backtest Engine for Gamma-EMA Strategy
=================================================
Enhanced backtesting with:
- Trailing stop loss
- Breakeven trigger
- Sideways exit
- Detailed trade tracking
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import json
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import REPORTS_DIR, LOT_SIZES, DEFAULT_CONFIG
from strategies.base_strategy import Signal, SignalType


@dataclass
class GammaTrade:
    """Enhanced trade tracking for Gamma strategy."""
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp = None
    signal_type: str = ""
    strike: int = 0
    entry_price: float = 0.0
    exit_price: float = 0.0
    quantity: int = 0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    exit_reason: str = ""
    max_profit_pct: float = 0.0
    max_loss_pct: float = 0.0
    duration_minutes: int = 0
    hit_breakeven: bool = False
    trailing_activated: bool = False
    
    def to_dict(self) -> Dict:
        return {
            'entry_time': str(self.entry_time),
            'exit_time': str(self.exit_time),
            'signal_type': self.signal_type,
            'strike': self.strike,
            'entry_price': round(self.entry_price, 2),
            'exit_price': round(self.exit_price, 2),
            'quantity': self.quantity,
            'pnl': round(self.pnl, 2),
            'pnl_pct': round(self.pnl_pct, 2),
            'exit_reason': self.exit_reason,
            'max_profit_pct': round(self.max_profit_pct, 2),
            'max_loss_pct': round(self.max_loss_pct, 2),
            'duration_minutes': self.duration_minutes,
            'hit_breakeven': self.hit_breakeven,
            'trailing_activated': self.trailing_activated,
        }


class GammaBacktestEngine:
    """
    Specialized backtest engine for Gamma-EMA strategy.
    Implements advanced exit logic including trailing and time-based exits.
    """
    
    def __init__(self, symbol: str, config: Dict = None):
        self.symbol = symbol
        self.config = config or {}
        self.lot_size = LOT_SIZES.get(symbol, 25)
        self.initial_capital = self.config.get('initial_capital', 100000)
        
        # Strategy parameters
        self.stop_loss_pct = self.config.get('stop_loss_pct', 25)
        self.initial_rr = self.config.get('initial_rr', 4)
        self.trail_start_rr = self.config.get('trail_start_rr', 3)
        self.breakeven_trigger = self.config.get('breakeven_trigger', 100)
        self.sideways_exit_minutes = self.config.get('sideways_exit_minutes', 5)
        
        self.trades: List[GammaTrade] = []
        self.capital = self.initial_capital
        self.equity_curve = [self.initial_capital]
    
    def run(self, signals: List[Signal], 
            strikes_data: Dict[str, Dict[int, pd.DataFrame]],
            slippage_pct: float = 0.1) -> Dict:
        """Run backtest with advanced exit logic."""
        
        if not signals:
            return self._create_empty_result()
        
        for signal in signals:
            trade = self._execute_trade(signal, strikes_data, slippage_pct)
            if trade:
                self.trades.append(trade)
                self.capital += trade.pnl
                self.equity_curve.append(self.capital)
        
        return self._calculate_results()
    
    def _execute_trade(self, signal: Signal, 
                       strikes_data: Dict[str, Dict[int, pd.DataFrame]],
                       slippage_pct: float) -> Optional[GammaTrade]:
        """Execute a single trade with full exit logic."""
        
        # Determine option type
        if signal.signal_type in [SignalType.BUY_CE, SignalType.SELL_CE]:
            option_type = 'CE'
        else:
            option_type = 'PE'
        
        # Get strike data
        if signal.strike not in strikes_data.get(option_type, {}):
            return None
        
        strike_df = strikes_data[option_type][signal.strike]
        
        # Find data after entry time
        entry_rows = strike_df[strike_df['timestamp'] >= signal.timestamp]
        if entry_rows.empty:
            return None
        
        # Entry
        entry_row = entry_rows.iloc[0]
        entry_price = entry_row['close'] * (1 + slippage_pct / 100)
        entry_time = entry_row['timestamp']
        
        # Initialize trade tracking
        trade = GammaTrade(
            entry_time=entry_time,
            signal_type=signal.signal_type.value,
            strike=signal.strike,
            entry_price=entry_price,
            quantity=self.lot_size,
        )
        
        # Calculate initial levels
        risk = entry_price * (self.stop_loss_pct / 100)
        initial_sl = entry_price - risk
        initial_target = entry_price + (risk * self.initial_rr)
        breakeven_price = entry_price * 2  # 100% gain
        trail_start_price = entry_price + (risk * self.trail_start_rr)
        
        current_sl = initial_sl
        trailing_active = False
        sideways_count = 0
        prev_price = entry_price
        
        # Track max profit/loss
        max_price = entry_price
        min_price = entry_price
        
        # Simulate bar by bar
        for _, row in entry_rows.iloc[1:].iterrows():
            current_price = row['close']
            current_time = row['timestamp']
            current_high = row['high']
            current_low = row['low']
            
            # Track extremes
            max_price = max(max_price, current_high)
            min_price = min(min_price, current_low)
            
            trade.max_profit_pct = ((max_price - entry_price) / entry_price) * 100
            trade.max_loss_pct = ((min_price - entry_price) / entry_price) * 100
            
            # Check breakeven trigger (100% gain)
            if current_high >= breakeven_price and not trade.hit_breakeven:
                trade.hit_breakeven = True
                current_sl = entry_price  # Move SL to cost
            
            # Check trailing activation (1:3 RR)
            if current_high >= trail_start_price and not trailing_active:
                trailing_active = True
                trade.trailing_activated = True
            
            # Update trailing stop
            if trailing_active:
                # Trail using previous candle low (for calls)
                if signal.signal_type == SignalType.BUY_CE:
                    current_sl = max(current_sl, current_low * 0.99)
                else:  # PUT
                    current_sl = max(current_sl, current_low * 0.99)
            
            # Check stop loss hit
            if current_low <= current_sl:
                trade.exit_time = current_time
                trade.exit_price = current_sl * (1 - slippage_pct / 100)
                trade.exit_reason = 'trailing_sl' if trailing_active else 'stoploss'
                break
            
            # Check target hit
            if current_high >= initial_target:
                trade.exit_time = current_time
                trade.exit_price = initial_target * (1 - slippage_pct / 100)
                trade.exit_reason = 'target_4x'
                break
            
            # Check sideways exit (price not moving for 5 minutes)
            price_change_pct = abs((current_price - prev_price) / prev_price * 100)
            if price_change_pct < 1:  # Less than 1% move
                sideways_count += 1
            else:
                sideways_count = 0
            
            if sideways_count >= self.sideways_exit_minutes:
                trade.exit_time = current_time
                trade.exit_price = current_price * (1 - slippage_pct / 100)
                trade.exit_reason = 'sideways_exit'
                break
            
            # Check time exit
            time_str = current_time.strftime('%H:%M')
            if time_str >= '15:25':
                trade.exit_time = current_time
                trade.exit_price = current_price * (1 - slippage_pct / 100)
                trade.exit_reason = 'time_exit'
                break
            
            prev_price = current_price
        
        # If no exit, close at last price
        if trade.exit_time is None:
            last_row = entry_rows.iloc[-1]
            trade.exit_time = last_row['timestamp']
            trade.exit_price = last_row['close'] * (1 - slippage_pct / 100)
            trade.exit_reason = 'end_of_data'
        
        # Calculate final P&L
        trade.pnl = (trade.exit_price - trade.entry_price) * trade.quantity
        trade.pnl -= 20  # Commission
        trade.pnl_pct = ((trade.exit_price - trade.entry_price) / trade.entry_price) * 100
        trade.duration_minutes = int((trade.exit_time - trade.entry_time).total_seconds() / 60)
        
        return trade
    
    def _calculate_results(self) -> Dict:
        """Calculate comprehensive backtest results."""
        
        result = {
            'strategy_name': 'Gamma_EMA_Confluence',
            'symbol': self.symbol,
            'initial_capital': self.initial_capital,
            'final_capital': self.capital,
            'total_trades': len(self.trades),
            'trades': [t.to_dict() for t in self.trades],
        }
        
        if not self.trades:
            return result
        
        # Trade statistics
        pnls = [t.pnl for t in self.trades]
        result['winning_trades'] = sum(1 for t in self.trades if t.pnl > 0)
        result['losing_trades'] = sum(1 for t in self.trades if t.pnl < 0)
        result['win_rate'] = result['winning_trades'] / len(self.trades) * 100
        
        # P&L statistics
        result['total_pnl'] = sum(pnls)
        result['avg_pnl_per_trade'] = result['total_pnl'] / len(self.trades)
        result['max_win'] = max(pnls)
        result['max_loss'] = min(pnls)
        
        # Profit factor
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        result['profit_factor'] = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Risk metrics
        equity = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = peak - equity
        result['max_drawdown'] = drawdown.max()
        result['max_drawdown_pct'] = (drawdown.max() / peak.max() * 100) if peak.max() > 0 else 0
        
        # Sharpe ratio
        if len(pnls) > 1:
            returns = np.array(pnls) / self.initial_capital
            result['sharpe_ratio'] = np.sqrt(252) * returns.mean() / returns.std() if returns.std() > 0 else 0
        else:
            result['sharpe_ratio'] = 0
        
        # Exit reason breakdown
        exit_reasons = {}
        for t in self.trades:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1
        result['exit_breakdown'] = exit_reasons
        
        # Average duration
        result['avg_duration_minutes'] = sum(t.duration_minutes for t in self.trades) / len(self.trades)
        
        # Trailing and breakeven stats
        result['trades_hit_breakeven'] = sum(1 for t in self.trades if t.hit_breakeven)
        result['trades_with_trailing'] = sum(1 for t in self.trades if t.trailing_activated)
        
        return result
    
    def _create_empty_result(self) -> Dict:
        return {
            'strategy_name': 'Gamma_EMA_Confluence',
            'symbol': self.symbol,
            'initial_capital': self.initial_capital,
            'final_capital': self.initial_capital,
            'total_trades': 0,
            'trades': [],
        }
    
    def print_report(self, result: Dict):
        """Print formatted report."""
        print(f"""
{'='*70}
        GAMMA-EMA CONFLUENCE BACKTEST REPORT
{'='*70}

📅 SYMBOL: {result.get('symbol', 'N/A')}

📊 TRADE STATISTICS
   Total Trades:     {result.get('total_trades', 0)}
   Winners:          {result.get('winning_trades', 0)}
   Losers:           {result.get('losing_trades', 0)}
   Win Rate:         {result.get('win_rate', 0):.1f}%

💰 PROFIT & LOSS
   Initial Capital:  ₹{result.get('initial_capital', 0):,.0f}
   Final Capital:    ₹{result.get('final_capital', 0):,.0f}
   Total P&L:        ₹{result.get('total_pnl', 0):,.0f}
   Avg P&L/Trade:    ₹{result.get('avg_pnl_per_trade', 0):,.0f}
   Max Win:          ₹{result.get('max_win', 0):,.0f}
   Max Loss:         ₹{result.get('max_loss', 0):,.0f}
   Profit Factor:    {result.get('profit_factor', 0):.2f}

⚠️ RISK METRICS
   Max Drawdown:     ₹{result.get('max_drawdown', 0):,.0f} ({result.get('max_drawdown_pct', 0):.1f}%)
   Sharpe Ratio:     {result.get('sharpe_ratio', 0):.2f}

🎯 ADVANCED METRICS
   Avg Duration:     {result.get('avg_duration_minutes', 0):.0f} minutes
   Hit Breakeven:    {result.get('trades_hit_breakeven', 0)} trades
   Trailing Active:  {result.get('trades_with_trailing', 0)} trades

📋 EXIT BREAKDOWN
""")
        for reason, count in result.get('exit_breakdown', {}).items():
            print(f"   {reason}: {count}")
        
        print(f"\n{'='*70}")
