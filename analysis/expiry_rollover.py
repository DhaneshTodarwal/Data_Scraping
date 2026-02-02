"""
Expiry Rollover Suggestions
============================
Monitors open positions and suggests:
- When to rollover to next expiry
- Best rollover time (1-2 days before expiry)
- Auto-alerts for upcoming expiry
"""
import sys
from pathlib import Path
from datetime import datetime, date, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from notifications import send_telegram_message
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False


class ExpiryRollover:
    """Manages expiry dates and rollover suggestions"""
    
    def __init__(self):
        # Weekly expiry days
        self.expiry_days = {
            'NIFTY': 3,       # Thursday
            'BANKNIFTY': 2,   # Wednesday  
            'FINNIFTY': 1,    # Tuesday
            'MIDCPNIFTY': 0,  # Monday
        }
    
    def get_current_expiry(self, symbol: str) -> date:
        """Get current week's expiry date for symbol"""
        today = datetime.now(IST).date()
        expiry_day = self.expiry_days.get(symbol, 3)  # Default Thursday
        
        days_until_expiry = (expiry_day - today.weekday()) % 7
        if days_until_expiry == 0 and datetime.now(IST).hour < 15:
            # Expiry is today but before market close
            return today
        elif days_until_expiry == 0:
            # Expiry was today, get next week
            days_until_expiry = 7
        
        return today + timedelta(days=days_until_expiry)
    
    def get_next_expiry(self, symbol: str) -> date:
        """Get next week's expiry date"""
        current = self.get_current_expiry(symbol)
        return current + timedelta(days=7)
    
    def days_to_expiry(self, symbol: str) -> int:
        """Get days until current expiry"""
        today = datetime.now(IST).date()
        expiry = self.get_current_expiry(symbol)
        return (expiry - today).days
    
    def should_rollover(self, symbol: str) -> bool:
        """Check if position should be rolled over"""
        days = self.days_to_expiry(symbol)
        # Suggest rollover 1-2 days before expiry
        return days <= 1
    
    def get_rollover_suggestion(self, symbol: str, strategy: str = None) -> dict:
        """Get rollover suggestion for a symbol"""
        
        current_expiry = self.get_current_expiry(symbol)
        next_expiry = self.get_next_expiry(symbol)
        days_left = self.days_to_expiry(symbol)
        should_roll = self.should_rollover(symbol)
        
        suggestion = {
            'symbol': symbol,
            'current_expiry': current_expiry.strftime('%Y-%m-%d'),
            'next_expiry': next_expiry.strftime('%Y-%m-%d'),
            'days_to_expiry': days_left,
            'should_rollover': should_roll,
            'urgency': 'HIGH' if days_left == 0 else 'MEDIUM' if days_left == 1 else 'LOW',
            'action': '',
        }
        
        if days_left == 0:
            suggestion['action'] = "⚠️ EXPIRY TODAY! Close position or rollover NOW!"
        elif days_left == 1:
            suggestion['action'] = "📍 Rollover Tomorrow - Consider rolling today for better prices"
        elif days_left == 2:
            suggestion['action'] = "✅ Good time to rollover - Premium decay is optimal"
        else:
            suggestion['action'] = f"⏳ {days_left} days to expiry - No action needed yet"
        
        return suggestion
    
    def generate_rollover_alert(self, symbol: str) -> str:
        """Generate Telegram alert for rollover"""
        
        sugg = self.get_rollover_suggestion(symbol)
        
        urgency_emoji = {
            'HIGH': '🔴',
            'MEDIUM': '🟡',
            'LOW': '🟢',
        }
        
        msg = f"""
📆 <b>EXPIRY ROLLOVER ALERT</b>

📈 <b>Symbol:</b> {symbol}
📅 <b>Current Expiry:</b> {sugg['current_expiry']}
⏰ <b>Days Left:</b> {sugg['days_to_expiry']}

{urgency_emoji.get(sugg['urgency'], '⚪')} <b>Urgency:</b> {sugg['urgency']}

<b>Action:</b> {sugg['action']}

📅 <b>Next Expiry:</b> {sugg['next_expiry']}

💡 <i>Rollover = Close current + Open new in next expiry</i>
"""
        return msg
    
    def check_all_symbols(self):
        """Check all symbols and send alerts if needed"""
        
        for symbol in ['NIFTY', 'BANKNIFTY']:
            days_left = self.days_to_expiry(symbol)
            
            # Alert if 2 or fewer days to expiry
            if days_left <= 2:
                msg = self.generate_rollover_alert(symbol)
                
                if TELEGRAM_OK:
                    send_telegram_message(msg)
                else:
                    print(msg)
    
    def get_expiry_info_message(self) -> str:
        """Get expiry info for all symbols"""
        
        msg = """
📆 <b>EXPIRY SCHEDULE</b>

"""
        for symbol in ['NIFTY', 'BANKNIFTY', 'FINNIFTY']:
            expiry = self.get_current_expiry(symbol)
            days = self.days_to_expiry(symbol)
            
            urgency = "🔴" if days <= 1 else "🟡" if days <= 2 else "🟢"
            
            msg += f"{urgency} <b>{symbol}:</b> {expiry.strftime('%d %b')} ({days} days)\n"
        
        msg += """
━━━━━━━━━━━━━━━━━━━━━━━━

<b>Weekly Expiry Days:</b>
• NIFTY: Thursday
• BANKNIFTY: Wednesday
• FINNIFTY: Tuesday
"""
        return msg


# Singleton
_rollover = None


def get_rollover() -> ExpiryRollover:
    global _rollover
    if _rollover is None:
        _rollover = ExpiryRollover()
    return _rollover


def check_rollovers():
    """Check and send rollover alerts"""
    get_rollover().check_all_symbols()


def get_expiry_info():
    """Get expiry info message"""
    return get_rollover().get_expiry_info_message()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Check and alert')
    parser.add_argument('--info', action='store_true', help='Show expiry info')
    
    args = parser.parse_args()
    
    rollover = ExpiryRollover()
    
    if args.check:
        rollover.check_all_symbols()
        print("✅ Rollover check complete")
    elif args.info:
        msg = rollover.get_expiry_info_message()
        print(msg.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', ''))
    else:
        print("Expiry Rollover")
        print("  --check  Check and send alerts")
        print("  --info   Show expiry info")
        
        print("\nCurrent Expiries:")
        for symbol in ['NIFTY', 'BANKNIFTY', 'FINNIFTY']:
            sugg = rollover.get_rollover_suggestion(symbol)
            print(f"  {symbol}: {sugg['current_expiry']} ({sugg['days_to_expiry']} days)")
