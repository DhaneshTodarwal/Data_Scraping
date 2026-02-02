"""
Auto-Close Trade Monitor
=========================
Monitors open positions and auto-closes when:
- Stop Loss is hit
- Target is hit
- Time exit (3:20 PM for intraday)
"""
import sys
import time
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from notifications import send_telegram_message
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False

try:
    from paper_trading_platform import get_platform
    PAPER_TRADING_OK = True
except ImportError:
    PAPER_TRADING_OK = False

try:
    from real_option_prices import get_real_option_price
    REAL_PRICES_OK = True
except ImportError:
    REAL_PRICES_OK = False


class AutoCloseMonitor:
    """
    Monitors positions and auto-closes on SL/TGT/Time
    """
    
    def __init__(self, 
                 sl_percent: float = 30.0,    # 30% SL
                 target_percent: float = 50.0, # 50% target
                 time_exit: str = "15:20"):    # 3:20 PM exit
        
        self.sl_percent = sl_percent
        self.target_percent = target_percent
        self.time_exit = datetime.strptime(time_exit, "%H:%M").time()
        
        self.running = False
        self.check_interval = 60  # seconds
    
    def check_sl_target(self, trade) -> Optional[str]:
        """Check if trade should be closed"""
        
        # Calculate current P&L %
        entry_value = abs(trade.entry_premium) * trade.lot_size
        if entry_value == 0:
            return None
        
        pnl_percent = (trade.pnl_amount / entry_value) * 100
        
        # Check Target (positive P&L)
        if pnl_percent >= self.target_percent:
            return f"TARGET HIT ({pnl_percent:.1f}% profit)"
        
        # Check SL (negative P&L)
        if pnl_percent <= -self.sl_percent:
            return f"STOP LOSS HIT ({pnl_percent:.1f}% loss)"
        
        return None
    
    def check_time_exit(self) -> bool:
        """Check if it's time to exit all positions"""
        now = datetime.now(IST).time()
        return now >= self.time_exit
    
    def send_close_alert(self, trade, reason: str):
        """Send alert when trade is closed"""
        emoji = "🟢" if trade.pnl_amount >= 0 else "🔴"
        
        msg = f"""
🔔 <b>AUTO-CLOSE ALERT</b>

{emoji} <b>Trade Closed!</b>

📋 <b>Trade ID:</b> {trade.trade_id}
📈 <b>Symbol:</b> {trade.symbol}
📊 <b>Strategy:</b> {trade.strategy}

💰 <b>P&L:</b> ₹{trade.pnl_amount:+,.0f}

📝 <b>Reason:</b> {reason}

⏰ {datetime.now(IST).strftime('%H:%M:%S')}
"""
        if TELEGRAM_OK:
            send_telegram_message(msg)
        else:
            print(msg)
    
    def monitor_once(self):
        """Run one monitoring cycle"""
        if not PAPER_TRADING_OK:
            return
        
        platform = get_platform()
        
        # Update all positions with current prices
        platform.update_positions()
        
        # Check time exit first
        if self.check_time_exit():
            for trade_id in list(platform.open_trades.keys()):
                trade = platform.close_trade(trade_id, "Time Exit (3:20 PM)")
                if trade:
                    self.send_close_alert(trade, "TIME EXIT - Market closing")
            return
        
        # Check each position for SL/Target
        for trade_id, trade in list(platform.open_trades.items()):
            exit_reason = self.check_sl_target(trade)
            
            if exit_reason:
                closed_trade = platform.close_trade(trade_id, exit_reason)
                if closed_trade:
                    self.send_close_alert(closed_trade, exit_reason)
    
    def run(self):
        """Run continuous monitoring"""
        print("🔍 Auto-close monitor started!")
        print(f"   SL: {self.sl_percent}%")
        print(f"   Target: {self.target_percent}%")
        print(f"   Time Exit: {self.time_exit}")
        
        self.running = True
        
        while self.running:
            try:
                now = datetime.now(IST)
                
                # Only run during market hours
                if now.hour >= 9 and now.hour < 16:
                    self.monitor_once()
                
                time.sleep(self.check_interval)
                
            except KeyboardInterrupt:
                print("\n⏹ Monitor stopped")
                break
            except Exception as e:
                print(f"Monitor error: {e}")
                time.sleep(60)
    
    def stop(self):
        """Stop monitoring"""
        self.running = False


# Singleton
_monitor = None


def get_monitor() -> AutoCloseMonitor:
    global _monitor
    if _monitor is None:
        _monitor = AutoCloseMonitor()
    return _monitor


def run_monitor():
    """Run the auto-close monitor"""
    get_monitor().run()


def check_once():
    """Run one monitoring check"""
    get_monitor().monitor_once()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true', help='Run monitor')
    parser.add_argument('--check', action='store_true', help='Check once')
    parser.add_argument('--sl', type=float, default=30, help='SL percent')
    parser.add_argument('--target', type=float, default=50, help='Target percent')
    
    args = parser.parse_args()
    
    if args.run:
        monitor = AutoCloseMonitor(sl_percent=args.sl, target_percent=args.target)
        monitor.run()
    elif args.check:
        check_once()
        print("✅ Check complete")
    else:
        print("Auto-Close Monitor")
        print("  --run     Run continuous monitor")
        print("  --check   Check once")
        print("  --sl      SL percentage (default: 30)")
        print("  --target  Target percentage (default: 50)")
