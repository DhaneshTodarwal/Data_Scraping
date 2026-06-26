#!/usr/bin/env python3
"""
Post-Market Scraper
===================
Runs daily at 07:30 PM IST on weekdays.
Fetches:
1. FII / DII Net Activity in Cash Market
2. Participant-wise Open Interest (OI) in Derivatives
3. Security-wise Deliverable Positions (for F&O and Nifty 50 stocks)

Saves data in structured JSON format and sends a premium terminal-style report to Telegram.
"""
import os
import sys
import json
import csv
import time
import logging
import argparse
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

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
FII_DII_DIR = DATA_DIR / "fii_dii"
PARTICIPANT_OI_DIR = DATA_DIR / "participant_oi"
DELIVERY_DIR = DATA_DIR / "delivery_percentage"

# Log configuration
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "post_market_scraper.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("PostMarketScraper")

# Nifty 50 constituents for delivery filtering
NIFTY_50_STOCKS = {
    'ADANIENT', 'ADANIPORTS', 'APOLLOHOSP', 'ASIANPAINT', 'AXISBANK', 'BAJAJ-AUTO', 
    'BAJAJFINSV', 'BAJFINANCE', 'BHARTIARTL', 'BPCL', 'BRITANNIA', 'CIPLA', 
    'COALINDIA', 'DIVISLAB', 'DRREDDY', 'EICHERMOT', 'GRASIM', 'HCLTECH', 
    'HDFCBANK', 'HDFCLIFE', 'HEROMOTOCO', 'HINDALCO', 'HINDUNILVR', 'ICICIBANK', 
    'ITC', 'INDUSINDBK', 'INFY', 'JSWSTEEL', 'KOTAKBANK', 'LT', 'M&M', 'MARUTI', 
    'NTPC', 'NESTLEIND', 'ONGC', 'POWERGRID', 'RELIANCE', 'SBILIFE', 'SBIN', 
    'SUNPHARMA', 'TCS', 'TATACONSUM', 'TATAMOTORS', 'TATASTEEL', 'TECHM', 
    'TITAN', 'ULTRACEMCO', 'WIPRO', 'SHRIRAMFIN', 'JIOFIN'
}

# NSE headers for session
NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Referer': 'https://www.nseindia.com/',
    'X-Requested-With': 'XMLHttpRequest'
}

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

def get_session():
    """Create a requests session and initialize cookies on NSE India."""
    session = requests.Session()
    session.headers.update(NSE_HEADERS)
    try:
        session.get("https://www.nseindia.com", timeout=10)
        time.sleep(1)
    except Exception as e:
        logger.warning(f"Could not initialize cookies: {e}")
    return session

def fetch_fii_dii_cash(session, target_date_str):
    """
    Fetch FII / DII net cash flows for the day.
    Returns: dict of values or None
    """
    url = "https://www.nseindia.com/api/fiidiiTradeReact"
    try:
        logger.info("Fetching FII/DII cash flow data...")
        res = session.get(url, timeout=10)
        if res.status_code != 200:
            logger.error(f"Failed to fetch FII/DII cash. Status: {res.status_code}")
            return None
            
        data = res.json()
        if not data:
            return None
            
        # Verify if the date in the response matches target date
        # Response date format: "24-Jun-2026"
        target_dt = datetime.strptime(target_date_str, "%Y-%m-%d")
        resp_date_str = data[0].get('date', '')
        resp_dt = datetime.strptime(resp_date_str, "%d-%b-%Y")
        
        if target_dt.date() != resp_dt.date():
            logger.warning(f"FII/DII cash data date {resp_date_str} does not match target date {target_date_str}.")
            return None
            
        result = {
            "date": target_date_str,
            "DII": {"buy_value_crores": 0.0, "sell_value_crores": 0.0, "net_value_crores": 0.0},
            "FII": {"buy_value_crores": 0.0, "sell_value_crores": 0.0, "net_value_crores": 0.0}
        }
        
        for item in data:
            cat = item.get('category', '')
            buy = float(item.get('buyValue', 0.0))
            sell = float(item.get('sellValue', 0.0))
            net = float(item.get('netValue', 0.0))
            
            if "DII" in cat:
                result["DII"] = {"buy_value_crores": buy, "sell_value_crores": sell, "net_value_crores": net}
            elif "FII" in cat or "FPI" in cat:
                result["FII"] = {"buy_value_crores": buy, "sell_value_crores": sell, "net_value_crores": net}
                
        return result
    except Exception as e:
        logger.error(f"Error fetching FII/DII cash: {e}")
        return None

def fetch_participant_oi(target_date_str):
    """
    Fetch F&O Participant-wise Open Interest (OI) CSV.
    Returns: dict of values or None
    """
    # Convert date to DDMMYYYY
    dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    date_suffix = dt.strftime("%d%m%Y")
    url = f"https://archives.nseindia.com/content/nsccl/fao_participant_oi_{date_suffix}.csv"
    
    try:
        logger.info(f"Fetching participant-wise OI from {url}...")
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if res.status_code != 200:
            logger.warning(f"Participant-wise OI file not found (Status {res.status_code}).")
            return None
            
        # Parse CSV lines
        lines = res.text.split('\n')
        # Skip the title line
        csv_data = [line.strip() for line in lines if line.strip()]
        if len(csv_data) < 3:
            return None
            
        reader = csv.reader(csv_data[1:])
        headers = [h.strip() for h in next(reader)]
        
        parsed_data = {}
        for row in reader:
            if not row or len(row) < len(headers):
                continue
            client_type = row[0].strip()
            # Map headers to values
            client_dict = {}
            for col_idx, col_name in enumerate(headers[1:], start=1):
                clean_name = col_name.lower().replace(' ', '_').replace('(', '').replace(')', '').replace('.', '')
                try:
                    client_dict[clean_name] = int(row[col_idx].strip())
                except ValueError:
                    client_dict[clean_name] = row[col_idx].strip()
            parsed_data[client_type] = client_dict
            
        return {
            "date": target_date_str,
            "data": parsed_data
        }
    except Exception as e:
        logger.error(f"Error fetching participant OI: {e}")
        return None

def fetch_delivery_data(target_date_str):
    """
    Fetch Security-wise Deliverable Positions DAT file.
    Returns: dict of values or None
    """
    # Convert date to DDMMYYYY
    dt = datetime.strptime(target_date_str, "%Y-%m-%d")
    date_suffix = dt.strftime("%d%m%Y")
    url = f"https://archives.nseindia.com/archives/equities/mto/MTO_{date_suffix}.DAT"
    
    try:
        logger.info(f"Fetching delivery data from {url}...")
        res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
        if res.status_code != 200:
            logger.warning(f"Delivery position file not found (Status {res.status_code}).")
            return None
            
        lines = res.text.split('\n')
        parsed_data = {}
        
        for line in lines:
            parts = line.strip().split(',')
            if len(parts) >= 7 and parts[0] == '20' and parts[3] == 'EQ':
                symbol = parts[2].strip()
                try:
                    traded_qty = int(parts[4].strip())
                    deliverable_qty = int(parts[5].strip())
                    delivery_pct = float(parts[6].strip())
                    
                    parsed_data[symbol] = {
                        "traded_quantity": traded_qty,
                        "deliverable_quantity": deliverable_qty,
                        "delivery_percentage": delivery_pct
                    }
                except ValueError:
                    continue
                    
        return {
            "date": target_date_str,
            "data": parsed_data
        }
    except Exception as e:
        logger.error(f"Error fetching delivery data: {e}")
        return None

def save_json(data, target_dir, date_str):
    """Helper to save dictionary as JSON in Year/Month/ file structure."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        year = dt.strftime("%Y")
        month = dt.strftime("%B")
        
        save_path = target_dir / year / month
        save_path.mkdir(parents=True, exist_ok=True)
        
        file_path = save_path / f"{date_str}.json"
        with open(file_path, "w") as f:
            json.dump(data, f, indent=4)
        logger.info(f"Saved data to {file_path}")
        return True
    except Exception as e:
        logger.error(f"Failed to save JSON data: {e}")
        return False

def generate_telegram_report(fii_dii, participant_oi, delivery_data):
    """Compile a high-fidelity Bloomberg-style Telegram alert."""
    dt_str = fii_dii.get("date") if fii_dii else (participant_oi.get("date") if participant_oi else "N/A")
    formatted_date = datetime.strptime(dt_str, "%Y-%m-%d").strftime("%d-%b-%Y")
    
    report = f"🏛️ <b>POST-MARKET CLUES ({formatted_date})</b>\n"
    report += "==================================\n\n"
    
    # 1. FII / DII Cash Flows
    if fii_dii:
        fii_net = fii_dii["FII"]["net_value_crores"]
        dii_net = fii_dii["DII"]["net_value_crores"]
        combined = fii_net + dii_net
        
        fii_sign = "+" if fii_net > 0 else ""
        dii_sign = "+" if dii_net > 0 else ""
        comb_sign = "+" if combined > 0 else ""
        
        report += "💰 <b>FII / DII CASH FLOWS (Cr)</b>\n"
        report += "----------------------------------\n"
        report += f"FII Net: <code>{fii_sign}{fii_net:,.2f} Cr</code>\n"
        report += f"DII Net: <code>{dii_sign}{dii_net:,.2f} Cr</code>\n"
        report += f"Combined: <b>{comb_sign}{combined:,.2f} Cr</b>\n\n"
    
    # 2. Participant-wise Index Futures OI
    if participant_oi and "data" in participant_oi:
        data = participant_oi["data"]
        report += "📊 <b>PARTICIPANT INDEX FUTURES (Net)</b>\n"
        report += "----------------------------------\n"
        
        for p_type in ["Client", "DII", "FII", "Pro"]:
            p_data = data.get(p_type, {})
            long_contracts = p_data.get("future_index_long", 0)
            short_contracts = p_data.get("future_index_short", 0)
            net_contracts = long_contracts - short_contracts
            
            sign = "+" if net_contracts > 0 else ""
            sentiment = "🟢 Bullish" if net_contracts > 15000 else "🔴 Bearish" if net_contracts < -15000 else "🟡 Neutral"
            
            # Pad name for monospacing
            p_name_padded = p_type.ljust(6)
            report += f"{p_name_padded}: <code>{sign}{net_contracts:,}</code> ({sentiment})\n"
        report += "\n"
        
    # 3. High Delivery percentage in Nifty 50
    if delivery_data and "data" in delivery_data:
        data = delivery_data["data"]
        report += "📈 <b>NIFTY 50 HIGH DELIVERY BREAKOUTS</b>\n"
        report += "----------------------------------\n"
        
        high_del = []
        for symbol, info in data.items():
            if symbol in NIFTY_50_STOCKS:
                del_pct = info["delivery_percentage"]
                if del_pct >= 60.0:
                    high_del.append((symbol, del_pct, info["traded_quantity"]))
                    
        # Sort by delivery percentage descending
        high_del.sort(key=lambda x: x[1], reverse=True)
        
        if high_del:
            for symbol, pct, qty in high_del[:8]:
                # Format volume in Millions
                vol_m = qty / 1000000.0
                report += f"• <b>{symbol}</b>: <code>{pct:.1f}%</code> (Vol: {vol_m:.2f}M)\n"
        else:
            report += "No Nifty 50 stock with delivery > 60%.\n"
            
    return report

def main():
    parser = argparse.ArgumentParser(description="Post-Market Clues Scraper & Alerting System")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD format (Default: Today)", default=None)
    args = parser.parse_args()
    
    # Calculate target date
    if args.date:
        target_date_str = args.date
        logger.info(f"Target date set via CLI: {target_date_str}")
    else:
        # Today in IST
        now_ist = datetime.now(IST)
        target_date_str = now_ist.strftime("%Y-%m-%d")
        
        # Verify if weekend or holiday
        sys.path.insert(0, str(SCRIPT_DIR))
        try:
            import market_holidays
            is_holiday, reason = market_holidays.get_market_status(now_ist)
            if is_holiday:
                logger.info(f"Today is a market holiday: {reason}. Skipping post-market scraper.")
                sys.exit(0)
        except Exception as e:
            logger.error(f"Error checking market holiday: {e}")
            if now_ist.weekday() >= 5:
                logger.info("Today is a weekend. Post-market data is not available. Use --date to backfill.")
                sys.exit(0)
            
    logger.info(f"Starting post-market scraping cycle for {target_date_str}...")
    
    session = get_session()
    
    # We will try up to 16 times (every 15 mins for 4 hours) if running for today
    max_retries = 1 if args.date else 16
    retry_interval = 900  # 15 minutes
    
    fii_dii = None
    participant_oi = None
    delivery_data = None
    
    for attempt in range(max_retries):
        logger.info(f"Execution attempt {attempt + 1}/{max_retries}...")
        
        if not fii_dii:
            fii_dii = fetch_fii_dii_cash(session, target_date_str)
        if not participant_oi:
            participant_oi = fetch_participant_oi(target_date_str)
        if not delivery_data:
            delivery_data = fetch_delivery_data(target_date_str)
            
        # Check if we have collected all data points
        if fii_dii and participant_oi and delivery_data:
            logger.info("✅ All post-market data points collected successfully!")
            break
            
        if attempt < max_retries - 1:
            logger.info(f"Some files are not published yet. Sleeping for {retry_interval/60:.1f} minutes...")
            time.sleep(retry_interval)
            # Recreate session to avoid connection stale
            session = get_session()
            
    # Save whatever we fetched
    if fii_dii:
        save_json(fii_dii, FII_DII_DIR, target_date_str)
    else:
        logger.warning("⚠️ FII/DII Cash data collection failed or was not published yet.")
        
    if participant_oi:
        save_json(participant_oi, PARTICIPANT_OI_DIR, target_date_str)
    else:
        logger.warning("⚠️ Participant-wise OI data collection failed or was not published yet.")
        
    if delivery_data:
        save_json(delivery_data, DELIVERY_DIR, target_date_str)
    else:
        logger.warning("⚠️ Delivery percentage data collection failed or was not published yet.")
        
    # Send Telegram alert if we have at least FII/DII or Participant OI
    if fii_dii or participant_oi or delivery_data:
        report_msg = generate_telegram_report(fii_dii, participant_oi, delivery_data)
        logger.info("Sending post-market clues summary to Telegram...")
        success = send_telegram_message(report_msg)
        if success:
            logger.info("✅ Telegram alert sent successfully.")
        else:
            logger.error("❌ Failed to send Telegram alert.")
    else:
        logger.error("❌ Scraper run failed. No data collected.")
        sys.exit(1)

if __name__ == "__main__":
    main()
