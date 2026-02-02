"""
Paper Trading Platform
=======================
Complete paper trading system that:
1. Auto-places trades when signals are generated
2. Tracks all open positions with live P&L
3. Records trade history
4. Calculates performance metrics
5. Provides dashboard view

Features:
- Virtual capital management
- Real-time position tracking
- Trade history with P&L
- Win rate, profit factor stats
- Daily/Weekly/Monthly reports
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Optional
from enum import Enum
import json
import uuid

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from notifications import send_telegram_message
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False

try:
    from real_option_prices import get_real_option_price, get_fetcher
    REAL_PRICES_OK = True
except ImportError:
    REAL_PRICES_OK = False


class TradeStatus(Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PARTIAL = "PARTIAL"


class TradeResult(Enum):
    PROFIT = "PROFIT"
    LOSS = "LOSS"
    BREAKEVEN = "BREAKEVEN"
    PENDING = "PENDING"


@dataclass
class PaperTradeLeg:
    """Single leg of a paper trade"""
    leg_id: str
    strike: int
    option_type: str  # CE or PE
    action: str  # BUY or SELL
    quantity: int
    entry_price: float
    current_price: float = 0.0
    exit_price: float = 0.0
    pnl: float = 0.0


@dataclass
class PaperTrade:
    """Complete paper trade with all legs"""
    trade_id: str
    symbol: str
    strategy: str
    entry_time: str
    exit_time: str = ""
    
    # Trade details
    legs: List[Dict] = field(default_factory=list)
    lot_size: int = 75
    
    # Capital
    entry_premium: float = 0.0
    exit_premium: float = 0.0
    margin_used: float = 0.0
    
    # P&L
    pnl_points: float = 0.0
    pnl_amount: float = 0.0
    pnl_percent: float = 0.0
    
    # Status
    status: str = "OPEN"
    result: str = "PENDING"
    
    # Meta
    confidence: int = 0
    win_probability: float = 0.0
    exit_reason: str = ""


@dataclass
class PortfolioStats:
    """Portfolio statistics"""
    total_capital: float = 100000.0  # 1 Lakh starting capital
    used_margin: float = 0.0
    available_capital: float = 100000.0
    
    # P&L
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    
    # Stats
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # Performance
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    max_drawdown: float = 0.0
    
    # Best/Worst
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0


class PaperTradingPlatform:
    """
    Complete paper trading platform
    """
    
    def __init__(self, initial_capital: float = 100000.0):
        self.data_dir = Path(__file__).parent / "paper_trading_data"
        self.data_dir.mkdir(exist_ok=True)
        
        self.trades_file = self.data_dir / "trades.json"
        self.stats_file = self.data_dir / "stats.json"
        self.history_file = self.data_dir / "history.json"
        
        # Initialize
        self.open_trades: Dict[str, PaperTrade] = {}
        self.closed_trades: List[PaperTrade] = []
        self.stats = PortfolioStats(total_capital=initial_capital,
                                     available_capital=initial_capital)
        
        # Load existing data
        self._load_data()
    
    def _load_data(self):
        """Load existing trades and stats"""
        # Load open trades
        if self.trades_file.exists():
            try:
                with open(self.trades_file, 'r') as f:
                    data = json.load(f)
                    for tid, tdata in data.items():
                        self.open_trades[tid] = PaperTrade(**tdata)
            except:
                pass
        
        # Load stats
        if self.stats_file.exists():
            try:
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                    self.stats = PortfolioStats(**data)
            except:
                pass
        
        # Load history
        if self.history_file.exists():
            try:
                with open(self.history_file, 'r') as f:
                    data = json.load(f)
                    self.closed_trades = [PaperTrade(**t) for t in data]
            except:
                pass
    
    def _save_data(self):
        """Save all data"""
        # Save open trades
        with open(self.trades_file, 'w') as f:
            json.dump({tid: asdict(t) for tid, t in self.open_trades.items()}, f, indent=2)
        
        # Save stats
        with open(self.stats_file, 'w') as f:
            json.dump(asdict(self.stats), f, indent=2)
        
        # Save history
        with open(self.history_file, 'w') as f:
            json.dump([asdict(t) for t in self.closed_trades[-100:]], f, indent=2)  # Keep last 100
    
    def place_trade(self, symbol: str, strategy: str, legs: List[Dict],
                    lot_size: int = 75, confidence: int = 0,
                    win_probability: float = 0.0) -> Optional[PaperTrade]:
        """
        Place a new paper trade
        
        Args:
            symbol: NIFTY, BANKNIFTY
            strategy: Iron Condor, etc.
            legs: List of leg dictionaries
            lot_size: Lot size
        
        Returns:
            PaperTrade object
        """
        trade_id = f"PT_{datetime.now(IST).strftime('%Y%m%d_%H%M%S')}_{len(self.open_trades)+1}"
        
        # Calculate entry premium
        total_premium = 0
        for leg in legs:
            if leg.get('action') == 'SELL':
                total_premium += leg.get('entry_price', 0)
            else:
                total_premium -= leg.get('entry_price', 0)
        
        # Calculate margin (approx)
        margin = abs(total_premium) * lot_size * 3
        
        # Check available capital
        if margin > self.stats.available_capital:
            print(f"❌ Insufficient capital! Need ₹{margin:,.0f}, have ₹{self.stats.available_capital:,.0f}")
            return None
        
        # Create trade
        trade = PaperTrade(
            trade_id=trade_id,
            symbol=symbol,
            strategy=strategy,
            entry_time=datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S'),
            legs=legs,
            lot_size=lot_size,
            entry_premium=total_premium,
            margin_used=margin,
            status="OPEN",
            result="PENDING",
            confidence=confidence,
            win_probability=win_probability,
        )
        
        # Update capital
        self.stats.used_margin += margin
        self.stats.available_capital -= margin
        self.stats.total_trades += 1
        
        # Add to open trades
        self.open_trades[trade_id] = trade
        
        # Save
        self._save_data()
        
        print(f"✅ Paper trade placed: {trade_id}")
        return trade
    
    def update_positions(self):
        """Update all open positions with current prices"""
        for trade_id, trade in self.open_trades.items():
            total_pnl_points = 0
            
            for i, leg in enumerate(trade.legs):
                entry_price = leg.get('entry_price', 0)
                current_price = entry_price  # Default to entry if can't fetch
                
                # Get current price
                if REAL_PRICES_OK:
                    fetched_price = get_real_option_price(
                        trade.symbol, 
                        leg['strike'], 
                        leg['type']
                    )
                    if fetched_price and fetched_price > 0:
                        current_price = fetched_price
                        leg['current_price'] = current_price
                        trade.legs[i] = leg
                    else:
                        current_price = leg.get('current_price', entry_price)
                
                # Calculate P&L for this leg
                # SELL: Profit when price falls (entry - current)
                # BUY: Profit when price rises (current - entry)
                if leg.get('action') == 'SELL':
                    leg_pnl = entry_price - current_price
                else:  # BUY
                    leg_pnl = current_price - entry_price
                
                total_pnl_points += leg_pnl
            
            # Total P&L
            trade.pnl_points = total_pnl_points
            trade.pnl_amount = trade.pnl_points * trade.lot_size
            if trade.entry_premium != 0:
                trade.pnl_percent = (trade.pnl_amount / (abs(trade.entry_premium) * trade.lot_size)) * 100
            else:
                trade.pnl_percent = 0
        
        # Update unrealized P&L
        self.stats.unrealized_pnl = sum(t.pnl_amount for t in self.open_trades.values())
        self.stats.total_pnl = self.stats.realized_pnl + self.stats.unrealized_pnl
        
        self._save_data()
    
    def close_trade(self, trade_id: str, exit_reason: str = "Manual") -> Optional[PaperTrade]:
        """Close a paper trade"""
        if trade_id not in self.open_trades:
            print(f"❌ Trade {trade_id} not found")
            return None
        
        trade = self.open_trades[trade_id]
        
        # Update final prices
        self.update_positions()
        
        # Calculate P&L per leg
        total_pnl_points = 0
        for leg in trade.legs:
            entry_price = leg.get('entry_price', 0)
            exit_price = leg.get('current_price', entry_price)
            leg['exit_price'] = exit_price
            
            # SELL: Profit when price falls (entry - exit)
            # BUY: Profit when price rises (exit - entry)
            if leg.get('action') == 'SELL':
                leg_pnl = entry_price - exit_price
            else:  # BUY
                leg_pnl = exit_price - entry_price
            
            total_pnl_points += leg_pnl
        
        trade.exit_time = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')
        trade.exit_reason = exit_reason
        trade.status = "CLOSED"
        
        # Final P&L
        trade.pnl_points = total_pnl_points
        trade.pnl_amount = trade.pnl_points * trade.lot_size
        
        # Determine result
        if trade.pnl_amount > 0:
            trade.result = "PROFIT"
            self.stats.winning_trades += 1
        elif trade.pnl_amount < 0:
            trade.result = "LOSS"
            self.stats.losing_trades += 1
        else:
            trade.result = "BREAKEVEN"
        
        # Update stats
        self.stats.realized_pnl += trade.pnl_amount
        self.stats.used_margin -= trade.margin_used
        self.stats.available_capital += trade.margin_used
        
        # Update best/worst
        if trade.pnl_amount > self.stats.best_trade_pnl:
            self.stats.best_trade_pnl = trade.pnl_amount
        if trade.pnl_amount < self.stats.worst_trade_pnl:
            self.stats.worst_trade_pnl = trade.pnl_amount
        
        # Calculate win rate
        completed = self.stats.winning_trades + self.stats.losing_trades
        if completed > 0:
            self.stats.win_rate = (self.stats.winning_trades / completed) * 100
        
        # Move to history
        self.closed_trades.append(trade)
        del self.open_trades[trade_id]
        
        self._save_data()
        
        print(f"✅ Trade closed: {trade_id} | P&L: ₹{trade.pnl_amount:+,.0f}")
        return trade
    
    def get_open_positions(self) -> List[PaperTrade]:
        """Get all open positions"""
        self.update_positions()
        return list(self.open_trades.values())
    
    def get_trade_history(self, limit: int = 20) -> List[PaperTrade]:
        """Get trade history"""
        return self.closed_trades[-limit:]
    
    def generate_positions_message(self) -> str:
        """Generate Telegram message for open positions"""
        self.update_positions()
        
        if not self.open_trades:
            return "📊 <b>PAPER PORTFOLIO</b>\n\n📭 No open positions"
        
        msg = f"""
📊 <b>PAPER TRADING PORTFOLIO</b>

💰 <b>Capital:</b> ₹{self.stats.total_capital:,.0f}
📈 <b>Available:</b> ₹{self.stats.available_capital:,.0f}
🔒 <b>Used Margin:</b> ₹{self.stats.used_margin:,.0f}

━━━━━ OPEN POSITIONS ━━━━━

"""
        total_unrealized = 0
        
        for trade in self.open_trades.values():
            emoji = "🟢" if trade.pnl_amount >= 0 else "🔴"
            total_unrealized += trade.pnl_amount
            
            legs_str = ", ".join([f"{l.get('action','')[0]}-{l.get('type','')}{l.get('strike','')}" 
                                  for l in trade.legs])
            
            msg += f"""<b>{trade.symbol} | {trade.strategy}</b>
• Entry: {trade.entry_time}
• Legs: {legs_str}
• Entry Premium: ₹{trade.entry_premium:.2f}
• {emoji} P&L: ₹{trade.pnl_amount:+,.0f} ({trade.pnl_percent:+.1f}%)

"""
        
        unrealized_emoji = "🟢" if total_unrealized >= 0 else "🔴"
        realized_emoji = "🟢" if self.stats.realized_pnl >= 0 else "🔴"
        
        msg += f"""━━━━━ P&L SUMMARY ━━━━━

{unrealized_emoji} <b>Unrealized P&L:</b> ₹{total_unrealized:+,.0f}
{realized_emoji} <b>Realized P&L:</b> ₹{self.stats.realized_pnl:+,.0f}
📊 <b>Total P&L:</b> ₹{self.stats.total_pnl:+,.0f}

━━━━━ STATS ━━━━━

📈 <b>Total Trades:</b> {self.stats.total_trades}
✅ <b>Winners:</b> {self.stats.winning_trades}
❌ <b>Losers:</b> {self.stats.losing_trades}
📊 <b>Win Rate:</b> {self.stats.win_rate:.1f}%
"""
        return msg
    
    def generate_history_message(self, limit: int = 10) -> str:
        """Generate trade history message"""
        history = self.get_trade_history(limit)
        
        if not history:
            return "📜 <b>TRADE HISTORY</b>\n\n📭 No trades yet"
        
        msg = f"""
📜 <b>PAPER TRADE HISTORY</b>
(Last {len(history)} trades)

"""
        for trade in reversed(history):
            emoji = "🟢" if trade.result == "PROFIT" else "🔴"
            
            msg += f"""{emoji} <b>{trade.symbol} {trade.strategy}</b>
   {trade.entry_time[:10]} | ₹{trade.pnl_amount:+,.0f}
   
"""
        
        msg += f"""━━━━━ OVERALL STATS ━━━━━

📊 Total Trades: {self.stats.total_trades}
📈 Win Rate: {self.stats.win_rate:.1f}%
💰 Realized P&L: ₹{self.stats.realized_pnl:+,.0f}
🏆 Best Trade: ₹{self.stats.best_trade_pnl:+,.0f}
📉 Worst Trade: ₹{self.stats.worst_trade_pnl:+,.0f}
"""
        return msg
    
    def send_positions_update(self) -> bool:
        """Send positions update to Telegram"""
        msg = self.generate_positions_message()
        if TELEGRAM_OK:
            return send_telegram_message(msg)
        print(msg)
        return False
    
    def send_history(self) -> bool:
        """Send trade history to Telegram"""
        msg = self.generate_history_message()
        if TELEGRAM_OK:
            return send_telegram_message(msg)
        print(msg)
        return False
    
    def reset_portfolio(self, initial_capital: float = 100000.0):
        """Reset portfolio to initial state"""
        self.open_trades = {}
        self.closed_trades = []
        self.stats = PortfolioStats(total_capital=initial_capital,
                                     available_capital=initial_capital)
        self._save_data()
        print("✅ Portfolio reset!")


# Singleton
_platform = None


def get_platform() -> PaperTradingPlatform:
    """Get paper trading platform instance"""
    global _platform
    if _platform is None:
        _platform = PaperTradingPlatform()
    return _platform


def place_paper_trade(symbol, strategy, legs, lot_size=75, confidence=0, win_prob=0):
    """Place a paper trade"""
    return get_platform().place_trade(symbol, strategy, legs, lot_size, confidence, win_prob)


def send_positions():
    """Send positions to Telegram"""
    return get_platform().send_positions_update()


def send_history():
    """Send history to Telegram"""
    return get_platform().send_history()


# =============================================================================
# TEST
# =============================================================================

def test_paper_trading():
    """Test paper trading platform"""
    print("\n" + "="*60)
    print("       PAPER TRADING PLATFORM TEST")
    print("="*60)
    
    platform = PaperTradingPlatform(initial_capital=100000)
    
    # Place a sample trade
    trade = platform.place_trade(
        symbol="NIFTY",
        strategy="Iron Condor",
        legs=[
            {'strike': 25700, 'type': 'CE', 'action': 'SELL', 'entry_price': 85},
            {'strike': 25800, 'type': 'CE', 'action': 'BUY', 'entry_price': 45},
            {'strike': 25400, 'type': 'PE', 'action': 'SELL', 'entry_price': 80},
            {'strike': 25300, 'type': 'PE', 'action': 'BUY', 'entry_price': 40},
        ],
        lot_size=75,
        confidence=85,
        win_probability=72,
    )
    
    if trade:
        print(f"\nTrade placed: {trade.trade_id}")
        
        # Show positions
        platform.send_positions_update()
        
        # Close trade
        platform.close_trade(trade.trade_id, "Test close")
        
        # Show history
        platform.send_history()
    
    print("\n✅ Test complete!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--test', action='store_true', help='Run test')
    parser.add_argument('--positions', action='store_true', help='Show positions')
    parser.add_argument('--history', action='store_true', help='Show history')
    parser.add_argument('--reset', action='store_true', help='Reset portfolio')
    
    args = parser.parse_args()
    
    if args.test:
        test_paper_trading()
    elif args.positions:
        send_positions()
    elif args.history:
        send_history()
    elif args.reset:
        get_platform().reset_portfolio()
    else:
        print("Paper Trading Platform")
        print("  --test       Run test")
        print("  --positions  Show open positions")
        print("  --history    Show trade history")
        print("  --reset      Reset portfolio")
