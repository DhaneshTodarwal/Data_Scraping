"""
Angel One Professional Data Collector
======================================
Automated collection of NIFTY/BANKNIFTY Index and Options OHLCV data.
Organizes data in a hierarchical, easy-to-navigate folder structure.

Structure:
- Index:  data/index_ohlcv/{SYMBOL}/{YYYY_MM_Month}/{YYYY-MM-DD}.csv
- Option: data/strikes_ohlcv/{SYMBOL}/{YYYY}/{MM_Month}/{DD}/{CE|PE}/{STRIKE}.csv

Features:
- Auto-Login with TOTP
- Robust Error Handling & Retries
- ATM ±20 Strikes Collection
- Clean Logging

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
try:
    from metadata_generator import MetadataGenerator
except ImportError:
    from scripts.metadata_generator import MetadataGenerator

# Import notification system
try:
    try:
        from notifications import (
            send_desktop_notification,
            send_telegram_message,
            notify_collection_started,
            notify_collection_success,
            notify_collection_failed
        )
    except ImportError:
        from scripts.notifications import (
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
STEP_SENSEX = 100  # SENSEX uses 100 step like BANKNIFTY

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)


class AngelOneComplete:
    """Professional Data Collector with Hierarchical Storage."""
    
    def __init__(self):
        self._validate_credentials()
        self.smart_api = SmartConnect(api_key=API_KEY)
        self.logged_in = False
        self.totp = pyotp.TOTP(TOTP_SECRET)
        self.instruments = []
        self.session = self._create_retry_session()
        
    def _validate_credentials(self):
        """Validate that all required credentials are present."""
        if not all([API_KEY, CLIENT_ID, PIN, TOTP_SECRET]):
            logger.error("Missing credentials in .env file")
            raise ValueError("Missing credentials")

    def _create_retry_session(self):
        """Create a requests session with retry logic."""
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
        session.mount('https://', HTTPAdapter(max_retries=retries))
        return session

    def login(self) -> bool:
        """Auto login with robust error handling."""
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

    def get_ltp(self, symbol: str) -> Optional[float]:
        """Get current LTP with safe token mapping."""
        if not self.logged_in:
            return None
        
        tokens = {
            'NIFTY': ('NSE', 'NIFTY', '99926000'),
            'BANKNIFTY': ('NSE', 'BANKNIFTY', '99926009'),
            'SENSEX': ('BSE', 'SENSEX', '99919000'),
        }
        
        try:
            exch, sym, token = tokens.get(symbol, (None, None, None))
            if not token:
                raise ValueError(f"Unknown symbol: {symbol}")

            data = self.smart_api.ltpData(exch, sym, token)
            if data and data.get('status'):
                return float(data['data']['ltp'])
        except Exception as e:
            logger.error(f"Error fetching LTP for {symbol}: {e}")
        return None

    def get_atm_strike(self, ltp: float, step: int) -> float:
        """Calculate ATM strike price."""
        return round(ltp / step) * step

    def get_option_instruments(self, symbol: str, atm_strike: float, step: int) -> List[Dict]:
        """Get option instruments for the nearest available expiry."""
        options = []
        today = datetime.now().date()
        
        # Use BFO for SENSEX, NFO for NIFTY/BANKNIFTY
        exch_seg = 'BFO' if symbol == 'SENSEX' else 'NFO'
        
        # 1. Collect all valid expiries for this symbol
        available_expiries = set()
        for inst in self.instruments:
            if inst.get('name') == symbol and inst.get('exch_seg') == exch_seg:
                exp_str = inst.get('expiry', '')
                if exp_str:
                    try:
                        # Parse expiry date (format DDMMMYYYY e.g. 27JAN2026)
                        exp_date = datetime.strptime(exp_str, '%d%b%Y').date()
                        if exp_date >= today:
                            available_expiries.add(exp_date)
                    except ValueError:
                        pass
        
        if not available_expiries:
            logger.warning(f"No future expiries found for {symbol}")
            return []
            
        # 2. Select the nearest expiry
        sorted_expiries = sorted(list(available_expiries))
        target_expiry = sorted_expiries[0]
        target_expiry_str = target_expiry.strftime('%d%b%Y').upper() # e.g. 20JAN2026
        target_expiry_str_short = target_expiry.strftime('%d%b%y').upper() # e.g. 20JAN26
        
        logger.info(f"  🎯 Targeted Expiry for {symbol}: {target_expiry_str}")

        range_val = STRIKE_RANGE * step

        for inst in self.instruments:
            if inst.get('name') == symbol and inst.get('exch_seg') == exch_seg:
                tsym = inst.get('symbol', '').upper()
                strike = float(inst.get('strike', 0)) / 100
                
                # Check Strike Range
                if not (atm_strike - range_val <= strike <= atm_strike + range_val):
                    continue

                # Check Expiry
                # Symbol usually contains 20JAN26 (short year) or 20JAN2026
                # But sometimes monthly options have format like NIFTY26JAN...
                # Best check is strict expiry field match
                
                inst_expiry = inst.get('expiry', '')
                if inst_expiry == target_expiry_str:
                     options.append({
                        'symbol': tsym,
                        'token': inst.get('token'),
                        'strike': int(strike),
                        'option_type': 'CE' if 'CE' in tsym else 'PE',
                        'name': symbol
                    })
        
        return sorted(options, key=lambda x: (x['strike'], x['option_type']))

    def save_csv(self, data: List, filepath: Path):
        """Save data to CSV with standard header."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            writer.writerows(data)

    def get_historical_candles(self, exchange: str, token: str, days: int = 1) -> List:
        """Fetch historical candle data."""
        if not self.logged_in:
            return []
        
        now = datetime.now()
        from_date = (now - timedelta(days=days)).replace(hour=9, minute=15, second=0).strftime('%Y-%m-%d %H:%M')
        to_date = now.strftime('%Y-%m-%d %H:%M')
        
        params = {
            'exchange': exchange,
            'symboltoken': str(token),
            'interval': 'ONE_MINUTE',
            'fromdate': from_date,
            'todate': to_date
        }
        
        try:
            request_data = self.smart_api.getCandleData(params)
            if request_data and request_data.get('status'):
                 return request_data.get('data', [])
        except Exception as e:
            logger.error(f"Error fetching candles for {token}: {e}")
        
        return []

    def collect_index_data(self):
        """Collect Index Data in Hierarchical Folder Structure."""
        logger.info("📊 Collecting Index Data...")
        
        # Format: (symbol, token, exchange)
        indices = [
            ('NIFTY', '99926000', 'NSE'),
            ('BANKNIFTY', '99926009', 'NSE'),
            ('SENSEX', '99919000', 'BSE')  # BSE SENSEX
        ]
        
        today = datetime.now()
        year_str = today.strftime('%Y')        # e.g., 2026
        month_str = today.strftime('%b')       # e.g., Jan
        date_filename = today.strftime('%Y-%m-%d') + ".csv"  # e.g., 2026-01-16.csv
        
        for symbol, token, exchange in indices:
            candles = self.get_historical_candles(exchange, token, days=1)
            
            if candles:
                # Structure: data/index_ohlcv/{YYYY}/{Mon}/{SYMBOL}/
                save_path = DATA_DIR / 'index_ohlcv' / year_str / month_str / symbol / date_filename
                self.save_csv(candles, save_path)
                logger.info(f"  ✅ {symbol}: Saved {len(candles)} candles to {save_path.relative_to(BASE_DIR)}")
            else:
                logger.warning(f"  ⚠️ {symbol}: No data found")

    def collect_options_data(self):
        """Collect Options Data in Hierarchical Folder Structure."""
        logger.info("📊 Collecting Options Data...")
        
        indices = [
            ('NIFTY', STEP_NIFTY), 
            ('BANKNIFTY', STEP_BANKNIFTY),
            ('SENSEX', STEP_SENSEX)
        ]
        
        today = datetime.now()
        year_str = today.strftime('%Y')
        month_str = today.strftime('%m_%B')
        day_str = today.strftime('%d')
        
        for symbol, step in indices:
            ltp = self.get_ltp(symbol)
            if not ltp:
                continue
                
            atm = self.get_atm_strike(ltp, step)
            logger.info(f"  🔹 {symbol} LTP: {ltp} | ATM: {atm}")
            
            options = self.get_option_instruments(symbol, atm, step)
            if not options:
                logger.warning(f"  ⚠️ No options found for {symbol}")
                continue
                
            logger.info(f"  Found {len(options)} strikes (ATM ±{STRIKE_RANGE})")
            
            count = 0
            for opt in options:
                candles = self.get_historical_candles('NFO', opt['token'], days=1)
                
                if candles:
                    # Structure: data/strikes_ohlcv/{SYMBOL}/{YYYY}/{MM_Month}/{DD}/{CE|PE}/{STRIKE}.csv
                    opt_type = opt['option_type'] # CE or PE
                    strike_price = str(opt['strike'])
                    
                    save_dir = DATA_DIR / 'strikes_ohlcv' / symbol / year_str / month_str / day_str / opt_type
                    save_path = save_dir / f"{strike_price}.csv"
                    
                    self.save_csv(candles, save_path)
                    count += 1
                    # Small delay to prevent rate limits (3 req/sec limit)
                    time.sleep(0.4)
            
            logger.info(f"  ✅ {symbol}: Saved data for {count}/{len(options)} options")

    def run(self):
        """Main execution flow with metadata generation."""
        logger.info("="*60)
        logger.info("ANGEL ONE DATA COLLECTION START")
        logger.info("="*60)
        
        # Send start notification
        if NOTIFICATIONS_AVAILABLE:
            send_desktop_notification(
                "📊 Data Collection Started",
                "Collecting NIFTY & BANKNIFTY options data...",
                "normal"
            )
            send_telegram_message(
                "🚀 <b>Data Collection Started</b>\n\n"
                f"📅 Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                "📈 Indices: NIFTY, BANKNIFTY\n"
                "⏳ Status: In Progress..."
            )
        
        start_time = datetime.now()
        metadata = {
            "date": start_time.strftime('%Y-%m-%d'),
            "collection_time": start_time.strftime('%H:%M:%S'),
            "nifty": {},
            "banknifty": {},
            "total_files": 0,
            "errors": 0,
            "status": "failed"
        }
        
        if not self.login():
            return
            
        if not self.load_instruments():
            return
        
        # Get LTPs and ATMs
        nifty_ltp = self.get_ltp('NIFTY')
        banknifty_ltp = self.get_ltp('BANKNIFTY')
        
        if nifty_ltp:
            nifty_atm = self.get_atm_strike(nifty_ltp, STEP_NIFTY)
            metadata['nifty'] = {
                'ltp': nifty_ltp,
                'atm': nifty_atm,
                'strikes_collected': 0,
                'candles': 0
            }
        
        if banknifty_ltp:
            banknifty_atm = self.get_atm_strike(banknifty_ltp, STEP_BANKNIFTY)
            metadata['banknifty'] = {
                'ltp': banknifty_ltp,
                'atm': banknifty_atm,
                'strikes_collected': 0,
                'candles': 0
            }
            
        self.collect_index_data()
        
        # Collect options and track metrics
        nifty_count, banknifty_count, sensex_count = self.collect_options_data_with_tracking()
        
        if nifty_ltp:
            metadata['nifty']['strikes_collected'] = nifty_count
        if banknifty_ltp:
            metadata['banknifty']['strikes_collected'] = banknifty_count
        
        metadata['total_files'] = nifty_count + banknifty_count + sensex_count + 3  # +3 for index files
        metadata['status'] = 'success'
        
        # Save metadata
        try:
            meta_gen = MetadataGenerator(BASE_DIR)
            meta_gen.save_metadata(metadata)
            logger.info("✅ Metadata saved")
        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")
        
        # Send success notification
        if NOTIFICATIONS_AVAILABLE:
            send_desktop_notification(
                "✅ Data Collection Complete!",
                f"NIFTY: {nifty_count} | BANKNIFTY: {banknifty_count} | SENSEX: {sensex_count}",
                "normal"
            )
            telegram_msg = (
                "✅ <b>Data Collection Complete!</b>\n\n"
                f"📅 Date: {metadata['date']}\n"
                f"⏰ Time: {metadata['collection_time']}\n\n"
                f"📈 <b>NIFTY</b>\n"
                f"• LTP: ₹{metadata['nifty'].get('ltp', 'N/A')}\n"
                f"• ATM: {metadata['nifty'].get('atm', 'N/A')}\n"
                f"• Strikes: {nifty_count}\n\n"
                f"📈 <b>BANKNIFTY</b>\n"
                f"• LTP: ₹{metadata['banknifty'].get('ltp', 'N/A')}\n"
                f"• ATM: {metadata['banknifty'].get('atm', 'N/A')}\n"
                f"• Strikes: {banknifty_count}\n\n"
                f"📊 <b>SENSEX</b>\n"
                f"• Strikes: {sensex_count}\n\n"
                f"💾 Total Files: {metadata['total_files']}"
            )
            send_telegram_message(telegram_msg)
        
        self.logout()
        logger.info("="*60)
        logger.info("COLLECTION COMPLETED")
        logger.info("="*60)
    
    def collect_options_data_with_tracking(self):
        """Collect options with strike count tracking."""
        logger.info("📊 Collecting Options Data...")
        
        indices = [
            ('NIFTY', STEP_NIFTY), 
            ('BANKNIFTY', STEP_BANKNIFTY),
            ('SENSEX', STEP_SENSEX)
        ]
        
        today = datetime.now()
        year_str = today.strftime('%Y')
        month_str = today.strftime('%m_%B')
        day_str = today.strftime('%d')
        
        nifty_count = 0
        banknifty_count = 0
        sensex_count = 0
        
        for symbol, step in indices:
            ltp = self.get_ltp(symbol)
            if not ltp:
                continue
                
            atm = self.get_atm_strike(ltp, step)
            logger.info(f"  🔹 {symbol} LTP: {ltp} | ATM: {atm}")
            
            options = self.get_option_instruments(symbol, atm, step)
            if not options:
                logger.warning(f"  ⚠️ No options found for {symbol}")
                continue
                
            logger.info(f"  Found {len(options)} strikes (ATM ±{STRIKE_RANGE})")
            
            # Use BFO exchange for SENSEX, NFO for others
            exchange = 'BFO' if symbol == 'SENSEX' else 'NFO'
            
            count = 0
            for opt in options:
                candles = self.get_historical_candles(exchange, opt['token'], days=1)
                
                if candles:
                    opt_type = opt['option_type']
                    strike_price = str(opt['strike'])
                    
                    save_dir = DATA_DIR / 'strikes_ohlcv' / symbol / year_str / month_str / day_str / opt_type
                    save_path = save_dir / f"{strike_price}.csv"
                    
                    self.save_csv(candles, save_path)
                    count += 1
                    time.sleep(0.4)
            
            if symbol == 'NIFTY':
                nifty_count = count
            elif symbol == 'BANKNIFTY':
                banknifty_count = count
            else:
                sensex_count = count
            
            logger.info(f"  ✅ {symbol}: Saved data for {count}/{len(options)} options")
        
        return nifty_count, banknifty_count, sensex_count

    def logout(self):
        try:
            self.smart_api.terminateSession(CLIENT_ID)
            logger.info("Logged out session")
        except:
            pass


if __name__ == "__main__":
    collector = AngelOneComplete()
    collector.run()
