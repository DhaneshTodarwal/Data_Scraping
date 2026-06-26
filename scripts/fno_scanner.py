"""
F&O Breakout & Option Selling Scanner
=====================================
Analyzes EOD F&O metrics to identify:
1. Futures Buildup (Long Buildup, Short Buildup, Short Covering, Long Unwinding)
2. Historical IV Rank & Percentile (over 30-day window)
3. High Probability Option Selling Setups (OTM Put Writing & Neutral Strangles)

Saves daily scan results and broadcasts a premium Bloomberg-style dashboard to Telegram.

Created: 2026-06-25
"""

import os
import sys
import json
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests

# Add project root to sys.path to access config
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = Path("/home/dhanesh-todarwal/nifty_options_scanner")
sys.path.insert(0, str(PROJECT_ROOT))

# Import config credentials
try:
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_BOT_TOKEN = "8435399514:AAExJBLy-Qouu7ousURDDDmZwHxHskNJHLg"
    TELEGRAM_CHAT_ID = "-1004420106626"

# IST Timezone
IST = timezone(timedelta(hours=5, minutes=30))

# Directories
DATA_DIR = BASE_DIR / "data"
FNO_DIR = DATA_DIR / "fno_intelligence"
STOCKS_DIR = FNO_DIR / "stocks"
SCANS_DIR = FNO_DIR / "scans"
SCANS_DIR.mkdir(parents=True, exist_ok=True)

# Setup Logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "fno_scanner.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("FnOScanner")

def send_telegram_message(message: str) -> bool:
    """Send formatted message to Telegram channel."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram token or Chat ID not configured.")
        return False
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        res = requests.post(url, data=data, timeout=10)
        return res.status_code == 200
    except Exception as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False

def scan_symbol_fno(symbol: str, target_date_str: str) -> dict:
    """Analyze historical F&O metrics for a single stock."""
    csv_path = STOCKS_DIR / symbol / "daily_fno_summary.csv"
    if not csv_path.exists():
        return None
        
    try:
        # Load and sort data
        df = pd.read_csv(csv_path)
        if len(df) < 2:
            return None
            
        df['Date'] = pd.to_datetime(df['Date'])
        df = df.sort_values('Date').reset_index(drop=True)
        
        # Format string dates back for ease
        df['Date_Str'] = df['Date'].dt.strftime('%Y-%m-%d')
        
        # Check if target date is in the DataFrame
        target_rows = df[df['Date_Str'] == target_date_str]
        if target_rows.empty:
            return None
            
        target_idx = target_rows.index[0]
        if target_idx < 1:  # Need at least one previous day for changes
            return None
            
        latest = df.iloc[target_idx]
        prev = df.iloc[target_idx - 1]
        
        # 1. Futures price change & OI change percentage
        price_change_pct = 0.0
        if prev['Spot_Price'] > 0:
            price_change_pct = (latest['Spot_Price'] - prev['Spot_Price']) / prev['Spot_Price'] * 100
            
        oi_change_pct = 0.0
        if prev['Fut_OI'] > 0:
            oi_change_pct = (latest['Fut_OI'] - prev['Fut_OI']) / prev['Fut_OI'] * 100
            
        # Classify Futures Buildup
        buildup = "Neutral"
        if price_change_pct >= 0.4 and oi_change_pct >= 4.0:
            buildup = "Long Buildup"
        elif price_change_pct <= -0.4 and oi_change_pct >= 4.0:
            buildup = "Short Buildup"
        elif price_change_pct >= 0.4 and oi_change_pct <= -4.0:
            buildup = "Short Covering"
        elif price_change_pct <= -0.4 and oi_change_pct <= -4.0:
            buildup = "Long Unwinding"
            
        # 2. Implied Volatility Analysis (over last 30 trading days of history)
        history_window = df.iloc[max(0, target_idx - 29):target_idx + 1]
        iv_history = history_window['ATM_IV'].dropna().tolist()
        
        iv_rank = 0.0
        iv_pct = 0.0
        current_iv = latest['ATM_IV']
        
        if len(iv_history) >= 5 and current_iv > 0:
            min_iv = min(iv_history)
            max_iv = max(iv_history)
            
            # IV Rank
            if max_iv > min_iv:
                iv_rank = (current_iv - min_iv) / (max_iv - min_iv) * 100
            else:
                iv_rank = 0.0
                
            # IV Percentile
            days_below = sum(1 for iv in iv_history if iv < current_iv)
            iv_pct = (days_below / len(iv_history)) * 100
            
        # 3. Setup Screening
        setup_type = "None"
        setup_desc = ""
        action = ""
        
        pcr = latest['PCR_OI']
        max_put_strike = latest['Max_Put_OI_Strike']
        max_call_strike = latest['Max_Call_OI_Strike']
        spot = latest['Spot_Price']
        
        # Put Writing Candidate (Bullish, High IV)
        if buildup in ["Long Buildup", "Short Covering"] and pcr >= 0.8 and iv_rank >= 45.0:
            # Check that Max Put Strike is at least 3% below spot
            if max_put_strike < spot * 0.985:
                setup_type = "PUT WRITING"
                setup_desc = f"Bullish future buildup ({buildup}) & rich options premium (IV Rank: {iv_rank:.1f}%)."
                action = f"Sell OTM Put @ ₹{int(max_put_strike)} (Target Support)"
                
        # Neutral Strangle Candidate (Rangebound, Very High IV)
        elif buildup == "Neutral" and 0.8 <= pcr <= 1.25 and iv_rank >= 55.0:
            # Check boundaries are wide enough
            if max_put_strike < spot * 0.97 and max_call_strike > spot * 1.03:
                setup_type = "STRANGLE"
                setup_desc = f"Rangebound movement & extremely high volatility (IV Rank: {iv_rank:.1f}%)."
                action = f"Sell Strangle: PE ₹{int(max_put_strike)} & CE ₹{int(max_call_strike)}"

        return {
            "symbol": symbol,
            "date": target_date_str,
            "spot_price": spot,
            "price_chg_pct": price_change_pct,
            "futures_buildup": buildup,
            "futures_oi_chg_pct": oi_change_pct,
            "atm_iv": current_iv * 100,  # convert to %
            "iv_rank": iv_rank,
            "iv_percentile": iv_pct,
            "pcr": pcr,
            "max_call_strike": max_call_strike,
            "max_put_strike": max_put_strike,
            "setup_type": setup_type,
            "setup_desc": setup_desc,
            "action": action
        }
        
    except Exception as e:
        logger.error(f"Error scanning stock {symbol}: {e}")
        return None

def format_telegram_report(date_str: str, matches: list) -> str:
    """Format matching setups into an aesthetic terminal-style layout."""
    date_formatted = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d %b %Y")
    
    header = (
        f"<b>⚡ F&amp;O INTEL OPTION WRITING DASHBOARD</b>\n"
        f"<code>📅 DATE: {date_formatted} | Watchlist Scan</code>\n"
        f"<code>========================================</code>\n\n"
    )
    
    body = ""
    for m in matches:
        setup_emoji = "🔥" if m["setup_type"] == "PUT WRITING" else "📦"
        spot_formatted = f"₹{m['spot_price']:,.2f}"
        
        # Build individual cards
        body += (
            f"<b>{setup_emoji} {m['symbol']}</b> (Spot: <code>{spot_formatted}</code> | "
            f"<code>{m['price_chg_pct']:+.2f}%</code>)\n"
            f"• Setup: <b>{m['setup_type']}</b>\n"
            f"• Future Buildup: <code>{m['futures_buildup']}</code> (OI: <code>{m['futures_oi_chg_pct']:+.1f}%</code>)\n"
            f"• Implied Volatility: <code>{m['atm_iv']:.1f}%</code> (IV Rank: <b>{m['iv_rank']:.1f}%</b>)\n"
            f"• Put-Call Ratio (PCR): <code>{m['pcr']:.2f}</code>\n"
            f"• Major Support: <code>₹{int(m['max_put_strike'])}</code> | Resistance: <code>₹{int(m['max_call_strike'])}</code>\n"
            f"👉 <b>RECOMMENDED:</b> <u>{m['action']}</u>\n"
            f"<code>----------------------------------------</code>\n\n"
        )
        
    if not body:
        body = "<i>No high-probability option selling setups identified for today. Option premiums are at fair value or trend direction lacks confirmation.</i>\n\n"
        
    footer = (
        f"<code>⚠️ DISCLAIMER: For educational/paper trading purposes. Option selling involves leverage. Keep margins hedged.</code>"
    )
    
    return header + body + footer

def main():
    # Set default target date as today (or weekday equivalent)
    today = datetime.now(IST)
    
    # Check for market holidays
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import market_holidays
        is_holiday, reason = market_holidays.get_market_status(today)
        if is_holiday:
            logger.info(f"📅 Market Holiday: {reason}. Skipping F&O scanning.")
            sys.exit(0)
    except Exception as e:
        logger.error(f"Error checking market holiday: {e}")
        
    # If weekend, check Friday's data
    if today.weekday() == 5:  # Saturday
        today = today - timedelta(days=1)
    elif today.weekday() == 6:  # Sunday
        today = today - timedelta(days=2)
        
    target_date_str = today.strftime("%Y-%m-%d")
    
    # Handle optional date argument
    if len(sys.argv) > 1:
        target_date_str = sys.argv[1]
        
    logger.info(f"Starting EOD F&O scan for date {target_date_str}...")
    
    # Scan all directories in stocks directory
    matches = []
    if not STOCKS_DIR.exists():
        logger.error(f"F&O stock directory {STOCKS_DIR} does not exist. Run collector first.")
        sys.exit(1)
        
    stocks = [d.name for d in STOCKS_DIR.iterdir() if d.is_dir()]
    logger.info(f"Scanning {len(stocks)} stocks...")
    
    setup_candidates = []
    for symbol in stocks:
        res = scan_symbol_fno(symbol, target_date_str)
        if res:
            # We save all scanned metrics
            matches.append(res)
            # Filter only active setups
            if res["setup_type"] != "None":
                setup_candidates.append(res)
                
    logger.info(f"Successfully scanned {len(matches)} stocks. Found {len(setup_candidates)} option selling setups.")
    
    # Save daily scan results
    scan_file = SCANS_DIR / f"{target_date_str}.json"
    with open(scan_file, "w") as f:
        json.dump(matches, f, indent=4)
    logger.info(f"Saved EOD F&O scan results to {scan_file}")
    
    # Broadcast to Telegram
    report = format_telegram_report(target_date_str, setup_candidates)
    success = send_telegram_message(report)
    if success:
        logger.info("✅ Broadcasted EOD F&O setups to Telegram successfully.")
    else:
        logger.error("❌ Failed to broadcast EOD F&O setups to Telegram.")

if __name__ == "__main__":
    main()
