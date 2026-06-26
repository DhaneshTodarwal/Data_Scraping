#!/usr/bin/env python3
"""
Swing Trading Data Collector
============================
Automates collection of Daily OHLCV (price/volume) and NSE Delivery stats
for a curated list of high-momentum swing trading candidate stocks.

Saves data under:
data/swing_intelligence/stocks/{SYMBOL}/daily_history.csv
"""

import os
import sys
import csv
import time
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
import yfinance as yf
import requests

# IST Timezone setup
IST = timezone(timedelta(hours=5, minutes=30))

# Directories
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = Path("/home/dhanesh-todarwal/nifty_options_scanner")
DATA_DIR = BASE_DIR / "data"
SWING_DIR = DATA_DIR / "swing_intelligence"
STOCKS_DIR = SWING_DIR / "stocks"

# Setup Logging
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "swing_data_collector.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("SwingDataCollector")

# Curated List of High-Momentum Cash & F&O Swing Stocks
# (Focuses on Defense, Railways, Energy, Infrastructure, PSU and high-momentum sectors)
SWING_STOCKS = [
    # --- Original High-Momentum Picks (Custom) ---
    "GRSE",
    "BEML",
    "IRCON",
    "RAILTEL",
    "TEXRAIL",
    "NCC",
    "CDSL",
    "ANGELONE",
    "TATATECH",
    "GITARENEW",
    "SOBHA",

    # --- Nifty 100 (Large Caps) ---
    "ABB", "ADANIENSOL", "ADANIENT", "ADANIGREEN", "ADANIPORTS", "ADANIPOWER", "AMBUJACEM", "APOLLOHOSP",
    "ASIANPAINT", "AXISBANK", "BAJAJ-AUTO", "BAJAJFINSV", "BAJAJHLDNG", "BAJFINANCE", "BANKBARODA", "BEL",
    "BHARTIARTL", "BOSCHLTD", "BPCL", "BRITANNIA", "CANBK", "CGPOWER", "CHOLAFIN", "CIPLA",
    "COALINDIA", "CUMMINSIND", "DIVISLAB", "DLF", "DMART", "DRREDDY", "EICHERMOT", "ENRIN",
    "ETERNAL", "GAIL", "GODREJCP", "GRASIM", "HAL", "HCLTECH", "HDFCAMC", "HDFCBANK",
    "HDFCLIFE", "HINDALCO", "HINDUNILVR", "HINDZINC", "HYUNDAI", "ICICIBANK", "INDHOTEL", "INDIGO",
    "INFY", "IOC", "IRFC", "ITC", "JINDALSTEL", "JIOFIN", "JSWSTEEL", "KOTAKBANK",
    "LODHA", "LT", "LTM", "M&M", "MARUTI", "MAXHEALTH", "MAZDOCK", "MOTHERSON",
    "MUTHOOTFIN", "NESTLEIND", "NTPC", "ONGC", "PFC", "PIDILITIND", "PNB", "POWERGRID",
    "RECLTD", "RELIANCE", "SBILIFE", "SBIN", "SHREECEM", "SHRIRAMFIN", "SIEMENS", "SOLARINDS",
    "SUNPHARMA", "TATACAP", "TATACONSUM", "TATAPOWER", "TATASTEEL", "TCS", "TECHM", "TITAN",
    "TMCV", "TMPV", "TORNTPHARM", "TRENT", "TVSMOTOR", "ULTRACEMCO", "UNIONBANK", "UNITDSPR",
    "VBL", "VEDL", "WIPRO", "ZYDUSLIFE",

    # --- Nifty Midcap 150 (Mid Caps) ---
    "360ONE", "3MINDIA", "ABBOTINDIA", "ABCAPITAL", "ACC", "AIAENG", "AIIL", "AJANTPHARM",
    "ALKEM", "ANTHEM", "APARINDS", "APLAPOLLO", "APOLLOTYRE", "ASHOKLEY", "ASTRAL", "ATGL",
    "AUBANK", "AUROPHARMA", "AWL", "BAJAJHFL", "BALKRISIND", "BANKINDIA", "BDL", "BERGEPAINT",
    "BHARATFORG", "BHARTIHEXA", "BHEL", "BIOCON", "BLUESTARCO", "BSE", "COCHINSHIP", "COFORGE",
    "COLPAL", "CONCOR", "COROMANDEL", "CRISIL", "DABUR", "DALBHARAT", "DIXON", "ENDURANCE",
    "ESCORTS", "EXIDEIND", "FEDERALBNK", "FLUOROCHEM", "FORTIS", "GICRE", "GLAXO", "GLENMARK",
    "GMRAIRPORT", "GODFRYPHLP", "GODREJIND", "GODREJPROP", "GROWW", "GVT&D", "HAVELLS", "HDBFS",
    "HEROMOTOCO", "HEXT", "HINDPETRO", "HONAUT", "HUDCO", "ICICIAMC", "ICICIGI", "ICICIPRULI",
    "IDEA", "IDFCFIRSTB", "INDIANB", "INDUSINDBK", "INDUSTOWER", "IPCALAB", "IRCTC", "IREDA",
    "ITCHOTELS", "JKCEMENT", "JSL", "JSWENERGY", "JSWINFRA", "JUBLFOOD", "KALYANKJIL", "KEI",
    "KPITTECH", "KPRMILL", "LAURUSLABS", "LENSKART", "LGEINDIA", "LICHSGFIN", "LICI", "LINDEINDIA",
    "LLOYDSME", "LTF", "LTTS", "LUPIN", "M&MFIN", "MAHABANK", "MANKIND", "MARICO",
    "MCX", "MEDANTA", "MFSL", "MOTILALOFS", "MPHASIS", "MRF", "NAM-INDIA", "NATIONALUM",
    "NAUKRI", "NHPC", "NIACL", "NLCINDIA", "NMDC", "NTPCGREEN", "NYKAA", "OBEROIRLTY",
    "OFSS", "OIL", "PAGEIND", "PATANJALI", "PAYTM", "PERSISTENT", "PETRONET", "PHOENIXLTD",
    "PIIND", "POLICYBZR", "POLYCAB", "POWERINDIA", "PREMIERENE", "PRESTIGE", "RADICO", "RVNL",
    "SAIL", "SBICARD", "SCHAEFFLER", "SJVN", "SRF", "SUNDARMFIN", "SUPREMEIND", "SUZLON",
    "SWIGGY", "TATACOMM", "TATAELXSI", "TATAINVEST", "THERMAX", "TIINDIA", "TORNTPOWER", "UBL",
    "UNOMINDA", "UPL", "VMM", "VOLTAS", "WAAREEENER", "YESBANK",
]

YFINANCE_TICKER_OVERRIDES = {
    "GITARENEW": "GITARENEW.BO",
}

def get_nse_delivery_data(target_date: datetime) -> dict:
    """
    Fetch and parse the NSE Deliverable Positions DAT file for a specific date.
    Returns: dict mapping SYMBOL -> {traded_quantity, deliverable_quantity, delivery_percentage}
    """
    date_suffix = target_date.strftime("%d%m%Y")
    url = f"https://archives.nseindia.com/archives/equities/mto/MTO_{date_suffix}.DAT"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    parsed_data = {}
    
    try:
        logger.info(f"Downloading NSE delivery file for {target_date.strftime('%Y-%m-%d')}...")
        res = requests.get(url, headers=headers, timeout=10)
        
        if res.status_code == 200:
            lines = res.text.split('\n')
            for line in lines:
                parts = line.strip().split(',')
                # Format: Record Type (20), Sr No, Symbol, Series, Traded Qty, Deliverable Qty, Delivery %
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
            logger.info(f"✅ Successfully downloaded and parsed {len(parsed_data)} stocks from MTO DAT.")
        else:
            logger.warning(f"⚠️ MTO file not found for {target_date.strftime('%Y-%m-%d')} (Status {res.status_code})")
            
    except Exception as e:
        logger.error(f"❌ Error downloading/parsing NSE delivery file: {e}")
        
    return parsed_data

def load_local_delivery_json(target_date: datetime) -> dict:
    """
    Load the delivery JSON generated by the post-market scraper if it exists locally.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    year = target_date.strftime("%Y")
    month = target_date.strftime("%B")
    
    local_path = DATA_DIR / "delivery_percentage" / year / month / f"{date_str}.json"
    if local_path.exists():
        try:
            with open(local_path, "r") as f:
                data = json.load(f)
                return data.get("data", {})
        except Exception as e:
            logger.error(f"Error loading local delivery JSON: {e}")
    return {}

def fetch_yfinance_history(symbol: str, start_date: datetime, end_date: datetime) -> list:
    """
    Fetch daily OHLCV history from yfinance.
    """
    ticker = YFINANCE_TICKER_OVERRIDES.get(symbol, f"{symbol}.NS")
    try:
        # Pad end date by 1 day to ensure we get the full range
        end_padded = end_date + timedelta(days=1)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = end_padded.strftime("%Y-%m-%d")
        
        logger.info(f"Fetching yfinance history for {ticker} from {start_str} to {end_str}...")
        df = yf.download(ticker, start=start_str, end=end_str, progress=False)
        
        if df.empty:
            logger.warning(f"⚠️ No yfinance data found for {ticker}")
            return []
            
        records = []
        for idx, row in df.iterrows():
            # Handle possible MultiIndex columns from yfinance
            close_val = float(row['Close'].iloc[0]) if hasattr(row['Close'], 'iloc') else float(row['Close'])
            open_val = float(row['Open'].iloc[0]) if hasattr(row['Open'], 'iloc') else float(row['Open'])
            high_val = float(row['High'].iloc[0]) if hasattr(row['High'], 'iloc') else float(row['High'])
            low_val = float(row['Low'].iloc[0]) if hasattr(row['Low'], 'iloc') else float(row['Low'])
            vol_val = int(row['Volume'].iloc[0]) if hasattr(row['Volume'], 'iloc') else int(row['Volume'])
            
            records.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "volume": vol_val
            })
        return records
    except Exception as e:
        logger.error(f"❌ Error fetching yfinance data for {symbol}: {e}")
        return []

def get_target_history_path(symbol: str) -> Path:
    """Return local path to the daily history CSV."""
    symbol_dir = STOCKS_DIR / symbol
    symbol_dir.mkdir(parents=True, exist_ok=True)
    return symbol_dir / "daily_history.csv"

def backfill_history(symbol: str, target_date: datetime, delivery_cache: dict):
    """
    Backfill daily price and delivery percentage for the last 90 calendar days.
    """
    csv_path = get_target_history_path(symbol)
    start_date = target_date - timedelta(days=90)
    
    # 1. Fetch Price history
    price_history = fetch_yfinance_history(symbol, start_date, target_date)
    if not price_history:
        return
        
    # 2. Iterate dates in price history and overlay delivery metrics
    merged_history = []
    
    for record in price_history:
        rec_date = datetime.strptime(record["date"], "%Y-%m-%d")
        
        # Load delivery metrics for this date
        if record["date"] not in delivery_cache:
            # Check local json first
            delivery_data = load_local_delivery_json(rec_date)
            if not delivery_data:
                # Download from NSE
                delivery_data = get_nse_delivery_data(rec_date)
                time.sleep(0.5)  # Rate limit safety
            delivery_cache[record["date"]] = delivery_data
            
        day_delivery = delivery_cache[record["date"]]
        stock_delivery = day_delivery.get(symbol, {})
        
        record["delivery_qty"] = stock_delivery.get("deliverable_quantity", 0)
        record["delivery_pct"] = stock_delivery.get("delivery_percentage", 0.0)
        merged_history.append(record)
        
    # Write to CSV
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume", "delivery_qty", "delivery_pct"])
        writer.writeheader()
        writer.writerows(merged_history)
        
    logger.info(f"✅ Initialized backfill for {symbol}: Saved {len(merged_history)} daily rows.")

def process_daily_update(target_date: datetime):
    """
    Run the daily update flow. Appends latest row or backfills if file does not exist.
    """
    date_str = target_date.strftime("%Y-%m-%d")
    logger.info(f"=== Starting Swing Daily Data Update for {date_str} ===")
    
    # Fetch today's delivery data once for all stocks
    today_delivery = load_local_delivery_json(target_date)
    if not today_delivery:
        today_delivery = get_nse_delivery_data(target_date)
        
    # Shared delivery cache to avoid redundant downloads during backfills
    delivery_cache = {date_str: today_delivery}
        
    for idx, symbol in enumerate(SWING_STOCKS, 1):
        try:
            csv_path = get_target_history_path(symbol)
            
            # Check if backfill needed
            if not csv_path.exists():
                logger.info(f"[{idx}/{len(SWING_STOCKS)}] Backfilling history for {symbol}...")
                backfill_history(symbol, target_date, delivery_cache)
                continue
                
            # If CSV exists, read existing dates to prevent duplicate rows
            existing_dates = set()
            with open(csv_path, "r") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    existing_dates.add(row["date"])
                    
            if date_str in existing_dates:
                logger.info(f"[{idx}/{len(SWING_STOCKS)}] {symbol}: Data for {date_str} already exists. Skipping.")
                continue
                
            # Fetch today's price using yfinance
            today_price = fetch_yfinance_history(symbol, target_date, target_date)
            if not today_price:
                logger.warning(f"[{idx}/{len(SWING_STOCKS)}] {symbol}: Could not fetch price for {date_str}. Skipping.")
                continue
                
            # Fetch today's delivery metrics
            stock_delivery = today_delivery.get(symbol, {})
            
            # Append today's data row
            today_record = today_price[0]
            today_record["delivery_qty"] = stock_delivery.get("deliverable_quantity", 0)
            today_record["delivery_pct"] = stock_delivery.get("delivery_percentage", 0.0)
            
            with open(csv_path, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["date", "open", "high", "low", "close", "volume", "delivery_qty", "delivery_pct"])
                writer.writerow(today_record)
                
            logger.info(f"✅ [{idx}/{len(SWING_STOCKS)}] {symbol}: Appended daily row for {date_str}.")
            
        except Exception as e:
            logger.error(f"❌ Error updating {symbol}: {e}")

def main():
    # Setup parser for custom dates
    import argparse
    parser = argparse.ArgumentParser(description="Collect daily swing trading stock and delivery data.")
    parser.add_argument("--date", help="Target date in YYYY-MM-DD format (Default: Today)", default=None)
    args = parser.parse_args()
    
    # Calculate target date in IST
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        now_ist = datetime.now(IST)
        # Avoid running on weekends
        if now_ist.weekday() >= 5:
            logger.info("Today is a weekend. Swing data collection is skipped on weekends.")
            sys.exit(0)
        target_date = now_ist
        
    process_daily_update(target_date)

if __name__ == "__main__":
    main()
