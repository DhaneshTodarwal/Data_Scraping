#!/usr/bin/env python3
"""
Intraday Indicators Logger
Runs continuously between 09:15 AM and 03:30 PM IST on weekdays.
Logs Nifty Spot, BankNifty Spot, India VIX, and Option Chain PCR every 60 seconds.
"""
import os
import sys
import time
import csv
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Add project directories to sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR.parent
PROJECT_ROOT = Path("/home/dhanesh-todarwal/nifty_options_scanner")
sys.path.insert(0, str(PROJECT_ROOT))

from angel_client import AngelClient
from config import INDEX_TOKENS, STRIKE_STEPS

# Timezone
IST = timezone(timedelta(hours=5, minutes=30))

# Target data directory
DATA_DIR = BASE_DIR / "data" / "intraday_indicators"

# Logging setup
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "intraday_logger.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("IntradayLogger")

def get_atm_strike(spot, step):
    """Round spot to nearest strike step."""
    return round(spot / step) * step

def compute_pcr(client, symbol, spot_price):
    """
    Fetch nearest expiry option chain and compute Put-Call Ratio (PCR).
    PCR = Total Put Open Interest / Total Call Open Interest
    """
    try:
        step = STRIKE_STEPS.get(symbol, 50)
        atm_strike = get_atm_strike(spot_price, step)
        
        # Get options for nearest expiry (num_expiries=1)
        expiry_data = client.get_option_instruments(symbol, atm_strike, num_expiries=1)
        if not expiry_data:
            logger.warning(f"No option instruments found for {symbol}")
            return 0.0
            
        # Get options list for the nearest expiry
        expiry_str = list(expiry_data.keys())[0]
        options = expiry_data[expiry_str]
        
        # Batch fetch market data to get Open Interest (OI)
        tokens = [opt['token'] for opt in options]
        market_data = client.get_market_data_full('NFO', tokens)
        
        if not market_data:
            logger.warning(f"No market data fetched for {symbol} options")
            return 0.0
            
        # Map token to option details
        token_to_type = {opt['token']: opt['option_type'] for opt in options}
        
        total_call_oi = 0
        total_put_oi = 0
        
        for item in market_data:
            token = item.get('symbolToken')
            oi = int(item.get('opnInterest', 0))
            opt_type = token_to_type.get(token)
            
            if opt_type == 'CE':
                total_call_oi += oi
            elif opt_type == 'PE':
                total_put_oi += oi
                
        if total_call_oi == 0:
            return 0.0
            
        pcr = total_put_oi / total_call_oi
        logger.info(f"{symbol} PCR: {pcr:.4f} (Put OI: {total_put_oi}, Call OI: {total_call_oi})")
        return pcr
        
    except Exception as e:
        logger.error(f"Error computing PCR for {symbol}: {e}")
        return 0.0

def main():
    logger.info("Initializing Intraday Indicators Logger...")
    
    # Check for market holidays
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import market_holidays
        is_holiday, reason = market_holidays.get_market_status(datetime.now(IST))
        if is_holiday:
            logger.info(f"📅 Market Holiday: {reason}. Skipping intraday logging.")
            sys.exit(0)
    except Exception as e:
        logger.error(f"Error checking market holiday: {e}")
        
    # Initialize Angel Client
    client = AngelClient()
    if not client.login():
        logger.error("Failed to login to Angel One API. Exiting.")
        sys.exit(1)
        
    client.load_instruments()
    
    try:
        while True:
            now_ist = datetime.now(IST)
            
            # Check market hours (Weekdays 09:15 - 15:30)
            is_weekday = now_ist.weekday() < 5
            market_start = now_ist.replace(hour=9, minute=15, second=0, microsecond=0)
            market_end = now_ist.replace(hour=15, minute=30, second=0, microsecond=0)
            
            if not is_weekday:
                logger.info("Today is a weekend. Exiting logger.")
                break
                
            if now_ist < market_start:
                sleep_secs = (market_start - now_ist).total_seconds()
                logger.info(f"Market not open yet. Sleeping for {sleep_secs:.0f} seconds until 09:15 AM.")
                time.sleep(min(sleep_secs, 60))
                continue
                
            if now_ist > market_end:
                logger.info("Market closed. Exiting logger.")
                break
                
            # Perform Data Collection
            logger.info("Collecting intraday ticks...")
            try:
                # Fetch Spot prices
                nifty_spot = client.get_ltp('NIFTY')
                banknifty_spot = client.get_ltp('BANKNIFTY')
                vix = client.get_ltp('VIX')
                
                if not nifty_spot or not banknifty_spot or not vix:
                    logger.warning("Failed to fetch spot prices or VIX. Retrying in next cycle.")
                    time.sleep(10)
                    continue
                
                # Fetch PCRs
                nifty_pcr = compute_pcr(client, 'NIFTY', nifty_spot)
                banknifty_pcr = compute_pcr(client, 'BANKNIFTY', banknifty_spot)
                
                # Prepare directories and file
                today_str = now_ist.strftime("%Y-%m-%d")
                year_str = now_ist.strftime("%Y")
                month_str = now_ist.strftime("%B")
                
                target_dir = DATA_DIR / year_str / month_str
                target_dir.mkdir(parents=True, exist_ok=True)
                csv_file = target_dir / f"{today_str}.csv"
                
                # Initialize CSV headers if file doesn't exist
                file_exists = csv_file.exists()
                with open(csv_file, 'a', newline='') as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow([
                            'Timestamp', 'Nifty_Spot', 'BankNifty_Spot', 
                            'India_VIX', 'Nifty_PCR', 'BankNifty_PCR'
                        ])
                    
                    writer.writerow([
                        now_ist.strftime("%Y-%m-%d %H:%M:%S"),
                        f"{nifty_spot:.2f}",
                        f"{banknifty_spot:.2f}",
                        f"{vix:.2f}",
                        f"{nifty_pcr:.4f}",
                        f"{banknifty_pcr:.4f}"
                    ])
                logger.info(f"Logged ticks to {csv_file}")
                
            except Exception as ex:
                logger.exception(f"Exception during collection cycle: {ex}")
                
            # Sleep until next minute boundary
            time.sleep(60)
            
    except KeyboardInterrupt:
        logger.info("Logger stopped by user.")
    finally:
        client.logout()

if __name__ == "__main__":
    main()
