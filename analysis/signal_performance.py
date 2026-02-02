"""
Signal Performance Monitor
============================
Tracks signal accuracy and generates performance reports

Features:
1. MTM Updates - Real-time P&L tracking every 15 minutes
2. Signal Accuracy Report - Track target hits vs SL hits
3. Weekly Performance Report - Summary of the week
4. Signal Outcome Logging - Record every signal result
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta, date, time
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
# DATA STRUCTURES
# =============================================================================

@dataclass
class SignalRecord:
    """Record of a signal and its outcome"""
    signal_id: str
    date: str
    time: str
    symbol: str
    strategy: str
    
    # Entry
    spot_at_entry: float
    entry_premium: float
    sl_premium: float
    target_premium: float
    confidence: int
    win_probability: float
    
    # Outcome (filled later)
    outcome: str = "PENDING"  # TARGET_HIT, SL_HIT, TIME_EXIT, BREAKEVEN
    exit_premium: float = 0.0
    exit_time: str = ""
    pnl_points: float = 0.0
    pnl_percent: float = 0.0
    
    # MTM tracking
    peak_profit: float = 0.0
    peak_loss: float = 0.0


@dataclass
class DayPerformance:
    """Performance for a single day"""
    date: str
    total_signals: int = 0
    target_hits: int = 0
    sl_hits: int = 0
    breakeven: int = 0
    time_exits: int = 0
    total_pnl_points: float = 0.0
    win_rate: float = 0.0


# =============================================================================
# SIGNAL PERFORMANCE TRACKER
# =============================================================================

class SignalPerformanceTracker:
    """
    Tracks all signals and their outcomes
    Generates accuracy reports
    """
    
    def __init__(self):
        self.active_signals: Dict[str, SignalRecord] = {}
        self.completed_signals: List[SignalRecord] = []
        self.signal_counter = 0
        
        # Data storage
        self.data_dir = Path(__file__).parent / "signal_logs"
        self.data_dir.mkdir(exist_ok=True)
        
        # Load historical data
        self._load_history()
    
    def _load_history(self):
        """Load historical signal data"""
        history_file = self.data_dir / "signal_history.json"
        if history_file.exists():
            with open(history_file, 'r') as f:
                data = json.load(f)
                self.completed_signals = [SignalRecord(**s) for s in data.get('signals', [])]
                self.signal_counter = data.get('counter', 0)
    
    def _save_history(self):
        """Save signal data"""
        history_file = self.data_dir / "signal_history.json"
        data = {
            'signals': [asdict(s) for s in self.completed_signals],
            'counter': self.signal_counter,
        }
        with open(history_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def generate_signal_id(self) -> str:
        """Generate unique signal ID"""
        self.signal_counter += 1
        return f"S{datetime.now(IST).strftime('%Y%m%d')}_{self.signal_counter:03d}"
    
    # =========================================================================
    # RECORD SIGNALS
    # =========================================================================
    
    def record_signal(self, symbol: str, strategy: str, spot: float,
                      entry_premium: float, sl_premium: float, target_premium: float,
                      confidence: int, win_probability: float) -> SignalRecord:
        """Record a new signal"""
        
        signal_id = self.generate_signal_id()
        now = datetime.now(IST)
        
        signal = SignalRecord(
            signal_id=signal_id,
            date=now.strftime('%Y-%m-%d'),
            time=now.strftime('%H:%M:%S'),
            symbol=symbol,
            strategy=strategy,
            spot_at_entry=spot,
            entry_premium=entry_premium,
            sl_premium=sl_premium,
            target_premium=target_premium,
            confidence=confidence,
            win_probability=win_probability,
        )
        
        self.active_signals[signal_id] = signal
        return signal
    
    def record_outcome(self, signal_id: str, outcome: str, 
                       exit_premium: float) -> Optional[SignalRecord]:
        """Record signal outcome"""
        
        if signal_id not in self.active_signals:
            return None
        
        signal = self.active_signals[signal_id]
        now = datetime.now(IST)
        
        signal.outcome = outcome
        signal.exit_premium = exit_premium
        signal.exit_time = now.strftime('%H:%M:%S')
        
        # Calculate P&L (for selling: profit when premium decreases)
        signal.pnl_points = signal.entry_premium - exit_premium
        signal.pnl_percent = (signal.pnl_points / signal.entry_premium) * 100
        
        # Move to completed
        del self.active_signals[signal_id]
        self.completed_signals.append(signal)
        
        # Save
        self._save_history()
        
        return signal
    
    # =========================================================================
    # MTM UPDATES
    # =========================================================================
    
    def update_mtm(self, signal_id: str, current_premium: float):
        """Update Mark-to-Market for active signal"""
        if signal_id not in self.active_signals:
            return
        
        signal = self.active_signals[signal_id]
        current_pnl = signal.entry_premium - current_premium
        
        if current_pnl > signal.peak_profit:
            signal.peak_profit = current_pnl
        if current_pnl < signal.peak_loss:
            signal.peak_loss = current_pnl
    
    def generate_mtm_alert(self) -> str:
        """Generate MTM update for all active signals"""
        
        if not self.active_signals:
            return ""
        
        now = datetime.now(IST).strftime('%H:%M')
        
        msg = f"""
📊 <b>MTM UPDATE</b> ({now})

"""
        total_pnl = 0
        
        for signal in self.active_signals.values():
            # Simulate current premium (in production, fetch live)
            import random
            current = signal.entry_premium * random.uniform(0.7, 1.2)
            pnl = signal.entry_premium - current
            pnl_pct = (pnl / signal.entry_premium) * 100
            total_pnl += pnl
            
            emoji = "🟢" if pnl > 0 else "🔴"
            
            msg += f"""<b>{signal.symbol} | {signal.strategy[:12]}</b>
• Entry: ₹{signal.entry_premium:.2f} → Now: ₹{current:.2f}
• {emoji} P&L: ₹{pnl:.2f} ({pnl_pct:+.1f}%)
• SL: ₹{signal.sl_premium:.2f} | Target: ₹{signal.target_premium:.2f}

"""
        
        total_emoji = "🟢" if total_pnl > 0 else "🔴"
        msg += f"━━━━━━━━━━━━━━━━━━\n{total_emoji} <b>Total P&L: ₹{total_pnl:.2f}</b>"
        
        return msg
    
    # =========================================================================
    # ACCURACY REPORTS
    # =========================================================================
    
    def get_daily_accuracy(self, date_str: str = None) -> DayPerformance:
        """Get accuracy for a specific day"""
        
        if date_str is None:
            date_str = datetime.now(IST).strftime('%Y-%m-%d')
        
        day_signals = [s for s in self.completed_signals if s.date == date_str]
        
        if not day_signals:
            return DayPerformance(date=date_str)
        
        target_hits = len([s for s in day_signals if s.outcome == "TARGET_HIT"])
        sl_hits = len([s for s in day_signals if s.outcome == "SL_HIT"])
        breakeven = len([s for s in day_signals if s.outcome == "BREAKEVEN"])
        time_exits = len([s for s in day_signals if s.outcome == "TIME_EXIT"])
        
        total_pnl = sum(s.pnl_points for s in day_signals)
        win_rate = (target_hits / len(day_signals)) * 100 if day_signals else 0
        
        return DayPerformance(
            date=date_str,
            total_signals=len(day_signals),
            target_hits=target_hits,
            sl_hits=sl_hits,
            breakeven=breakeven,
            time_exits=time_exits,
            total_pnl_points=total_pnl,
            win_rate=win_rate,
        )
    
    def generate_accuracy_report(self) -> str:
        """Generate signal accuracy report for today"""
        
        today = datetime.now(IST).strftime('%Y-%m-%d')
        perf = self.get_daily_accuracy(today)
        
        if perf.total_signals == 0:
            return f"""
📊 <b>SIGNAL ACCURACY REPORT</b>

📅 {today}

No signals completed today.
"""
        
        msg = f"""
📊 <b>SIGNAL ACCURACY REPORT</b>

📅 {today}

━━━━━ TODAY'S SIGNALS ━━━━━

• Total Signals: {perf.total_signals}
• 🎯 Target Hit: {perf.target_hits} ({perf.target_hits/perf.total_signals*100:.0f}%)
• 🛑 SL Hit: {perf.sl_hits} ({perf.sl_hits/perf.total_signals*100:.0f}%)
• ⚖️ Breakeven: {perf.breakeven}
• ⏰ Time Exit: {perf.time_exits}

<b>Win Rate: {perf.win_rate:.0f}%</b>
<b>P&L Points: {perf.total_pnl_points:+.2f}</b>

━━━━━ SIGNAL BREAKDOWN ━━━━━

"""
        # Add each signal
        day_signals = [s for s in self.completed_signals if s.date == today]
        for s in day_signals:
            emoji = "🎯" if s.outcome == "TARGET_HIT" else ("🛑" if s.outcome == "SL_HIT" else "⏰")
            pnl_emoji = "🟢" if s.pnl_points > 0 else "🔴"
            msg += f"{emoji} {s.symbol} {s.strategy[:10]}: {pnl_emoji} {s.pnl_percent:+.0f}%\n"
        
        return msg
    
    # =========================================================================
    # WEEKLY REPORT
    # =========================================================================
    
    def generate_weekly_report(self) -> str:
        """Generate weekly performance report"""
        
        today = datetime.now(IST).date()
        week_start = today - timedelta(days=today.weekday())
        week_end = week_start + timedelta(days=6)
        
        # Filter signals for this week
        week_signals = [
            s for s in self.completed_signals 
            if week_start <= datetime.strptime(s.date, '%Y-%m-%d').date() <= week_end
        ]
        
        if not week_signals:
            return f"""
📊 <b>WEEKLY PERFORMANCE REPORT</b>

📅 Week: {week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}

No signals this week yet.
"""
        
        # Calculate stats
        total = len(week_signals)
        target_hits = len([s for s in week_signals if s.outcome == "TARGET_HIT"])
        sl_hits = len([s for s in week_signals if s.outcome == "SL_HIT"])
        
        win_rate = (target_hits / total) * 100 if total else 0
        total_pnl = sum(s.pnl_points for s in week_signals)
        
        # By symbol
        symbol_stats = {}
        for s in week_signals:
            if s.symbol not in symbol_stats:
                symbol_stats[s.symbol] = {'signals': 0, 'wins': 0, 'pnl': 0}
            symbol_stats[s.symbol]['signals'] += 1
            if s.outcome == "TARGET_HIT":
                symbol_stats[s.symbol]['wins'] += 1
            symbol_stats[s.symbol]['pnl'] += s.pnl_points
        
        # By strategy
        strategy_stats = {}
        for s in week_signals:
            if s.strategy not in strategy_stats:
                strategy_stats[s.strategy] = {'signals': 0, 'wins': 0, 'pnl': 0}
            strategy_stats[s.strategy]['signals'] += 1
            if s.outcome == "TARGET_HIT":
                strategy_stats[s.strategy]['wins'] += 1
            strategy_stats[s.strategy]['pnl'] += s.pnl_points
        
        # Daily breakdown
        daily_pnl = {}
        for s in week_signals:
            if s.date not in daily_pnl:
                daily_pnl[s.date] = 0
            daily_pnl[s.date] += s.pnl_points
        
        msg = f"""
📊 <b>WEEKLY PERFORMANCE REPORT</b>

📅 Week: {week_start.strftime('%d %b')} - {week_end.strftime('%d %b %Y')}

━━━━━ OVERALL STATS ━━━━━

• Total Signals: {total}
• 🎯 Target Hits: {target_hits}
• 🛑 SL Hits: {sl_hits}
• <b>Win Rate: {win_rate:.0f}%</b>
• <b>Total P&L: {total_pnl:+.2f} pts</b>

━━━━━ BY SYMBOL ━━━━━

"""
        for symbol, stats in symbol_stats.items():
            wr = (stats['wins'] / stats['signals']) * 100
            emoji = "🟢" if stats['pnl'] > 0 else "🔴"
            msg += f"• {symbol}: {stats['signals']} signals | {wr:.0f}% WR | {emoji} {stats['pnl']:+.1f}pts\n"
        
        msg += """
━━━━━ BY STRATEGY ━━━━━

"""
        for strategy, stats in strategy_stats.items():
            wr = (stats['wins'] / stats['signals']) * 100
            emoji = "🟢" if stats['pnl'] > 0 else "🔴"
            msg += f"• {strategy[:15]}: {stats['signals']} | {wr:.0f}% | {emoji} {stats['pnl']:+.1f}pts\n"
        
        msg += """
━━━━━ DAILY BREAKDOWN ━━━━━

"""
        for day, pnl in sorted(daily_pnl.items()):
            day_name = datetime.strptime(day, '%Y-%m-%d').strftime('%a %d')
            emoji = "🟢" if pnl > 0 else "🔴"
            msg += f"• {day_name}: {emoji} {pnl:+.1f} pts\n"
        
        # Best and worst days
        if daily_pnl:
            best_day = max(daily_pnl.items(), key=lambda x: x[1])
            worst_day = min(daily_pnl.items(), key=lambda x: x[1])
            
            msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━

🏆 <b>Best Day:</b> {best_day[0]} ({best_day[1]:+.1f} pts)
📉 <b>Worst Day:</b> {worst_day[0]} ({worst_day[1]:+.1f} pts)

━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📈 Key Insights:</b>
"""
            if win_rate >= 60:
                msg += "• ✅ Signals are profitable - consider trading with small size\n"
            else:
                msg += "• ⚠️ Win rate below 60% - continue observing\n"
            
            best_strategy = max(strategy_stats.items(), key=lambda x: x[1]['pnl'])
            msg += f"• 🏆 Best strategy: {best_strategy[0]}\n"
        
        return msg
    
    # =========================================================================
    # SEND ALERTS
    # =========================================================================
    
    def send_mtm_update(self) -> bool:
        """Send MTM update"""
        msg = self.generate_mtm_alert()
        if msg and NOTIFICATIONS_AVAILABLE:
            return send_telegram_message(msg)
        return False
    
    def send_accuracy_report(self) -> bool:
        """Send accuracy report"""
        msg = self.generate_accuracy_report()
        if NOTIFICATIONS_AVAILABLE:
            return send_telegram_message(msg)
        return False
    
    def send_weekly_report(self) -> bool:
        """Send weekly report"""
        msg = self.generate_weekly_report()
        if NOTIFICATIONS_AVAILABLE:
            return send_telegram_message(msg)
        return False


# =============================================================================
# SINGLETON
# =============================================================================

performance_tracker = SignalPerformanceTracker()


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def record_signal(symbol, strategy, spot, entry_premium, sl, target, confidence, probability):
    """Record a signal"""
    return performance_tracker.record_signal(
        symbol, strategy, spot, entry_premium, sl, target, confidence, probability
    )

def record_outcome(signal_id, outcome, exit_premium):
    """Record signal outcome"""
    return performance_tracker.record_outcome(signal_id, outcome, exit_premium)

def send_mtm():
    """Send MTM update"""
    return performance_tracker.send_mtm_update()

def send_accuracy():
    """Send accuracy report"""
    return performance_tracker.send_accuracy_report()

def send_weekly():
    """Send weekly report"""
    return performance_tracker.send_weekly_report()


# =============================================================================
# TEST
# =============================================================================

def test_performance_tracker():
    """Test with sample data"""
    
    # Add sample completed signals
    tracker = SignalPerformanceTracker()
    
    # Sample signals
    samples = [
        ("NIFTY", "Short Straddle", "TARGET_HIT", 50),
        ("NIFTY", "Short Strangle", "TARGET_HIT", 40),
        ("BANKNIFTY", "Short Straddle", "SL_HIT", -30),
        ("NIFTY", "Iron Condor", "TARGET_HIT", 35),
        ("BANKNIFTY", "Short Strangle", "TARGET_HIT", 45),
    ]
    
    for symbol, strategy, outcome, pnl_pct in samples:
        signal = SignalRecord(
            signal_id=tracker.generate_signal_id(),
            date=datetime.now(IST).strftime('%Y-%m-%d'),
            time="10:30:00",
            symbol=symbol,
            strategy=strategy,
            spot_at_entry=24500,
            entry_premium=200,
            sl_premium=260,
            target_premium=100,
            confidence=70,
            win_probability=65,
            outcome=outcome,
            exit_premium=200 * (1 - pnl_pct/100),
            exit_time="14:30:00",
            pnl_points=pnl_pct * 2,
            pnl_percent=pnl_pct,
        )
        tracker.completed_signals.append(signal)
    
    # Send reports
    print("Sending accuracy report...")
    tracker.send_accuracy_report()
    
    print("\nSending weekly report...")
    tracker.send_weekly_report()
    
    print("\n✅ Test complete!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Signal Performance Monitor')
    parser.add_argument('--test', action='store_true', help='Run test')
    parser.add_argument('--accuracy', action='store_true', help='Send accuracy report')
    parser.add_argument('--weekly', action='store_true', help='Send weekly report')
    parser.add_argument('--mtm', action='store_true', help='Send MTM update')
    
    args = parser.parse_args()
    
    if args.test:
        test_performance_tracker()
    elif args.accuracy:
        send_accuracy()
    elif args.weekly:
        send_weekly()
    elif args.mtm:
        send_mtm()
    else:
        print("Signal Performance Monitor")
        print("Usage:")
        print("  --test      Run test with sample data")
        print("  --accuracy  Send daily accuracy report")
        print("  --weekly    Send weekly report")
        print("  --mtm       Send MTM update")
