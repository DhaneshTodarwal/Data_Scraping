"""
Enhanced Angel One Complete Collector
======================================
Collects:
1. Index OHLCV (minute candles)
2. Options OHLCV (minute candles)
3. Option Chain Snapshot (IV, OI, PCR) - END OF DAY

Created: 2026-01-16
"""

import os
import csv
import json
import time
import logging
import pyotp
import requests
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from SmartApi import SmartConnect
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Import metadata generator
from metadata_generator import MetadataGenerator

# Import notification system
try:
    from notifications import (
        send_desktop_notification,
        send_telegram_message,
        notify_collection_started,
        notify_collection_success,
        notify_collection_failed
    )
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False
    logger.warning("Notifications module not available")

# Setup Logging
LOG_DIR = Path(__file__).parent.parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / f"collection_{datetime.now().strftime('%Y%m%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AngelOneCollector")

# Load environment
def load_env():
    env_path = Path(__file__).parent.parent / '.env'
    if env_path.exists():
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())

load_env()

# Configuration
API_KEY = os.getenv('ANGEL_API_KEY')
CLIENT_ID = os.getenv('ANGEL_CLIENT_ID')
PIN = os.getenv('ANGEL_PIN')
TOTP_SECRET = os.getenv('ANGEL_TOTP_SECRET')

# Constants
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
CACHE_DIR = BASE_DIR / 'scripts' / 'cache'
INSTRUMENT_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

STRIKE_RANGE = 20  # ATM +/- 20 strikes
STEP_NIFTY = 50
STEP_BANKNIFTY = 100

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class AngelOneEnhanced:
    """Enhanced data collector with option chain snapshots."""
    
    def __init__(self):
        self._validate_credentials()
        self.smart_api = SmartConnect(api_key=API_KEY)
        self.logged_in = False
        self.totp = pyotp.TOTP(TOTP_SECRET)
        self.instruments = []
        self.session = self._create_retry_session()
        
    def _validate_credentials(self):
        """Validate credentials."""
        if not all([API_KEY, CLIENT_ID, PIN, TOTP_SECRET]):
            logger.error("Missing credentials in .env file")
            raise ValueError("Missing credentials")

    def _create_retry_session(self):
        """Create requests session with retry logic."""
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        return session

    def login(self) -> bool:
        """Auto login."""
        try:
            totp_code = self.totp.now()
            logger.info(f"Attempting login for {CLIENT_ID}...")
            
            data = self.smart_api.generateSession(
                clientCode=CLIENT_ID,
                password=PIN,
                totp=totp_code
            )
            
            if data.get('status'):
                self.logged_in = True
                logger.info("✅ Login successful")
                return True
            else:
                logger.error(f"❌ Login failed: {data.get('message')}")
                return False
        except Exception as e:
            logger.exception(f"❌ Login exception: {e}")
            return False

    def load_instruments(self) -> bool:
        """Load instrument list with caching."""
        date_str = datetime.now().strftime('%Y%m%d')
        cache_file = CACHE_DIR / f"instruments_{date_str}.json"
        
        # Cleanup old cache files
        for f in CACHE_DIR.glob("instruments_*.json"):
            if f.name != cache_file.name:
                try:
                    f.unlink()
                except:
                    pass

        if cache_file.exists():
            logger.info("Loading instruments from cache...")
            try:
                with open(cache_file, 'r') as f:
                    self.instruments = json.load(f)
                return True
            except json.JSONDecodeError:
                logger.warning("Cache file corrupted, downloading fresh...")

        logger.info("Downloading fresh instrument list...")
        try:
            response = self.session.get(INSTRUMENT_URL, timeout=60)
            response.raise_for_status()
            self.instruments = response.json()
            
            with open(cache_file, 'w') as f:
                json.dump(self.instruments, f)
            logger.info(f"✅ Downloaded {len(self.instruments)} instruments")
            return True
        except Exception as e:
            logger.error(f"❌ Error downloading instruments: {e}")
            return False

    def get_option_chain_snapshot(self, symbol: str, atm_strike: float, step: int) -> List[Dict]:
        """
        Get current option chain data with IV, OI, Volume, LTP.
        This is Angel One's getMarketData API call.
        """
        if not self.logged_in:
            return []
        
        option_chain = []
        options = self.get_option_instruments(symbol, atm_strike, step)
        
        if not options:
            return []
        
        logger.info(f"  Fetching option chain data for {len(options)} strikes...")
        
        for opt in options:
            try:
                # Get market data for this option
                data = self.smart_api.marketData(
                    mode="FULL",
                    exchangeTokens={
                        "NFO": [opt['token']]
                    }
                )
                
                if data and data.get('status') and data.get('data'):
                    market_data = data['data'][0]
                    
                    option_chain.append({
                        'symbol': opt['symbol'],
                        'strike': opt['strike'],
                        'option_type': opt['option_type'],
                        'ltp': float(market_data.get('ltp', 0)),
                        'oi': int(market_data.get('oi', 0)),
                        'volume': int(market_data.get('volume', 0)),
                        'change_oi': int(market_data.get('oichangepercent', 0)),
                        # IV not directly available from Angel One API
                        # Would need to calculate using Black-Scholes
                    })
                
                time.sleep(0.1)  # Rate limit
                
            except Exception as e:
                logger.error(f"Error fetching market data for {opt['symbol']}: {e}")
        
        return option_chain

    def save_option_chain_snapshot(self, symbol: str, chain_data: List[Dict]):
        """Save option chain snapshot to JSON."""
        today = datetime.now()
        year = today.strftime('%Y')
        month = today.strftime('%m_%B')
        day = today.strftime('%d')
        
        save_dir = DATA_DIR / 'option_chain' / symbol / year / month / day
        save_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = save_dir / 'snapshot_eod.json'
        
        # Organize data by strike
        organized_data = {}
        for item in chain_data:
            strike = item['strike']
            if strike not in organized_data:
                organized_data[strike] = {'strike': strike}
            
            opt_type = item['option_type'].lower()
            organized_data[strike][f'{opt_type}_ltp'] = item['ltp']
            organized_data[strike][f'{opt_type}_oi'] = item['oi']
            organized_data[strike][f'{opt_type}_volume'] = item['volume']
            organized_data[strike][f'{opt_type}_change_oi'] = item['change_oi']
        
        # Calculate PCR
        total_ce_oi = sum(d.get('ce_oi', 0) for d in organized_data.values())
        total_pe_oi = sum(d.get('pe_oi', 0) for d in organized_data.values())
        pcr = round(total_pe_oi / total_ce_oi, 2) if total_ce_oi > 0 else 0
        
        snapshot = {
            'symbol': symbol,
            'date': today.strftime('%Y-%m-%d'),
            'time': today.strftime('%H:%M:%S'),
            'pcr': pcr,
            'strikes': list(organized_data.values())
        }
        
        with open(filepath, 'w') as f:
            json.dump(snapshot, f, indent=2)
        
        logger.info(f"  ✅ Option chain snapshot saved: {len(organized_data)} strikes, PCR: {pcr}")
        return pcr

    # ... (rest of the methods from angelone_complete.py remain the same)
    # get_ltp, get_atm_strike, get_option_instruments, get_historical_candles,
    # collect_index_data, collect_options_data_with_tracking, save_csv, run, logout


if __name__ == "__main__":
    collector = AngelOneEnhanced()
    collector.run()
