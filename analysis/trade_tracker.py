"""
Trade Result Tracker
======================
Tracks all trades from entry to exit and sends result notifications

Features:
1. Record each signal as an open trade
2. Monitor trades during the day
3. Send closing alerts with results (Profit/Loss)
4. Track exit reason (Target, SL, Trailing SL, Breakeven, Time Exit)
5. Generate daily trade results summary
6. Keep historical trade log
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta, time, date
from enum import Enum
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

try:
    from notifications import send_telegram_message
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False

IST = timezone(timedelta(hours=5, minutes=30))


# =============================================================================
# ENUMS
# =============================================================================

class TradeStatus(Enum):
    OPEN = "Open"
    CLOSED_TARGET = "Target Hit"
    CLOSED_SL = "Stop Loss Hit"
    CLOSED_TRAILING = "Trailing SL Hit"
    CLOSED_BREAKEVEN = "Breakeven Exit"
    CLOSED_TIME = "Time Exit"
    CLOSED_MANUAL = "Manual Exit"


class TradeResult(Enum):
    PROFIT = "Profit"
    LOSS = "Loss"
    BREAKEVEN = "Breakeven"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class TrackedTrade:
    """A tracked trade from entry to exit"""
    trade_id: str
    symbol: str
    strategy: str
    trade_date: str
    
    # Entry
    entry_time: str
    entry_premium: float
    quantity: int
    lot_size: int
    
    # Targets
    initial_sl: float
    current_sl: float
    target: float
    
    # Exit (filled when closed)
    exit_time: str = ""
    exit_premium: float = 0.0
    exit_reason: str = ""
    
    # P&L
    pnl: float = 0.0
    pnl_percent: float = 0.0
    result: str = ""
    
    # Status
    status: str = "OPEN"
    trail_count: int = 0
    
    # Confidence at entry
    confidence: int = 0
    win_probability: float = 0.0


# =============================================================================
# TRADE TRACKER
# =============================================================================

class TradeResultTracker:
    """
    Tracks all trades and sends result notifications
    """
    
    def __init__(self):
        self.open_trades: Dict[str, TrackedTrade] = {}
        self.closed_trades: List[TrackedTrade] = []
        self.trade_counter = 0
        
        # File paths for persistence
        self.data_dir = Path(__file__).parent / "trade_logs"
        self.data_dir.mkdir(exist_ok=True)
    
    def generate_trade_id(self) -> str:
        """Generate unique trade ID"""
        self.trade_counter += 1
        return f"T{datetime.now(IST).strftime('%Y%m%d')}_{self.trade_counter:03d}"
    
    # =========================================================================
    # TRADE ENTRY
    # =========================================================================
    
    def record_entry(self, symbol: str, strategy: str, entry_premium: float,
                     quantity: int, lot_size: int, sl: float, target: float,
                     confidence: int = 0, win_probability: float = 0.0) -> TrackedTrade:
        """Record a new trade entry"""
        
        trade_id = self.generate_trade_id()
        now = datetime.now(IST)
        
        trade = TrackedTrade(
            trade_id=trade_id,
            symbol=symbol,
            strategy=strategy,
            trade_date=now.strftime('%Y-%m-%d'),
            entry_time=now.strftime('%H:%M:%S'),
            entry_premium=entry_premium,
            quantity=quantity,
            lot_size=lot_size,
            initial_sl=sl,
            current_sl=sl,
            target=target,
            status="OPEN",
            confidence=confidence,
            win_probability=win_probability,
        )
        
        self.open_trades[trade_id] = trade
        print(f"📝 Trade recorded: {trade_id} | {symbol} {strategy}")
        
        return trade
    
    # =========================================================================
    # TRADE EXIT
    # =========================================================================
    
    def record_exit(self, trade_id: str, exit_premium: float, 
                    exit_reason: TradeStatus) -> Optional[TrackedTrade]:
        """Record trade exit and calculate P&L"""
        
        if trade_id not in self.open_trades:
            print(f"⚠ Trade {trade_id} not found")
            return None
        
        trade = self.open_trades[trade_id]
        now = datetime.now(IST)
        
        # Calculate P&L (for option selling: profit when premium decreases)
        pnl = (trade.entry_premium - exit_premium) * trade.quantity
        pnl_percent = ((trade.entry_premium - exit_premium) / trade.entry_premium) * 100
        
        # Determine result
        if pnl > 0:
            result = TradeResult.PROFIT
        elif pnl < 0:
            result = TradeResult.LOSS
        else:
            result = TradeResult.BREAKEVEN
        
        # Update trade
        trade.exit_time = now.strftime('%H:%M:%S')
        trade.exit_premium = exit_premium
        trade.exit_reason = exit_reason.value
        trade.pnl = pnl
        trade.pnl_percent = pnl_percent
        trade.result = result.value
        trade.status = "CLOSED"
        
        # Move to closed trades
        del self.open_trades[trade_id]
        self.closed_trades.append(trade)
        
        # Send result notification
        self._send_result_notification(trade)
        
        return trade
    
    def update_trailing_sl(self, trade_id: str, new_sl: float):
        """Update trailing stop loss"""
        if trade_id in self.open_trades:
            self.open_trades[trade_id].current_sl = new_sl
            self.open_trades[trade_id].trail_count += 1
    
    # =========================================================================
    # RESULT NOTIFICATIONS
    # =========================================================================
    
    def _send_result_notification(self, trade: TrackedTrade):
        """Send trade result notification"""
        
        # Emoji based on result
        if trade.result == "Profit":
            result_emoji = "🟢"
            title = "TRADE CLOSED IN PROFIT"
        elif trade.result == "Loss":
            result_emoji = "🔴"
            title = "TRADE CLOSED IN LOSS"
        else:
            result_emoji = "🟡"
            title = "TRADE CLOSED AT BREAKEVEN"
        
        # Exit reason emoji
        reason_emojis = {
            "Target Hit": "🎯",
            "Stop Loss Hit": "🛑",
            "Trailing SL Hit": "🔄",
            "Breakeven Exit": "⚖️",
            "Time Exit": "⏰",
            "Manual Exit": "👤",
        }
        reason_emoji = reason_emojis.get(trade.exit_reason, "📍")
        
        # Calculate duration
        entry_time = datetime.strptime(f"{trade.trade_date} {trade.entry_time}", 
                                       "%Y-%m-%d %H:%M:%S")
        exit_time = datetime.strptime(f"{trade.trade_date} {trade.exit_time}", 
                                      "%Y-%m-%d %H:%M:%S")
        duration = exit_time - entry_time
        hours = duration.seconds // 3600
        mins = (duration.seconds % 3600) // 60
        
        msg = f"""
{result_emoji} <b>{title}</b>

📈 <b>{trade.symbol}</b> | {trade.strategy}
📅 {trade.trade_date}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 TRADE RESULT:</b>

<b>Entry:</b> ₹{trade.entry_premium:.2f} at {trade.entry_time}
<b>Exit:</b> ₹{trade.exit_premium:.2f} at {trade.exit_time}

{result_emoji} <b>P&L: ₹{trade.pnl:,.0f} ({trade.pnl_percent:+.1f}%)</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>{reason_emoji} EXIT REASON: {trade.exit_reason}</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📋 TRADE DETAILS:</b>
• Trade ID: {trade.trade_id}
• Duration: {hours}h {mins}m
• Quantity: {trade.quantity} ({trade.quantity // trade.lot_size} lots)
• Initial SL: ₹{trade.initial_sl:.2f}
• Final SL: ₹{trade.current_sl:.2f}
• Target: ₹{trade.target:.2f}
• Trailing SL Updates: {trade.trail_count}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📈 SIGNAL ACCURACY:</b>
• Entry Confidence: {trade.confidence}%
• Win Probability: {trade.win_probability:.0f}%
• Actual Result: {trade.result}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        self._send_alert(msg)
    
    def _send_alert(self, msg: str) -> bool:
        """Send alert"""
        if NOTIFICATIONS_AVAILABLE:
            return send_telegram_message(msg)
        print(msg)
        return False
    
    # =========================================================================
    # DAILY SUMMARY
    # =========================================================================
    
    def generate_daily_summary(self) -> str:
        """Generate end-of-day summary of all trades"""
        
        today = datetime.now(IST).strftime('%Y-%m-%d')
        todays_trades = [t for t in self.closed_trades if t.trade_date == today]
        
        if not todays_trades:
            return self._format_no_trades_summary(today)
        
        # Calculate statistics
        total_pnl = sum(t.pnl for t in todays_trades)
        winners = [t for t in todays_trades if t.result == "Profit"]
        losers = [t for t in todays_trades if t.result == "Loss"]
        breakeven = [t for t in todays_trades if t.result == "Breakeven"]
        
        win_rate = (len(winners) / len(todays_trades)) * 100 if todays_trades else 0
        
        # Best and worst trades
        best_trade = max(todays_trades, key=lambda t: t.pnl, default=None)
        worst_trade = min(todays_trades, key=lambda t: t.pnl, default=None)
        
        # P&L by strategy
        strategy_pnl = {}
        for t in todays_trades:
            if t.strategy not in strategy_pnl:
                strategy_pnl[t.strategy] = {'pnl': 0, 'count': 0}
            strategy_pnl[t.strategy]['pnl'] += t.pnl
            strategy_pnl[t.strategy]['count'] += 1
        
        # Exit reasons breakdown
        exit_reasons = {}
        for t in todays_trades:
            exit_reasons[t.exit_reason] = exit_reasons.get(t.exit_reason, 0) + 1
        
        # Overall emoji
        if total_pnl > 0:
            day_emoji = "🟢"
            day_status = "PROFITABLE DAY"
        elif total_pnl < 0:
            day_emoji = "🔴"
            day_status = "LOSS DAY"
        else:
            day_emoji = "🟡"
            day_status = "BREAKEVEN DAY"
        
        msg = f"""
📊 <b>DAILY TRADING REPORT</b>

📅 {today}
{day_emoji} <b>{day_status}</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📈 SUMMARY:</b>

• Total Trades: {len(todays_trades)}
• Winners: {len(winners)} ✅
• Losers: {len(losers)} ❌
• Breakeven: {len(breakeven)} ⚖️
• Win Rate: {win_rate:.0f}%

{day_emoji} <b>Total P&L: ₹{total_pnl:,.0f}</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🏆 BEST TRADE:</b>
• {best_trade.symbol} {best_trade.strategy}
• P&L: ₹{best_trade.pnl:,.0f}

<b>📉 WORST TRADE:</b>
• {worst_trade.symbol} {worst_trade.strategy}
• P&L: ₹{worst_trade.pnl:,.0f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 BY STRATEGY:</b>
"""
        for strategy, data in strategy_pnl.items():
            emoji = "🟢" if data['pnl'] > 0 else "🔴"
            msg += f"• {strategy}: {emoji} ₹{data['pnl']:,.0f} ({data['count']} trades)\n"
        
        msg += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📋 EXIT REASONS:</b>
"""
        for reason, count in exit_reasons.items():
            msg += f"• {reason}: {count}\n"
        
        msg += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📈 TRADE LOG:</b>
"""
        for t in todays_trades:
            emoji = "🟢" if t.result == "Profit" else ("🔴" if t.result == "Loss" else "🟡")
            msg += f"{emoji} {t.symbol} {t.strategy[:10]}: ₹{t.pnl:+,.0f}\n"
        
        msg += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📱 <i>Trade smarter tomorrow!</i>
"""
        return msg
    
    def _format_no_trades_summary(self, today: str) -> str:
        """Format summary when no trades"""
        return f"""
📊 <b>DAILY TRADING REPORT</b>

📅 {today}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>No trades today</b>

Either:
• No signals met the criteria
• Market conditions were unfavorable
• Scanner was not running

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📱 <i>See you tomorrow!</i>
"""
    
    def send_daily_summary(self):
        """Send daily summary notification"""
        msg = self.generate_daily_summary()
        self._send_alert(msg)
    
    # =========================================================================
    # PERSISTENCE
    # =========================================================================
    
    def save_trades(self):
        """Save trades to file"""
        today = datetime.now(IST).strftime('%Y-%m-%d')
        filepath = self.data_dir / f"trades_{today}.json"
        
        data = {
            'date': today,
            'closed_trades': [asdict(t) for t in self.closed_trades],
            'open_trades': [asdict(t) for t in self.open_trades.values()],
        }
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"✅ Trades saved to {filepath}")
    
    def load_trades(self, date_str: str = None):
        """Load trades from file"""
        if date_str is None:
            date_str = datetime.now(IST).strftime('%Y-%m-%d')
        
        filepath = self.data_dir / f"trades_{date_str}.json"
        
        if not filepath.exists():
            print(f"⚠ No trade file for {date_str}")
            return
        
        with open(filepath, 'r') as f:
            data = json.load(f)
        
        self.closed_trades = [TrackedTrade(**t) for t in data.get('closed_trades', [])]
        
        print(f"✅ Loaded {len(self.closed_trades)} trades from {date_str}")
    
    # =========================================================================
    # OPEN TRADES STATUS
    # =========================================================================
    
    def get_open_trades_summary(self) -> str:
        """Get summary of open trades"""
        if not self.open_trades:
            return "No open trades"
        
        msg = f"""
📋 <b>OPEN TRADES STATUS</b>

⏰ {datetime.now(IST).strftime('%H:%M:%S')}

"""
        for trade in self.open_trades.values():
            msg += f"""
<b>{trade.symbol} | {trade.strategy}</b>
• Entry: ₹{trade.entry_premium:.2f} at {trade.entry_time}
• Current SL: ₹{trade.current_sl:.2f}
• Target: ₹{trade.target:.2f}
• Trails: {trade.trail_count}
"""
        
        return msg


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

tracker = TradeResultTracker()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def record_trade_entry(symbol: str, strategy: str, entry_premium: float,
                       quantity: int, lot_size: int, sl: float, target: float,
                       confidence: int = 0, win_probability: float = 0.0) -> TrackedTrade:
    """Record a new trade entry"""
    return tracker.record_entry(symbol, strategy, entry_premium, quantity, 
                                lot_size, sl, target, confidence, win_probability)


def record_trade_exit(trade_id: str, exit_premium: float, 
                      exit_reason: TradeStatus) -> Optional[TrackedTrade]:
    """Record trade exit"""
    return tracker.record_exit(trade_id, exit_premium, exit_reason)


def send_daily_trade_summary():
    """Send daily summary"""
    tracker.send_daily_summary()


def save_all_trades():
    """Save trades to file"""
    tracker.save_trades()


# =============================================================================
# TEST FUNCTION
# =============================================================================

def test_trade_tracking():
    """Test the trade tracking system"""
    
    # Record a winning trade
    trade1 = tracker.record_entry(
        symbol="NIFTY",
        strategy="Short Straddle",
        entry_premium=250.0,
        quantity=75,
        lot_size=75,
        sl=325.0,
        target=125.0,
        confidence=75,
        win_probability=65.0,
    )
    
    # Simulate exit at target
    tracker.record_exit(trade1.trade_id, 120.0, TradeStatus.CLOSED_TARGET)
    
    # Record a losing trade
    trade2 = tracker.record_entry(
        symbol="BANKNIFTY",
        strategy="Short Strangle",
        entry_premium=180.0,
        quantity=30,
        lot_size=30,
        sl=270.0,
        target=90.0,
        confidence=68,
        win_probability=60.0,
    )
    
    # Simulate exit at SL
    tracker.record_exit(trade2.trade_id, 275.0, TradeStatus.CLOSED_SL)
    
    # Send daily summary
    tracker.send_daily_summary()
    
    # Save trades
    tracker.save_trades()
    
    print("\n✅ Test complete!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Trade Result Tracker')
    parser.add_argument('--test', action='store_true', help='Run test')
    parser.add_argument('--summary', action='store_true', help='Send daily summary')
    
    args = parser.parse_args()
    
    if args.test:
        test_trade_tracking()
    elif args.summary:
        tracker.load_trades()
        tracker.send_daily_summary()
    else:
        print("Trade Result Tracker")
        print("Usage:")
        print("  --test     Run test (sends sample alerts)")
        print("  --summary  Send daily summary")
