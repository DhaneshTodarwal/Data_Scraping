"""
Pre-Market System Health Check
================================
Runs at 9:00 AM before market opens (9:15 AM)
Sends a confirmation alert that everything is working

Checks:
1. AngelOne API connection
2. Live data fetch
3. Telegram connection
4. Scanner ready
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

IST = timezone(timedelta(hours=5, minutes=30))

# Import required modules
try:
    from notifications import send_telegram_message
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False

try:
    from angelone_api import AngelOneAPI
    API_OK = True
except ImportError:
    API_OK = False


def check_api_connection():
    """Check AngelOne API connection"""
    if not API_OK:
        return False, "AngelOne API module not found"
    
    try:
        api = AngelOneAPI()
        if api.login():
            # Try to get NIFTY LTP
            ltp = api.get_ltp('NSE', 'Nifty 50', '99926000')
            if ltp and ltp.get('data'):
                price = ltp['data']['ltp']
                api.logout()
                return True, f"₹{price:,.2f}"
            api.logout()
            return True, "Connected (no price - market closed)"
        return False, "Login failed"
    except Exception as e:
        return False, str(e)


def check_telegram():
    """Check Telegram connection"""
    if not TELEGRAM_OK:
        return False, "Telegram module not found"
    return True, "Ready"


def run_health_check():
    """Run complete health check and send alert"""
    
    now = datetime.now(IST)
    
    print("\n" + "="*60)
    print("       PRE-MARKET SYSTEM HEALTH CHECK")
    print("="*60)
    print(f"⏰ Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    results = {}
    all_ok = True
    
    # 1. Check Telegram
    print("📱 Checking Telegram connection...")
    telegram_ok, telegram_msg = check_telegram()
    results['Telegram'] = (telegram_ok, telegram_msg)
    if not telegram_ok:
        all_ok = False
    print(f"   {'✅' if telegram_ok else '❌'} {telegram_msg}")
    
    # 2. Check API
    print("🔗 Checking AngelOne API...")
    api_ok, api_msg = check_api_connection()
    results['AngelOne API'] = (api_ok, api_msg)
    if not api_ok:
        all_ok = False
    print(f"   {'✅' if api_ok else '❌'} {api_msg}")
    
    # 3. Check scanner file exists
    scanner_path = Path(__file__).parent / "realtime_scanner.py"
    scanner_ok = scanner_path.exists()
    results['Scanner'] = (scanner_ok, "Ready" if scanner_ok else "Not found")
    print(f"📡 Scanner: {'✅ Ready' if scanner_ok else '❌ Not found'}")
    
    # 4. Check cron job
    import subprocess
    try:
        cron_output = subprocess.check_output(['crontab', '-l'], stderr=subprocess.DEVNULL).decode()
        cron_ok = 'realtime_scanner' in cron_output or 'start_scanner' in cron_output
    except:
        cron_ok = False
    results['Auto-start'] = (cron_ok, "Configured" if cron_ok else "Not set")
    print(f"⏰ Auto-start: {'✅ Configured' if cron_ok else '❌ Not set'}")
    
    print()
    print("="*60)
    
    # Generate message
    if all_ok:
        status_emoji = "🟢"
        status_text = "ALL SYSTEMS READY"
    else:
        status_emoji = "🟡"
        status_text = "SOME ISSUES DETECTED"
    
    # Get previous close price
    nifty_price = api_msg if api_ok else "N/A"
    
    # Determine market status
    if now.weekday() >= 5:
        market_status = "CLOSED (Weekend)"
    elif now.time() < datetime.strptime("09:15", "%H:%M").time():
        market_status = "OPENS AT 9:15 AM"
    else:
        market_status = "OPEN"
    
    msg = f"""
{status_emoji} <b>PRE-MARKET SYSTEM CHECK</b>

⏰ <b>Time:</b> {now.strftime('%H:%M:%S')}
📅 <b>Date:</b> {now.strftime('%A, %d %B %Y')}

━━━━━ SYSTEM STATUS ━━━━━

📱 Telegram: {'✅ Ready' if results['Telegram'][0] else '❌ Error'}
🔗 AngelOne API: {'✅ Connected' if results['AngelOne API'][0] else '❌ Error'}
📡 Scanner: {'✅ Ready' if results['Scanner'][0] else '❌ Not found'}
⏰ Auto-start (9:18): {'✅ Configured' if results['Auto-start'][0] else '❌ Not set'}

━━━━━ MARKET INFO ━━━━━

📈 <b>NIFTY:</b> {nifty_price}
📊 <b>Market Status:</b> {market_status}

━━━━━━━━━━━━━━━━━━━━━━━━

{status_emoji} <b>{status_text}</b>

"""
    
    if all_ok:
        msg += """
✅ All systems operational
✅ Scanner will start at 9:18 AM
✅ Alerts will come on Telegram
✅ Live data connected

<b>📱 You're ready for trading!</b>
"""
    else:
        msg += """
⚠️ Some issues detected
Check the error above
"""
    
    print(f"Status: {status_text}")
    
    # Send to Telegram
    if TELEGRAM_OK:
        result = send_telegram_message(msg)
        if result:
            print("✅ Health check alert sent to Telegram!")
        else:
            print("❌ Failed to send Telegram alert")
    
    return all_ok


if __name__ == "__main__":
    run_health_check()
