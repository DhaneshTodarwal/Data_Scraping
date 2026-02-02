"""
Trading Alerts Module
=======================
Extends existing notification system for real-time trading alerts
Uses the existing Telegram bot from scripts/notifications.py
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

# Add paths
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

# Import existing notifications
try:
    from notifications import send_telegram_message, send_desktop_notification
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False
    print("⚠ notifications module not found. Install in scripts/notifications.py")


IST = timezone(timedelta(hours=5, minutes=30))


class TradingAlerter:
    """Send trading alerts via Telegram and Desktop"""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled and NOTIFICATIONS_AVAILABLE
    
    def alert_signal(self, signal: Dict) -> bool:
        """
        Alert when a new signal is generated
        
        Signal format:
        {
            'symbol': 'NIFTY',
            'strategy': 'Short Straddle',
            'type': 'SELL',
            'strike': 24500,
            'entry_price': 250,
            'stop_loss': 325,
            'target': 125,
            'time': '10:30'
        }
        """
        if not self.enabled:
            return False
        
        now = datetime.now(IST).strftime('%H:%M:%S')
        
        msg = f"""
🚨 <b>NEW TRADING SIGNAL</b>

📈 <b>Symbol:</b> {signal.get('symbol', 'N/A')}
🎯 <b>Strategy:</b> {signal.get('strategy', 'N/A')}

<b>📊 Trade Details:</b>
• Type: {signal.get('type', 'SELL')}
• Strike: {signal.get('strike', 'ATM')}
• Entry Premium: ₹{signal.get('entry_price', 0):.2f}
• Stop Loss: ₹{signal.get('stop_loss', 0):.2f}
• Target: ₹{signal.get('target', 0):.2f}

⏰ Signal Time: {now}
"""
        
        return send_telegram_message(msg)
    
    def alert_entry(self, trade: Dict) -> bool:
        """Alert when entering a trade"""
        if not self.enabled:
            return False
        
        now = datetime.now(IST).strftime('%H:%M:%S')
        
        msg = f"""
✅ <b>TRADE ENTRY</b>

📈 <b>{trade.get('symbol', 'N/A')}</b> - {trade.get('strategy', 'Strategy')}

• Action: {trade.get('action', 'SELL')}
• Strike: {trade.get('strike', 'ATM')}
• Premium: ₹{trade.get('premium', 0):.2f}
• Quantity: {trade.get('quantity', 1)} lot(s)

🎯 Target: ₹{trade.get('target', 0):.2f}
🛑 Stop Loss: ₹{trade.get('stop_loss', 0):.2f}

⏰ Entry Time: {now}
"""
        
        send_desktop_notification("✅ Trade Entry", f"{trade.get('symbol')} - {trade.get('strategy')}")
        return send_telegram_message(msg)
    
    def alert_exit(self, trade: Dict) -> bool:
        """Alert when exiting a trade"""
        if not self.enabled:
            return False
        
        now = datetime.now(IST).strftime('%H:%M:%S')
        pnl = trade.get('pnl', 0)
        pnl_emoji = "🟢" if pnl >= 0 else "🔴"
        
        msg = f"""
{pnl_emoji} <b>TRADE EXIT</b>

📈 <b>{trade.get('symbol', 'N/A')}</b> - {trade.get('strategy', 'Strategy')}

• Exit Reason: {trade.get('exit_reason', 'Manual')}
• Entry: ₹{trade.get('entry_price', 0):.2f}
• Exit: ₹{trade.get('exit_price', 0):.2f}

💰 <b>P&L: ₹{pnl:,.2f}</b>

⏰ Exit Time: {now}
"""
        
        urgency = "normal" if pnl >= 0 else "critical"
        send_desktop_notification(f"{'✅' if pnl >= 0 else '❌'} Trade Exit", f"P&L: ₹{pnl:,.0f}")
        return send_telegram_message(msg)
    
    def alert_daily_summary(self, summary: Dict) -> bool:
        """Send daily trading summary"""
        if not self.enabled:
            return False
        
        date = datetime.now(IST).strftime('%Y-%m-%d')
        total_pnl = summary.get('total_pnl', 0)
        pnl_emoji = "🟢" if total_pnl >= 0 else "🔴"
        
        msg = f"""
📊 <b>DAILY TRADING SUMMARY</b>
📅 {date}

<b>📈 Performance:</b>
• Total Trades: {summary.get('total_trades', 0)}
• Winners: {summary.get('winners', 0)}
• Losers: {summary.get('losers', 0)}
• Win Rate: {summary.get('win_rate', 0):.1f}%

{pnl_emoji} <b>Total P&L: ₹{total_pnl:,.2f}</b>

<b>🏆 Best Trade:</b> ₹{summary.get('max_win', 0):,.2f}
<b>💔 Worst Trade:</b> ₹{summary.get('max_loss', 0):,.2f}

📈 Capital: ₹{summary.get('capital', 0):,.2f}
"""
        
        return send_telegram_message(msg)
    
    def alert_risk_warning(self, warning: str, severity: str = 'warning') -> bool:
        """Alert for risk warnings"""
        if not self.enabled:
            return False
        
        now = datetime.now(IST).strftime('%H:%M:%S')
        emoji = "⚠️" if severity == 'warning' else "🚨"
        
        msg = f"""
{emoji} <b>RISK ALERT</b>

{warning}

⏰ Time: {now}
"""
        
        urgency = "critical" if severity == 'critical' else "normal"
        send_desktop_notification(f"{emoji} Risk Warning", warning, urgency)
        return send_telegram_message(msg)
    
    def alert_market_open(self, market_data: Dict) -> bool:
        """Alert at market open with key levels"""
        if not self.enabled:
            return False
        
        date = datetime.now(IST).strftime('%Y-%m-%d')
        
        msg = f"""
🔔 <b>MARKET OPEN</b>
📅 {date}

<b>📈 NIFTY</b>
• Spot: ₹{market_data.get('nifty_spot', 0):,.2f}
• ATM: {market_data.get('nifty_atm', 'N/A')}

<b>📈 BANKNIFTY</b>
• Spot: ₹{market_data.get('banknifty_spot', 0):,.2f}
• ATM: {market_data.get('banknifty_atm', 'N/A')}

<b>🎯 Today's Strategies:</b>
• Short Straddle Entry: 09:45
• Target: 50% | SL: 30%

Good luck! 🚀
"""
        
        send_desktop_notification("🔔 Market Open", f"NIFTY: ₹{market_data.get('nifty_spot', 0):,.0f}")
        return send_telegram_message(msg)


# Singleton instance
alerter = TradingAlerter()


# Convenience functions
def alert_signal(signal: Dict) -> bool:
    return alerter.alert_signal(signal)

def alert_entry(trade: Dict) -> bool:
    return alerter.alert_entry(trade)

def alert_exit(trade: Dict) -> bool:
    return alerter.alert_exit(trade)

def send_daily_summary(summary: Dict) -> bool:
    return alerter.alert_daily_summary(summary)


if __name__ == "__main__":
    print("\n=== Testing Trading Alerts ===\n")
    
    if not NOTIFICATIONS_AVAILABLE:
        print("❌ Notifications not available")
        exit(1)
    
    # Test signal alert
    test_signal = {
        'symbol': 'NIFTY',
        'strategy': 'Short Straddle',
        'type': 'SELL',
        'strike': 24500,
        'entry_price': 250,
        'stop_loss': 325,
        'target': 125,
    }
    
    print("Sending test signal alert...")
    alert_signal(test_signal)
    
    print("\n✅ Test complete!")
