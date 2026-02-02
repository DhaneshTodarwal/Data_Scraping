"""
Portfolio Manager for Paper Trading
=====================================
Tracks positions, P&L, and portfolio metrics
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import NIFTY_LOT_SIZE, BANKNIFTY_LOT_SIZE

IST = timezone(timedelta(hours=5, minutes=30))


@dataclass
class Position:
    """Represents an open position"""
    id: str
    symbol: str
    strategy: str
    strategy_type: str  # STRADDLE, STRANGLE, etc.
    direction: str  # BUY or SELL
    entry_time: datetime
    entry_premium: float
    stop_loss: float
    target: float
    quantity: int
    legs: Dict = field(default_factory=dict)  # Strike details
    current_premium: float = 0.0
    unrealized_pnl: float = 0.0
    status: str = 'OPEN'


@dataclass
class Trade:
    """Represents a completed trade"""
    id: str
    symbol: str
    strategy: str
    direction: str
    entry_time: datetime
    exit_time: datetime
    entry_premium: float
    exit_premium: float
    quantity: int
    pnl: float
    pnl_percent: float
    exit_reason: str


class Portfolio:
    """Manages paper trading portfolio"""
    
    def __init__(self, initial_capital: float = 1000000):
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.positions: Dict[str, Position] = {}
        self.trades: List[Trade] = []
        self.daily_pnl: Dict[str, float] = {}
        self.trade_counter = 0
        
        # Lot sizes
        self.lot_sizes = {
            'NIFTY': NIFTY_LOT_SIZE,
            'BANKNIFTY': BANKNIFTY_LOT_SIZE,
            'FINNIFTY': 65,
            'MIDCAPNIFTY': 100,
            'SENSEX': 20,
        }
    
    def get_lot_size(self, symbol: str) -> int:
        """Get lot size for symbol"""
        return self.lot_sizes.get(symbol, 50)
    
    def open_position(self, symbol: str, strategy: str, strategy_type: str,
                      direction: str, entry_premium: float, sl_pct: float,
                      target_pct: float, legs: Dict = None, lots: int = 1) -> Position:
        """Open a new position"""
        
        self.trade_counter += 1
        position_id = f"PT_{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}_{self.trade_counter}"
        
        lot_size = self.get_lot_size(symbol)
        quantity = lot_size * lots
        
        # Calculate SL and target based on direction
        if direction == 'SELL':
            # For selling, SL is premium increasing (loss)
            stop_loss = entry_premium * (1 + sl_pct / 100)
            target = entry_premium * (1 - target_pct / 100)
        else:
            # For buying, SL is premium decreasing (loss)
            stop_loss = entry_premium * (1 - sl_pct / 100)
            target = entry_premium * (1 + target_pct / 100)
        
        position = Position(
            id=position_id,
            symbol=symbol,
            strategy=strategy,
            strategy_type=strategy_type,
            direction=direction,
            entry_time=datetime.now(IST),
            entry_premium=entry_premium,
            stop_loss=stop_loss,
            target=target,
            quantity=quantity,
            legs=legs or {},
            current_premium=entry_premium,
        )
        
        self.positions[position_id] = position
        return position
    
    def update_position(self, position_id: str, current_premium: float):
        """Update position with current market price"""
        if position_id not in self.positions:
            return
        
        pos = self.positions[position_id]
        pos.current_premium = current_premium
        
        # Calculate unrealized P&L
        if pos.direction == 'SELL':
            pos.unrealized_pnl = (pos.entry_premium - current_premium) * pos.quantity
        else:
            pos.unrealized_pnl = (current_premium - pos.entry_premium) * pos.quantity
    
    def check_exit_conditions(self, position_id: str) -> Optional[str]:
        """Check if position should be closed"""
        if position_id not in self.positions:
            return None
        
        pos = self.positions[position_id]
        
        if pos.direction == 'SELL':
            # For SELL: SL hit if premium goes UP, target hit if goes DOWN
            if pos.current_premium >= pos.stop_loss:
                return 'stoploss'
            if pos.current_premium <= pos.target:
                return 'target'
        else:
            # For BUY: SL hit if premium goes DOWN, target hit if goes UP
            if pos.current_premium <= pos.stop_loss:
                return 'stoploss'
            if pos.current_premium >= pos.target:
                return 'target'
        
        return None
    
    def close_position(self, position_id: str, exit_premium: float = None,
                       exit_reason: str = 'manual') -> Optional[Trade]:
        """Close a position and record the trade"""
        if position_id not in self.positions:
            return None
        
        pos = self.positions[position_id]
        exit_premium = exit_premium or pos.current_premium
        
        # Calculate P&L
        if pos.direction == 'SELL':
            pnl = (pos.entry_premium - exit_premium) * pos.quantity
        else:
            pnl = (exit_premium - pos.entry_premium) * pos.quantity
        
        pnl_percent = ((exit_premium - pos.entry_premium) / pos.entry_premium) * 100
        if pos.direction == 'SELL':
            pnl_percent = -pnl_percent
        
        trade = Trade(
            id=pos.id,
            symbol=pos.symbol,
            strategy=pos.strategy,
            direction=pos.direction,
            entry_time=pos.entry_time,
            exit_time=datetime.now(IST),
            entry_premium=pos.entry_premium,
            exit_premium=exit_premium,
            quantity=pos.quantity,
            pnl=pnl,
            pnl_percent=pnl_percent,
            exit_reason=exit_reason,
        )
        
        self.trades.append(trade)
        self.capital += pnl
        
        # Track daily P&L
        date_str = datetime.now(IST).strftime('%Y-%m-%d')
        self.daily_pnl[date_str] = self.daily_pnl.get(date_str, 0) + pnl
        
        # Remove position
        del self.positions[position_id]
        
        return trade
    
    def get_open_positions(self) -> List[Position]:
        """Get all open positions"""
        return list(self.positions.values())
    
    def get_portfolio_value(self) -> float:
        """Get total portfolio value including unrealized P&L"""
        unrealized = sum(p.unrealized_pnl for p in self.positions.values())
        return self.capital + unrealized
    
    def get_stats(self) -> Dict:
        """Get portfolio statistics"""
        total_trades = len(self.trades)
        winners = sum(1 for t in self.trades if t.pnl > 0)
        total_pnl = sum(t.pnl for t in self.trades)
        
        return {
            'initial_capital': self.initial_capital,
            'current_capital': self.capital,
            'portfolio_value': self.get_portfolio_value(),
            'total_return': ((self.capital - self.initial_capital) / self.initial_capital) * 100,
            'open_positions': len(self.positions),
            'total_trades': total_trades,
            'winners': winners,
            'losers': total_trades - winners,
            'win_rate': (winners / total_trades * 100) if total_trades > 0 else 0,
            'total_pnl': total_pnl,
            'avg_pnl_per_trade': total_pnl / total_trades if total_trades > 0 else 0,
            'max_win': max((t.pnl for t in self.trades), default=0),
            'max_loss': min((t.pnl for t in self.trades), default=0),
        }
    
    def print_summary(self):
        """Print portfolio summary"""
        stats = self.get_stats()
        
        print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    PAPER TRADING PORTFOLIO                     ║
╠══════════════════════════════════════════════════════════════╣
║  Initial Capital:    ₹{stats['initial_capital']:>12,.0f}                    ║
║  Current Capital:    ₹{stats['current_capital']:>12,.0f}                    ║
║  Total Return:       {stats['total_return']:>12.2f}%                    ║
╠══════════════════════════════════════════════════════════════╣
║  Open Positions:     {stats['open_positions']:>12}                         ║
║  Total Trades:       {stats['total_trades']:>12}                         ║
║  Winners:            {stats['winners']:>12}                         ║
║  Win Rate:           {stats['win_rate']:>12.1f}%                    ║
╠══════════════════════════════════════════════════════════════╣
║  Total P&L:          ₹{stats['total_pnl']:>12,.0f}                    ║
║  Avg P&L/Trade:      ₹{stats['avg_pnl_per_trade']:>12,.0f}                    ║
║  Max Win:            ₹{stats['max_win']:>12,.0f}                    ║
║  Max Loss:           ₹{stats['max_loss']:>12,.0f}                    ║
╚══════════════════════════════════════════════════════════════╝
""")
    
    def save_state(self, filepath: Path = None):
        """Save portfolio state to file"""
        filepath = filepath or Path(__file__).parent / "portfolio_state.json"
        
        state = {
            'capital': self.capital,
            'initial_capital': self.initial_capital,
            'trade_counter': self.trade_counter,
            'positions': [
                {
                    'id': p.id, 'symbol': p.symbol, 'strategy': p.strategy,
                    'direction': p.direction, 'entry_premium': p.entry_premium,
                    'stop_loss': p.stop_loss, 'target': p.target,
                    'quantity': p.quantity,
                }
                for p in self.positions.values()
            ],
            'trades': [
                {
                    'id': t.id, 'symbol': t.symbol, 'strategy': t.strategy,
                    'pnl': t.pnl, 'exit_reason': t.exit_reason,
                }
                for t in self.trades
            ],
            'daily_pnl': self.daily_pnl,
        }
        
        with open(filepath, 'w') as f:
            json.dump(state, f, indent=2, default=str)
        
        print(f"✅ Portfolio saved to: {filepath}")
    
    def load_state(self, filepath: Path = None):
        """Load portfolio state from file"""
        filepath = filepath or Path(__file__).parent / "portfolio_state.json"
        
        if not filepath.exists():
            print("⚠ No saved state found")
            return False
        
        with open(filepath, 'r') as f:
            state = json.load(f)
        
        self.capital = state.get('capital', self.initial_capital)
        self.trade_counter = state.get('trade_counter', 0)
        self.daily_pnl = state.get('daily_pnl', {})
        
        print(f"✅ Portfolio loaded from: {filepath}")
        return True
