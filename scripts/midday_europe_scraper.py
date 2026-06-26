#!/usr/bin/env python3
"""
Midday European Market Open Scanner
===================================
Runs daily at 01:15 PM IST (mid-way through Indian market session).
Checks:
- DAX (^GDAXI), CAC 40 (^FCHI), FTSE 100 (^FTSE) live daily returns.
- Nifty 50 Spot (^NSEI) current position.
- Compares against morning Daily Bias Score to detect global sentiment shifts.
Sends a warning or status update to Telegram to protect active trades.
"""
import os
import sys
import json
import logging
import yfinance as yf
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project root to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = Path("/home/dhanesh-todarwal/nifty_options_scanner")
sys.path.insert(0, str(PROJECT_ROOT))

# Load Telegram credentials
try:
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
except ImportError:
    TELEGRAM_BOT_TOKEN = "8435399514:AAExJBLy-Qouu7ousURDDDmZwHxHskNJHLg"
    TELEGRAM_CHAT_ID = "-1004420106626"

import requests

# IST Timezone
IST = timezone(timedelta(hours=5, minutes=30))

# Directories
DATA_DIR = BASE_DIR / "data"
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Logger setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "midday_europe_scanner.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("MiddayEuropeScanner")

def send_telegram_message(message: str) -> bool:
    """Send message to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured.")
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

def get_ticker_pct_change(symbol: str) -> float:
    """Fetch 1d return for ticker."""
    try:
        ticker = yf.Ticker(symbol)
        # Fetch 5 days to make sure we have data
        hist = ticker.history(period="5d")
        if hist.empty:
            return 0.0
        latest_row = hist.iloc[-1]
        prev_row = hist.iloc[-2] if len(hist) > 1 else latest_row
        close_val = latest_row["Close"]
        prev_close = prev_row["Close"]
        if prev_close == 0:
            return 0.0
        return ((close_val - prev_close) / prev_close) * 100
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
        return 0.0

def load_morning_prediction(date_str: str):
    """Load morning prediction JSON from DATA_DIR."""
    year = datetime.strptime(date_str, "%Y-%m-%d").strftime("%Y")
    month = datetime.strptime(date_str, "%Y-%m-%d").strftime("%B")
    pred_file = DATA_DIR / "predictions" / year / month / f"{date_str}.json"
    if pred_file.exists():
        try:
            with open(pred_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to read morning prediction file {pred_file}: {e}")
    return None

def main():
    now_ist = datetime.now(IST)
    
    # Check for market holidays
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import market_holidays
        is_holiday, reason = market_holidays.get_market_status(now_ist)
        if is_holiday:
            logger.info(f"Today is a market holiday: {reason}. Skipping midday scan.")
            sys.exit(0)
    except Exception as e:
        logger.error(f"Error checking market holiday: {e}")
        if now_ist.weekday() >= 5:
            logger.info("Today is weekend. Skipping midday scan.")
            sys.exit(0)
            
    today_str = now_ist.strftime("%Y-%m-%d")
    logger.info(f"Starting Midday European Market Open Scan for {today_str} IST...")
    
    # Fetch Europe returns
    dax_change = get_ticker_pct_change("^GDAXI")
    cac_change = get_ticker_pct_change("^FCHI")
    ftse_change = get_ticker_pct_change("^FTSE")
    nifty_change = get_ticker_pct_change("^NSEI")
    
    # Calculate European average change
    europe_avg = (dax_change + cac_change + ftse_change) / 3.0
    
    # Load morning bias
    morning_pred = load_morning_prediction(today_str)
    morning_bias_str = "UNKNOWN"
    morning_score = 0.0
    recommended_strategy = "N/A"
    
    if morning_pred:
        morning_bias_str = morning_pred.get("bias", "UNKNOWN")
        morning_score = morning_pred.get("score", 0.0)
        recommended_strategy = morning_pred.get("recommended_strategy", "N/A")
        
    # Analyze shift and risk
    threat_level = "LOW"
    warning_flag = False
    details_msg = ""
    
    # Morning is Bullish, Europe opens Bearish
    if morning_score >= 2.0 and europe_avg <= -0.5:
        threat_level = "🚨 HIGH (Bullish Bias vs Bearish European Open)"
        warning_flag = True
        details_msg = "Morning setup was bullish, but European markets opened negative. Bullish spreads/calls may face pressure. Consider trailing SL or Booking Profits."
    # Morning is Bearish, Europe opens Bullish
    elif morning_score <= -2.0 and europe_avg >= 0.5:
        threat_level = "🚨 HIGH (Bearish Bias vs Bullish European Open)"
        warning_flag = True
        details_msg = "Morning setup was bearish, but European markets opened positive. Bearish spreads/calls may face pressure. Consider trailing SL or Booking Profits."
    # European Markets down heavily
    elif europe_avg <= -1.0:
        threat_level = "🚨 CRITICAL (Severe European Sell-off)"
        warning_flag = True
        details_msg = "European indices are experiencing heavy selling pressure. High probability of downside transmission to Indian markets."
    # European Markets up heavily
    elif europe_avg >= 1.0:
        threat_level = "✅ STRONG STRENGTH (European Surge)"
        warning_flag = False
        details_msg = "European indices opened with strong gains. Supports positive intraday trends."
    else:
        # Check for smaller alignment or neutral confirmation
        if abs(europe_avg) <= 0.3:
            threat_level = "LOW (Stable/Flat Open)"
            details_msg = "European markets opened flat, confirming rangebound/neutral intraday expectations."
        else:
            threat_level = "MODERATE"
            details_msg = "European markets open matches global baseline. No immediate action required."

    # Format message
    time_str = now_ist.strftime("%I:%M %p IST")
    report = f"🇪🇺 <b>MIDDAY GLOBAL SENTIMENT CHECK ({time_str})</b>\n"
    report += "==================================\n\n"
    
    # European Indices Status
    report += "📊 <b>EUROPEAN MARKETS PERFORMANCE:</b>\n"
    dax_sign = "+" if dax_change > 0 else ""
    cac_sign = "+" if cac_change > 0 else ""
    ftse_sign = "+" if ftse_change > 0 else ""
    report += f"• Germany DAX: <code>{dax_sign}{dax_change:.2f}%</code>\n"
    report += f"• France CAC:  <code>{cac_sign}{cac_change:.2f}%</code>\n"
    report += f"• London FTSE: <code>{ftse_sign}{ftse_change:.2f}%</code>\n"
    report += f"• <b>Europe Avg: <code>{'+' if europe_avg > 0 else ''}{europe_avg:.2f}%</code></b>\n\n"
    
    # Morning Bias and current Nifty Status
    report += "🔍 <b>MORNING SETUP REFERENCE:</b>\n"
    report += f"• Morning Bias: {morning_bias_str} (<code>{morning_score:+.2f}</code>)\n"
    report += f"• Strategy: <code>{recommended_strategy}</code>\n"
    report += f"• Nifty 50 Return: <code>{'+' if nifty_change > 0 else ''}{nifty_change:.2f}%</code>\n\n"
    
    # Threat / Risk recommendation
    color_emoji = "🔴" if warning_flag or "HIGH" in threat_level or "CRITICAL" in threat_level else "🟡" if "MODERATE" in threat_level else "🟢"
    report += f"{color_emoji} <b>THREAT LEVEL: {threat_level}</b>\n"
    report += f"📝 <i>{details_msg}</i>\n\n"
    report += "⚡ <i>Check active straddles/strangles and adjust stops as needed.</i>"
    
    logger.info(f"Midday Analysis Complete. Threat Level: {threat_level}")
    logger.info("Sending report to Telegram...")
    success = send_telegram_message(report)
    if success:
        logger.info("✅ Midday alert sent successfully.")
    else:
        logger.error("❌ Failed to send midday Telegram alert.")

if __name__ == "__main__":
    main()
