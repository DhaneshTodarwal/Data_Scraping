"""
F&O Daily Data Collector
========================
Downloads the daily NSE F&O UDiFF Bhavcopy, parses spot/futures/options metrics
for watchlist stocks and indices, and updates the historical database.

Created: 2026-06-25
"""

import os
import sys
import csv
import zipfile
import io
import time
import argparse
import logging
import math
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

# Setup directories
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR = BASE_DIR / "data" / "fno_intelligence"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR = BASE_DIR / "data" / "cache" / "fno_bhavcopy"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "fno_data_collector.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("FnODataCollector")

# Import watchlist symbols dynamically to avoid duplication
try:
    sys.path.append(str(Path(__file__).parent))
    from swing_data_collector import SWING_STOCKS
except Exception as e:
    logger.warning(f"Could not import SWING_STOCKS from swing_data_collector: {e}")
    SWING_STOCKS = []

# Ensure index symbols are included in collection
WATCHLIST = list(dict.fromkeys(["NIFTY", "BANKNIFTY"] + SWING_STOCKS))

# Constants
RISK_FREE_RATE = 0.065  # 6.5% standard Indian risk-free rate

# --- Pure Python Black-Scholes Normal Distributions for IV Calculation ---
def normal_pdf(x: float) -> float:
    """Standard Normal Probability Density Function."""
    return math.exp(-0.5 * x**2) / math.sqrt(2 * math.pi)

def normal_cdf(x: float) -> float:
    """Standard Normal Cumulative Distribution Function (Abramowitz & Stegun approximation)."""
    if x < 0:
        return 1.0 - normal_cdf(-x)
    p = 0.2316419
    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429
    t = 1.0 / (1.0 + p * x)
    return 1.0 - normal_pdf(x) * (t * (b1 + t * (b2 + t * (b3 + t * (b4 + t * b5)))))

def bs_call_price(spot: float, strike: float, time_to_expiry: float, vol: float, r: float = RISK_FREE_RATE) -> float:
    """Theoretical Call price using Black-Scholes."""
    if time_to_expiry <= 0:
        return max(spot - strike, 0.0)
    if vol <= 0:
        return max(spot - strike, 0.0)
    d1 = (math.log(spot / strike) + (r + 0.5 * vol**2) * time_to_expiry) / (vol * math.sqrt(time_to_expiry))
    d2 = d1 - vol * math.sqrt(time_to_expiry)
    return spot * normal_cdf(d1) - strike * math.exp(-r * time_to_expiry) * normal_cdf(d2)

def bs_put_price(spot: float, strike: float, time_to_expiry: float, vol: float, r: float = RISK_FREE_RATE) -> float:
    """Theoretical Put price using Black-Scholes."""
    if time_to_expiry <= 0:
        return max(strike - spot, 0.0)
    if vol <= 0:
        return max(strike - spot, 0.0)
    d1 = (math.log(spot / strike) + (r + 0.5 * vol**2) * time_to_expiry) / (vol * math.sqrt(time_to_expiry))
    d2 = d1 - vol * math.sqrt(time_to_expiry)
    return strike * math.exp(-r * time_to_expiry) * normal_cdf(-d2) - spot * normal_cdf(-d1)

def bs_vega(spot: float, strike: float, time_to_expiry: float, vol: float, r: float = RISK_FREE_RATE) -> float:
    """Vega (sensitivity to volatility) - same for call and put."""
    if time_to_expiry <= 0 or vol <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (r + 0.5 * vol**2) * time_to_expiry) / (vol * math.sqrt(time_to_expiry))
    return spot * normal_pdf(d1) * math.sqrt(time_to_expiry)

def calculate_implied_volatility(price: float, spot: float, strike: float, time_to_expiry: float, option_type: str, r: float = RISK_FREE_RATE) -> float:
    """Calculate implied volatility using the Newton-Raphson numerical method."""
    if time_to_expiry <= 0 or price <= 0.01:
        return 0.0
    
    # Intrinsic boundary checks
    if option_type == 'CE' and price < max(spot - strike * math.exp(-r * time_to_expiry), 0.0):
        return 0.0
    if option_type == 'PE' and price < max(strike * math.exp(-r * time_to_expiry) - spot, 0.0):
        return 0.0

    vol = 0.20  # Initial guess (20% IV)
    for _ in range(50):
        if option_type == 'CE':
            th_price = bs_call_price(spot, strike, time_to_expiry, vol, r)
        else:
            th_price = bs_put_price(spot, strike, time_to_expiry, vol, r)
            
        diff = th_price - price
        if abs(diff) < 1e-4:
            return round(vol, 4)
            
        vega = bs_vega(spot, strike, time_to_expiry, vol, r)
        if vega < 1e-4:
            break
            
        vol = vol - diff / (vega * 100)  # adjustment
        if vol <= 0.001 or vol > 5.0:
            break
            
    # Fallback to Bisection search if Newton-Raphson diverges
    low_vol, high_vol = 0.001, 3.0
    for _ in range(30):
        mid_vol = (low_vol + high_vol) / 2
        if option_type == 'CE':
            th_price = bs_call_price(spot, strike, time_to_expiry, mid_vol, r)
        else:
            th_price = bs_put_price(spot, strike, time_to_expiry, mid_vol, r)
            
        if abs(th_price - price) < 1e-3:
            return round(mid_vol, 4)
        if th_price > price:
            high_vol = mid_vol
        else:
            low_vol = mid_vol
            
    return round((low_vol + high_vol) / 2, 4)

# --- Downloader & Parser Logic ---
def download_fno_bhavcopy(target_date: datetime) -> Optional[bytes]:
    """Download the official F&O UDiFF Bhavcopy ZIP from NSE Archives."""
    date_str = target_date.strftime("%Y%m%d")
    year_str = target_date.strftime("%Y")
    month_str = target_date.strftime("%b").upper()
    
    # Save path in cache
    local_zip = CACHE_DIR / f"BhavCopy_NSE_FO_0_0_0_{date_str}_F_0000.csv.zip"
    if local_zip.exists():
        logger.info(f"Using cached Bhavcopy zip file for {date_str}.")
        return local_zip.read_bytes()
        
    url = f"https://nsearchives.nseindia.com/content/fo/BhavCopy_NSE_FO_0_0_0_{date_str}_F_0000.csv.zip"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': '*/*'
    }
    
    try:
        logger.info(f"Downloading F&O Bhavcopy for {target_date.strftime('%Y-%m-%d')}...")
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            local_zip.write_bytes(res.content)
            logger.info("✅ Download successful and saved to cache.")
            return res.content
        elif res.status_code == 404:
            logger.warning(f"⚠️ F&O Bhavcopy file not found (404) for {target_date.strftime('%Y-%m-%d')}. Weekend or Holiday?")
            return None
        else:
            logger.error(f"Failed to download. Status: {res.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error downloading Bhavcopy: {e}")
        return None

def parse_bhavcopy(zip_content: bytes) -> Dict[str, List[Dict]]:
    """Parse the unzipped F&O Bhavcopy CSV, grouping rows by Ticker Symbol."""
    grouped_data = {}
    try:
        with zipfile.ZipFile(io.BytesIO(zip_content)) as z:
            csv_filename = z.namelist()[0]
            with z.open(csv_filename) as f:
                reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
                for row in reader:
                    symbol = row['TckrSymb'].strip()
                    if symbol in WATCHLIST:
                        if symbol not in grouped_data:
                            grouped_data[symbol] = []
                        grouped_data[symbol].append(row)
    except Exception as e:
        logger.error(f"Error parsing unzipped CSV content: {e}")
    return grouped_data

def process_symbol_fno_data(symbol: str, rows: List[Dict], target_date: datetime) -> Optional[Dict]:
    """Extract spot, near-month futures, PCR, Support/Resistance (OI), and ATM IV."""
    try:
        # 1. Determine Spot Price from underlying price column
        spot = 0.0
        for r in rows:
            val = r.get('UndrlygPric')
            if val and float(val) > 0:
                spot = float(val)
                break
        if spot == 0.0:
            logger.warning(f"No valid spot price found in file for {symbol}.")
            return None

        # 2. Separate Futures and Options Expiries
        fut_inst_type = 'STF' if symbol not in ["NIFTY", "BANKNIFTY"] else 'IDF'
        fut_expiries = sorted(list(set(r['XpryDt'] for r in rows if r['XpryDt'] and r['FinInstrmTp'] == fut_inst_type)))
        
        opt_inst_type = 'STO' if symbol not in ["NIFTY", "BANKNIFTY"] else 'IDO'
        opt_expiries = sorted(list(set(r['XpryDt'] for r in rows if r['XpryDt'] and r['FinInstrmTp'] == opt_inst_type)))

        if not opt_expiries:
            return None
        near_opt_expiry_str = opt_expiries[0]
        near_opt_expiry = datetime.strptime(near_opt_expiry_str, "%Y-%m-%d")
        days_to_expiry = max((near_opt_expiry - target_date).days, 0)
        time_to_expiry = days_to_expiry / 365.0

        near_fut_expiry_str = fut_expiries[0] if fut_expiries else near_opt_expiry_str

        # 3. Process Future Contract (Near-Month STF / IDF)
        fut_close, fut_oi, fut_oi_chg, fut_volume = 0.0, 0, 0, 0
        
        fut_rows = [r for r in rows if r['FinInstrmTp'] == fut_inst_type and r['XpryDt'] == near_fut_expiry_str]
        if fut_rows:
            f_row = fut_rows[0]
            fut_close = float(f_row['ClsPric'])
            fut_oi = int(f_row['OpnIntrst'])
            fut_oi_chg = int(f_row['ChngInOpnIntrst'])
            fut_volume = int(f_row['TtlTradgVol'])

        # 4. Process Option Contacts (Near-Month STO / IDO)
        opt_rows = [r for r in rows if r['FinInstrmTp'] == opt_inst_type and r['XpryDt'] == near_opt_expiry_str]
        
        total_call_oi = 0
        total_put_oi = 0
        max_call_oi = 0
        max_call_strike = 0.0
        max_put_oi = 0
        max_put_strike = 0.0
        
        strikes = []
        ce_by_strike = {}
        pe_by_strike = {}

        for r in opt_rows:
            strike = float(r['StrkPric'])
            opt_type = r['OptnTp'].strip()
            oi = int(r['OpnIntrst'])
            close = float(r['ClsPric'])
            
            strikes.append(strike)
            if opt_type == 'CE':
                total_call_oi += oi
                ce_by_strike[strike] = {'oi': oi, 'close': close}
                if oi > max_call_oi:
                    max_call_oi = oi
                    max_call_strike = strike
            elif opt_type == 'PE':
                total_put_oi += oi
                pe_by_strike[strike] = {'oi': oi, 'close': close}
                if oi > max_put_oi:
                    max_put_oi = oi
                    max_put_strike = strike

        # Put-Call Ratio
        pcr = round(total_put_oi / total_call_oi, 4) if total_call_oi > 0 else 0.0
        strikes = sorted(list(set(strikes)))

        # 5. ATM Implied Volatility Calculation
        atm_iv = 0.0
        if strikes and spot > 0:
            # Find strike closest to spot
            atm_strike = min(strikes, key=lambda s: abs(s - spot))
            atm_ce = ce_by_strike.get(atm_strike)
            atm_pe = pe_by_strike.get(atm_strike)
            
            iv_ce = 0.0
            iv_pe = 0.0
            if atm_ce and atm_ce['close'] > 0:
                iv_ce = calculate_implied_volatility(atm_ce['close'], spot, atm_strike, time_to_expiry, 'CE')
            if atm_pe and atm_pe['close'] > 0:
                iv_pe = calculate_implied_volatility(atm_pe['close'], spot, atm_strike, time_to_expiry, 'PE')
                
            # If both valid, average them, else take whichever is positive
            if iv_ce > 0 and iv_pe > 0:
                atm_iv = round((iv_ce + iv_pe) / 2.0, 4)
            elif iv_ce > 0:
                atm_iv = iv_ce
            elif iv_pe > 0:
                atm_iv = iv_pe

        return {
            "Date": target_date.strftime("%Y-%m-%d"),
            "Spot_Price": spot,
            "Fut_Close": fut_close,
            "Fut_OI": fut_oi,
            "Fut_OI_Chg": fut_oi_chg,
            "Fut_Volume": fut_volume,
            "Near_Expiry": near_opt_expiry_str,
            "Max_Call_OI_Strike": max_call_strike,
            "Max_Call_OI": max_call_oi,
            "Max_Put_OI_Strike": max_put_strike,
            "Max_Put_OI": max_put_oi,
            "PCR_OI": pcr,
            "ATM_IV": atm_iv
        }
    except Exception as e:
        logger.error(f"Error processing F&O metrics for {symbol}: {e}")
        return None

def update_symbol_csv_db(symbol: str, data: Dict):
    """Save or append daily F&O summary row into stock specific CSV."""
    symbol_dir = DATA_DIR / "stocks" / symbol
    symbol_dir.mkdir(parents=True, exist_ok=True)
    csv_path = symbol_dir / "daily_fno_summary.csv"
    
    headers = [
        "Date", "Spot_Price", "Fut_Close", "Fut_OI", "Fut_OI_Chg", "Fut_Volume", 
        "Near_Expiry", "Max_Call_OI_Strike", "Max_Call_OI", "Max_Put_OI_Strike", "Max_Put_OI", 
        "PCR_OI", "ATM_IV"
    ]
    
    # Read existing rows to prevent duplicate date insertion
    existing_rows = []
    if csv_path.exists():
        try:
            with open(csv_path, 'r', newline='') as f:
                reader = csv.DictReader(f)
                existing_rows = list(reader)
        except Exception as e:
            logger.error(f"Error reading {csv_path}: {e}")

    # Remove existing row for today if present
    existing_rows = [r for r in existing_rows if r["Date"] != data["Date"]]
    
    # Append the new row and sort by date
    new_row = {k: str(data[k]) for k in headers}
    existing_rows.append(new_row)
    existing_rows.sort(key=lambda x: x["Date"])
    
    try:
        with open(csv_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(existing_rows)
    except Exception as e:
        logger.error(f"Error writing update to {csv_path}: {e}")

def run_collector(target_date: datetime):
    """Run EOD collection and extraction for the entire watchlist."""
    logger.info(f"=== Starting EOD F&O Collector for {target_date.strftime('%Y-%m-%d')} ===")
    zip_content = download_fno_bhavcopy(target_date)
    if not zip_content:
        logger.warning("No Bhavcopy file downloaded. Stopping execution.")
        return
        
    grouped_data = parse_bhavcopy(zip_content)
    if not grouped_data:
        logger.warning("No watchlist stock data parsed from Bhavcopy. Stopping.")
        return
        
    logger.info(f"Parsed F&O data for {len(grouped_data)} watchlist symbols from Bhavcopy.")
    
    success_count = 0
    for symbol in WATCHLIST:
        if symbol not in grouped_data:
            continue
        rows = grouped_data[symbol]
        metrics = process_symbol_fno_data(symbol, rows, target_date)
        if metrics:
            update_symbol_csv_db(symbol, metrics)
            success_count += 1
            
    logger.info(f"Successfully processed and updated databases for {success_count} stocks.")
    logger.info("=== EOD F&O Collector Execution Complete ===")

# --- Backfill Mode Function ---
def backfill_history(days: int = 15):
    """Backfill F&O historical data for the last N trading days."""
    logger.info(f"=== Initializing Historical F&O Backfill (Last {days} days) ===")
    current = datetime.now()
    dates_to_process = []
    
    # Generate dates looking back
    step = 0
    while len(dates_to_process) < days and step < 60:  # Safety boundary
        check_date = current - timedelta(days=step)
        # Skip Sundays and Saturdays
        if check_date.weekday() < 5:
            dates_to_process.append(check_date)
        step += 1
        
    # Process oldest first
    dates_to_process.reverse()
    logger.info(f"Identified {len(dates_to_process)} weekdays to check for F&O data.")
    
    for d in dates_to_process:
        run_collector(d)
        time.sleep(1)  # small rate-limit safety

# --- Main Entry Point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NSE F&O EOD Data Collector")
    parser.add_argument("--date", type=str, help="Specific target date in YYYY-MM-DD format")
    parser.add_argument("--backfill", type=int, help="Backfill historical F&O data for N days")
    
    args = parser.parse_args()
    
    if args.backfill:
        backfill_history(args.backfill)
    elif args.date:
        target = datetime.strptime(args.date, "%Y-%m-%d")
        run_collector(target)
    else:
        # Default to today's date
        run_collector(datetime.now())
