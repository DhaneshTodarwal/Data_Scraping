"""
Intraday 1-Minute Data Collector
=================================
Collects 1-minute OHLCV data for F&O stocks and their options.

Features:
- 30 F&O Stocks + NIFTY/BANKNIFTY
- ATM ± 5 Option Strikes
- Gzip compression (~80% smaller)
- Organized folder structure
- Uses AngelOne API

Storage: ~4-5 MB/day (compressed)

Run during market hours: 9:15 AM - 3:30 PM
"""

import os
import csv
import gzip
import json
import time
import logging
import pyotp
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from SmartApi import SmartConnect

# Setup
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'stock_intelligence' / '1min_data'
CACHE_DIR = BASE_DIR / 'scripts' / 'cache'
LOG_DIR = BASE_DIR / 'logs'

LOG_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"intraday_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("IntradayCollector")

# Load environment
def load_env():
    for env_file in ['.env', '.env.angelone']:
        env_path = BASE_DIR / env_file
        if env_path.exists():
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        os.environ.setdefault(key.strip(), value.strip())

load_env()

# Credentials
API_KEY = os.getenv('ANGEL_API_KEY')
CLIENT_ID = os.getenv('ANGEL_CLIENT_ID')
PIN = os.getenv('ANGEL_PIN')
TOTP_SECRET = os.getenv('ANGEL_TOTP_SECRET')

INSTRUMENT_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

# 30 Top F&O Stocks
FNO_STOCKS = [
    # Indices (special handling)
    ("NIFTY", "99926000", "NSE", 50),
    ("BANKNIFTY", "99926009", "NSE", 100),
    
    # Banking (6)
    ("HDFCBANK", None, "NSE", 50),
    ("ICICIBANK", None, "NSE", 50),
    ("SBIN", None, "NSE", 25),
    ("AXISBANK", None, "NSE", 50),
    ("KOTAKBANK", None, "NSE", 50),
    ("BAJFINANCE", None, "NSE", 100),
    
    # IT (4)
    ("TCS", None, "NSE", 50),
    ("INFY", None, "NSE", 50),
    ("WIPRO", None, "NSE", 10),
    ("HCLTECH", None, "NSE", 50),
    
    # Energy (4)
    ("RELIANCE", None, "NSE", 50),
    ("ONGC", None, "NSE", 10),
    ("NTPC", None, "NSE", 10),
    ("POWERGRID", None, "NSE", 10),
    
    # Auto (3)
    ("TATAMOTORS", None, "NSE", 25),
    ("MARUTI", None, "NSE", 100),
    ("M&M", None, "NSE", 50),
    
    # Metals (2)
    ("TATASTEEL", None, "NSE", 25),
    ("HINDALCO", None, "NSE", 25),
    
    # Pharma (2)
    ("SUNPHARMA", None, "NSE", 25),
    ("CIPLA", None, "NSE", 25),
    
    # FMCG (3)
    ("HINDUNILVR", None, "NSE", 50),
    ("ITC", None, "NSE", 10),
    ("TITAN", None, "NSE", 50),
    
    # Others (6)
    ("ADANIENT", None, "NSE", 50),
    ("LT", None, "NSE", 50),
    ("ASIANPAINT", None, "NSE", 50),
    ("BHARTIARTL", None, "NSE", 50),
    ("COALINDIA", None, "NSE", 10),
    ("ULTRACEMCO", None, "NSE", 50),
]

STRIKES_RANGE = 5  # ATM ± 5 strikes


class IntradayCollector:
    """Collects 1-minute data for F&O stocks and options."""
    
    def __init__(self):
        self._validate()
        self.smart_api = SmartConnect(api_key=API_KEY)
        self.totp = pyotp.TOTP(TOTP_SECRET)
        self.logged_in = False
        self.instruments = []
        self.today = datetime.now().strftime('%Y-%m-%d')
        
    def _validate(self):
        if not all([API_KEY, CLIENT_ID, PIN, TOTP_SECRET]):
            raise ValueError("Missing AngelOne credentials in .env file")
    
    def login(self) -> bool:
        """Login to AngelOne."""
        try:
            totp_code = self.totp.now()
            logger.info(f"Logging in as {CLIENT_ID}...")
            
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
            logger.error(f"Login error: {e}")
            return False
    
    def logout(self):
        """Logout from AngelOne."""
        try:
            self.smart_api.terminateSession(CLIENT_ID)
            logger.info("Logged out")
        except:
            pass
    
    def load_instruments(self) -> bool:
        """Load instrument master."""
        cache_file = CACHE_DIR / f"instruments_{datetime.now().strftime('%Y%m%d')}.json"
        
        if cache_file.exists():
            logger.info("Loading instruments from cache...")
            with open(cache_file, 'r') as f:
                self.instruments = json.load(f)
            return True
        
        logger.info("Downloading instrument master...")
        import requests
        try:
            resp = requests.get(INSTRUMENT_URL, timeout=60)
            resp.raise_for_status()
            self.instruments = resp.json()
            
            cache_file.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_file, 'w') as f:
                json.dump(self.instruments, f)
            
            logger.info(f"✅ Loaded {len(self.instruments)} instruments")
            return True
        except Exception as e:
            logger.error(f"Failed to load instruments: {e}")
            return False
    
    def find_stock_token(self, symbol: str) -> Optional[str]:
        """Find token for a stock symbol."""
        for inst in self.instruments:
            if inst.get('symbol') == f"{symbol}-EQ" and inst.get('exch_seg') == 'NSE':
                return inst.get('token')
            if inst.get('symbol') == symbol and inst.get('exch_seg') == 'NSE':
                return inst.get('token')
        return None
    
    def get_ltp(self, exchange: str, symbol: str, token: str) -> Optional[float]:
        """Get current LTP."""
        if not self.logged_in:
            return None
        
        try:
            data = self.smart_api.ltpData(exchange, symbol, token)
            if data and data.get('status'):
                return float(data['data']['ltp'])
        except Exception as e:
            logger.debug(f"LTP error for {symbol}: {e}")
        return None
    
    def get_atm_strike(self, ltp: float, step: int) -> int:
        """Calculate ATM strike."""
        return int(round(ltp / step) * step)
    
    def get_option_strikes(self, symbol: str, atm: int, step: int) -> List[Dict]:
        """Get option instruments for ATM ± N strikes."""
        options = []
        today = datetime.now().date()
        
        # Find nearest expiry
        expiries = set()
        for inst in self.instruments:
            if inst.get('name') == symbol and inst.get('exch_seg') == 'NFO':
                exp_str = inst.get('expiry', '')
                if exp_str:
                    try:
                        exp_date = datetime.strptime(exp_str, '%d%b%Y').date()
                        if exp_date >= today:
                            expiries.add(exp_date)
                    except:
                        pass
        
        if not expiries:
            return []
        
        target_expiry = sorted(expiries)[0]
        target_exp_str = target_expiry.strftime('%d%b%Y').upper()
        
        # Calculate strike range
        min_strike = atm - (STRIKES_RANGE * step)
        max_strike = atm + (STRIKES_RANGE * step)
        
        for inst in self.instruments:
            if inst.get('name') == symbol and inst.get('exch_seg') == 'NFO':
                if inst.get('expiry') != target_exp_str:
                    continue
                
                strike = float(inst.get('strike', 0)) / 100
                if min_strike <= strike <= max_strike:
                    tsym = inst.get('symbol', '')
                    options.append({
                        'symbol': tsym,
                        'token': inst.get('token'),
                        'strike': int(strike),
                        'type': 'CE' if 'CE' in tsym else 'PE',
                        'expiry': target_exp_str
                    })
        
        return sorted(options, key=lambda x: (x['strike'], x['type']))
    
    def get_historical_candles(self, exchange: str, token: str) -> List:
        """Get today's 1-minute candles."""
        if not self.logged_in:
            return []
        
        now = datetime.now()
        from_date = now.replace(hour=9, minute=15, second=0).strftime('%Y-%m-%d %H:%M')
        to_date = now.strftime('%Y-%m-%d %H:%M')
        
        try:
            data = self.smart_api.getCandleData({
                'exchange': exchange,
                'symboltoken': str(token),
                'interval': 'ONE_MINUTE',
                'fromdate': from_date,
                'todate': to_date
            })
            
            if data and data.get('status'):
                return data.get('data', [])
        except Exception as e:
            logger.debug(f"Candle fetch error: {e}")
        
        return []
    
    def save_csv_gzip(self, candles: List, filepath: Path):
        """Save candles to gzip-compressed CSV."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        with gzip.open(filepath, 'wt', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            writer.writerows(candles)
    
    def collect_stocks(self) -> Dict:
        """Collect 1-min data for all stocks."""
        logger.info("=" * 60)
        logger.info("📈 COLLECTING STOCK DATA")
        logger.info("=" * 60)
        
        results = {'collected': [], 'failed': []}
        today_dir = DATA_DIR / self.today / 'stocks'
        today_dir.mkdir(parents=True, exist_ok=True)
        
        for stock_info in FNO_STOCKS:
            symbol, preset_token, exchange, step = stock_info
            
            # Get token
            if preset_token:
                token = preset_token
            else:
                token = self.find_stock_token(symbol)
            
            if not token:
                logger.warning(f"  ❌ {symbol}: Token not found")
                results['failed'].append(symbol)
                continue
            
            # Get candles
            candles = self.get_historical_candles(exchange, token)
            
            if candles:
                filepath = today_dir / f"{symbol}.csv.gz"
                self.save_csv_gzip(candles, filepath)
                logger.info(f"  ✅ {symbol}: {len(candles)} candles")
                results['collected'].append(symbol)
            else:
                logger.warning(f"  ⚠️ {symbol}: No data")
                results['failed'].append(symbol)
            
            time.sleep(0.4)  # Rate limit
        
        logger.info(f"Stocks: {len(results['collected'])} collected, {len(results['failed'])} failed")
        return results
    
    def collect_options(self) -> Dict:
        """Collect 1-min data for option strikes."""
        logger.info("=" * 60)
        logger.info("📊 COLLECTING OPTIONS DATA")
        logger.info("=" * 60)
        
        results = {'total_strikes': 0, 'symbols_processed': 0}
        today_dir = DATA_DIR / self.today / 'options'
        
        # Only process stocks that support options (not all stocks)
        option_symbols = [
            ("NIFTY", "99926000", "NSE", 50),
            ("BANKNIFTY", "99926009", "NSE", 100),
            ("RELIANCE", None, "NSE", 50),
            ("HDFCBANK", None, "NSE", 50),
            ("TCS", None, "NSE", 50),
            ("INFY", None, "NSE", 50),
            ("ICICIBANK", None, "NSE", 50),
            ("SBIN", None, "NSE", 25),
            ("TATAMOTORS", None, "NSE", 25),
            ("BAJFINANCE", None, "NSE", 100),
        ]
        
        for symbol, preset_token, exchange, step in option_symbols:
            logger.info(f"  Processing {symbol}...")
            
            # Get LTP
            if preset_token:
                token = preset_token
            else:
                token = self.find_stock_token(symbol)
            
            if not token:
                continue
            
            ltp = self.get_ltp(exchange, symbol, token)
            if not ltp:
                logger.warning(f"    ⚠️ Could not get LTP for {symbol}")
                continue
            
            atm = self.get_atm_strike(ltp, step)
            logger.info(f"    LTP: {ltp} | ATM: {atm}")
            
            # Get option strikes
            strikes = self.get_option_strikes(symbol, atm, step)
            logger.info(f"    Found {len(strikes)} option strikes")
            
            count = 0
            for opt in strikes:
                candles = self.get_historical_candles('NFO', opt['token'])
                
                if candles:
                    # Save: options/{symbol}/{strike}{type}.csv.gz
                    sym_dir = today_dir / symbol
                    filepath = sym_dir / f"{opt['strike']}{opt['type']}.csv.gz"
                    self.save_csv_gzip(candles, filepath)
                    count += 1
                
                time.sleep(0.35)  # Rate limit
            
            logger.info(f"    ✅ Saved {count} strikes")
            results['total_strikes'] += count
            results['symbols_processed'] += 1
        
        logger.info(f"Options: {results['total_strikes']} strikes from {results['symbols_processed']} symbols")
        return results
    
    def get_storage_stats(self) -> Dict:
        """Calculate storage used."""
        today_dir = DATA_DIR / self.today
        
        total_size = 0
        file_count = 0
        
        if today_dir.exists():
            for f in today_dir.rglob('*.gz'):
                total_size += f.stat().st_size
                file_count += 1
        
        return {
            'files': file_count,
            'size_bytes': total_size,
            'size_mb': round(total_size / (1024 * 1024), 2)
        }
    
    def run(self) -> Dict:
        """Run full collection."""
        logger.info("=" * 60)
        logger.info("🚀 INTRADAY 1-MIN DATA COLLECTOR")
        logger.info(f"📅 Date: {self.today}")
        logger.info("=" * 60)
        
        results = {}
        
        if not self.login():
            return {'error': 'Login failed'}
        
        if not self.load_instruments():
            return {'error': 'Instruments load failed'}
        
        # Collect stocks
        results['stocks'] = self.collect_stocks()
        
        # Collect options
        results['options'] = self.collect_options()
        
        # Get storage stats
        results['storage'] = self.get_storage_stats()
        
        self.logout()
        
        logger.info("=" * 60)
        logger.info("✅ COLLECTION COMPLETE")
        logger.info(f"📁 Data: stock_intelligence/1min_data/{self.today}/")
        logger.info(f"💾 Storage: {results['storage']['size_mb']} MB ({results['storage']['files']} files)")
        logger.info("=" * 60)
        
        return results


def main():
    """Main execution."""
    collector = IntradayCollector()
    results = collector.run()
    
    if 'error' not in results:
        print(f"\n📊 Collection Summary:")
        print(f"  • Stocks: {len(results.get('stocks', {}).get('collected', []))}")
        print(f"  • Option Strikes: {results.get('options', {}).get('total_strikes', 0)}")
        print(f"  • Storage Used: {results.get('storage', {}).get('size_mb', 0)} MB")
        print(f"\n📁 Data saved to: stock_intelligence/1min_data/{datetime.now().strftime('%Y-%m-%d')}/")


if __name__ == "__main__":
    main()
