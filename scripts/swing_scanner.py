#!/usr/bin/env python3
"""
Swing Trading Breakout Scanner
==============================
Analyzes daily stock history CSVs and identifies breakout setups based on:
1. Institutional Delivery Accumulation (Delivery Qty > 2x average, Delivery % > 50%)
2. Volume Expansion (Volume > 3x average)
3. Trend & Momentum (Close > 20 EMA > 50 EMA, 50 < RSI < 68)

Saves daily scan results to:
data/swing_intelligence/scans/{YYYY-MM-DD}.json
And broadcasts a premium terminal-style dashboard to Telegram.
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
SWING_DIR = DATA_DIR / "swing_intelligence"
STOCKS_DIR = SWING_DIR / "stocks"
SCANS_DIR = SWING_DIR / "scans"

# Setup Logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "swing_scanner.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SwingScanner")

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

def calculate_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI using Wilder's smoothing."""
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).copy()
    loss = (-delta.where(delta < 0, 0)).copy()
    
    # Use exponential moving average (Wilder's method)
    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def scan_stock(symbol: str) -> dict:
    """
    Perform technical and volume scan on a single stock's CSV.
    """
    csv_path = STOCKS_DIR / symbol / "daily_history.csv"
    if not csv_path.exists():
        return None
        
    try:
        df = pd.read_csv(csv_path)
        if len(df) < 50: # Need enough data for 50 EMA
            return None
            
        # Sort by date ascending to compute indicators
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        # 1. Price Calculations
        close = df['close']
        df['20_ema'] = close.ewm(span=20, adjust=False).mean()
        df['50_ema'] = close.ewm(span=50, adjust=False).mean()
        df['rsi'] = calculate_rsi(close, 14)
        df['pct_change'] = close.pct_change() * 100
        
        # 2. Volume Calculations
        vol = df['volume']
        df['20_avg_vol'] = vol.rolling(20).mean()
        
        # 3. Delivery Calculations
        del_qty = df['delivery_qty']
        df['10_avg_delivery'] = del_qty.rolling(10).mean()
        
        # Get latest day details
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) > 1 else latest
        
        # Calculate multipliers safely
        vol_mult = latest['volume'] / latest['20_avg_vol'] if latest['20_avg_vol'] > 0 else 1.0
        del_mult = latest['delivery_qty'] / latest['10_avg_delivery'] if latest['10_avg_delivery'] > 0 else 1.0
        
        # Base trend conditions
        in_uptrend = latest['close'] > latest['20_ema'] > latest['50_ema']
        rsi_momentum = 50.0 < latest['rsi'] < 68.0
        
        # Check Strategy Rules
        del_spike = latest['delivery_pct'] >= 50.0 and del_mult >= 2.0
        vol_breakout = vol_mult >= 3.0 and latest['pct_change'] >= 2.0
        
        # Classification
        signal = None
        score = 0
        
        if del_spike and vol_breakout and in_uptrend and rsi_momentum:
            signal = "🔥 SUPER BREAKOUT"
            score = 3
        elif del_spike and in_uptrend:
            signal = "📦 HEAVY DELIVERY"
            score = 2
        elif vol_breakout and in_uptrend and rsi_momentum:
            signal = "🚀 MOMENTUM BREAKOUT"
            score = 1
            
        if signal:
            # Suggest Trade Setup parameters
            close_price = float(latest['close'])
            entry_min = round(close_price * 0.99, 1)
            entry_max = round(close_price * 1.01, 1)
            target = round(close_price * 1.10, 1) # 10% target
            stop_loss = round(min(latest['20_ema'], close_price * 0.94), 1) # ~6% or 20 EMA
            
            return {
                "symbol": symbol,
                "date": latest['date'].strftime("%Y-%m-%d"),
                "close": close_price,
                "pct_change": float(latest['pct_change']),
                "volume": int(latest['volume']),
                "vol_mult": float(vol_mult),
                "delivery_pct": float(latest['delivery_pct']),
                "del_mult": float(del_mult),
                "rsi": float(latest['rsi']),
                "signal": signal,
                "score": score,
                "entry_range": f"{entry_min} - {entry_max}",
                "target": target,
                "stop_loss": stop_loss
            }
            
    except Exception as e:
        logger.error(f"Error scanning {symbol}: {e}")
        
    return None

def format_telegram_report(date_str: str, matches: list) -> str:
    """Format matching swing breakouts into a premium Bloomberg-style report."""
    formatted_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%b-%Y")
    
    report = f"🔮 <b>SWING TRADING BREAKOUTS ({formatted_date})</b>\n"
    report += "==================================\n\n"
    
    if not matches:
        report += "No breakout setups identified today.\n<i>Keep capital safe. Wait for clean setups.</i>"
        return report
        
    # Sort matches by score (Super Breakout first) then percentage change descending
    matches.sort(key=lambda x: (x["score"], x["pct_change"]), reverse=True)
    
    for idx, m in enumerate(matches[:6], 1):  # Display top 6 candidates
        sign = "+" if m["pct_change"] > 0 else ""
        report += f"{idx}. <b>{m['symbol']}</b> (LTP: <code>₹{m['close']:.2f}</code> | {sign}{m['pct_change']:.2f}%)\n"
        report += f"   Setup: <b>{m['signal']}</b>\n"
        report += f"   🔹 Delivery: <code>{m['delivery_pct']:.1f}%</code> ({m['del_mult']:.1f}x)\n"
        report += f"   🔹 Volume: <code>{m['vol_mult']:.1f}x avg</code>\n"
        report += f"   🔹 RSI (14): <code>{m['rsi']:.1f}</code>\n"
        report += f"   🎯 Entry: <code>{m['entry_range']}</code>\n"
        report += f"   🎯 Target: <code>₹{m['target']:.2f}</code>\n"
        report += f"   🛑 Stop-Loss: <code>₹{m['stop_loss']:.2f}</code>\n"
        report += "----------------------------------\n"
        
    report += "\n📝 <i>Note: Positions are cash cash-on-delivery. Average holding period is 3 to 15 days. Always maintain position sizing.</i>"
    return report

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scan stocks for swing trading breakouts.")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD format (Default: Today)", default=None)
    args = parser.parse_args()
    
    # Calculate target date in IST
    if args.date:
        target_date_str = args.date
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d")
    else:
        now_ist = datetime.now(IST)
        if now_ist.weekday() >= 5:
            logger.info("Today is a weekend. Swing scanning is not run on weekends.")
            sys.exit(0)
        target_date_str = now_ist.strftime("%Y-%m-%d")
        target_date = now_ist
        
    logger.info(f"Starting swing scan for date {target_date_str}...")
    
    # Scan all active folders in stocks directory
    matches = []
    if not STOCKS_DIR.exists():
        logger.error(f"Stocks directory {STOCKS_DIR} does not exist. Run collector first.")
        sys.exit(1)
        
    stocks = [d.name for d in STOCKS_DIR.iterdir() if d.is_dir()]
    logger.info(f"Scanning {len(stocks)} stocks...")
    
    for symbol in stocks:
        res = scan_stock(symbol)
        if res and res["date"] == target_date_str:
            matches.append(res)
            
    logger.info(f"Found {len(matches)} matching setups.")
    
    # Save output json
    SCANS_DIR.mkdir(parents=True, exist_ok=True)
    scan_file = SCANS_DIR / f"{target_date_str}.json"
    with open(scan_file, "w") as f:
        json.dump(matches, f, indent=4)
    logger.info(f"Saved scan results to {scan_file}")
    
    # Broadcast to Telegram
    report = format_telegram_report(target_date_str, matches)
    success = send_telegram_message(report)
    if success:
        logger.info("✅ Broadcasted swing breakouts to Telegram successfully.")
    else:
        logger.error("❌ Failed to send swing breakouts to Telegram.")

if __name__ == "__main__":
    main()
