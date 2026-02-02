"""
NSE Option Chain Scraper
========================
Fetches Implied Volatility, Open Interest, and other data from NSE India.

Data Source: NSE Official API (Free, Legal)
Schedule: 3:29 PM daily (before market close)

Created: 2026-01-17
"""

import json
import requests
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Setup Logging
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"nse_scraper_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NSEScraper")

# NSE Configuration
NSE_BASE_URL = "https://www.nseindia.com"
OPTION_CHAIN_URL = f"{NSE_BASE_URL}/api/option-chain-indices"

# Headers to bypass NSE anti-bot protection
NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://www.nseindia.com/option-chain',
    'X-Requested-With': 'XMLHttpRequest'
}


class NSEOptionChainScraper:
    """Scraper for NSE option chain data with IV, OI, Volume."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(NSE_HEADERS)
        self.cookies_initialized = False
        
    def _initialize_cookies(self):
        """Initialize session cookies by visiting NSE homepage."""
        if self.cookies_initialized:
            return True
            
        try:
            logger.info("Initializing NSE session cookies...")
            
            # First, visit the main page
            response = self.session.get(NSE_BASE_URL, timeout=15)
            
            if response.status_code != 200:
                logger.warning(f"Main page returned {response.status_code}, trying alternatives...")
                
                # Try option chain page directly
                opt_url = f"{NSE_BASE_URL}/option-chain"
                response = self.session.get(opt_url, timeout=15)
            
            if response.status_code == 200:
                self.cookies_initialized = True
                logger.info(f"✅ NSE session initialized (cookies: {len(self.session.cookies)})")
                time.sleep(2)  # Important delay
                return True
            else:
                logger.error(f"Failed to initialize NSE session: {response.status_code}")
                logger.info("Note: NSE may be blocking automated requests. This is expected outside market hours.")
                return False
                
        except Exception as e:
            logger.error(f"Error initializing NSE session: {e}")
            return False
    
    def fetch_option_chain(self, symbol: str) -> Optional[Dict]:
        """
        Fetch option chain data from NSE.
        
        Args:
            symbol: 'NIFTY' or 'BANKNIFTY'
            
        Returns:
            Dict with option chain data or None if failed
        """
        if not self._initialize_cookies():
            return None
        
        try:
            logger.info(f"Fetching {symbol} option chain from NSE...")
            
            params = {'symbol': symbol}
            response = self.session.get(
                OPTION_CHAIN_URL,
                params=params,
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ {symbol} option chain fetched successfully")
                return data
            else:
                logger.error(f"NSE API returned status {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout fetching {symbol} option chain")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return None
    
    def parse_option_chain(self, raw_data: Dict, symbol: str) -> Dict:
        """
        Parse NSE option chain data into clean format.
        
        Returns:
            {
                'symbol': 'NIFTY',
                'spot_price': 25694.35,
                'timestamp': '2026-01-17 15:29:00',
                'strikes': [
                    {
                        'strike': 25700,
                        'expiry': '20-Jan-2026',
                        'ce': {'ltp': 150, 'iv': 18.25, 'oi': 125400, ...},
                        'pe': {'ltp': 145, 'iv': 19.10, 'oi': 142300, ...}
                    }
                ]
            }
        """
        try:
            # Extract spot price
            records = raw_data.get('records', {})
            underlying_value = records.get('underlyingValue', 0)
            
            # Get option data
            option_data = records.get('data', [])
            
            # Parse each strike
            strikes = []
            for item in option_data:
                strike_price = item.get('strikePrice')
                expiry_date = item.get('expiryDate')
                
                strike_data = {
                    'strike': strike_price,
                    'expiry': expiry_date
                }
                
                # Call option data
                if 'CE' in item:
                    ce = item['CE']
                    strike_data['ce'] = {
                        'ltp': ce.get('lastPrice', 0),
                        'iv': ce.get('impliedVolatility', 0),
                        'oi': ce.get('openInterest', 0),
                        'change_oi': ce.get('changeinOpenInterest', 0),
                        'volume': ce.get('totalTradedVolume', 0),
                        'bid_price': ce.get('bidprice', 0),
                        'ask_price': ce.get('askPrice', 0),
                        'change': ce.get('change', 0),
                        'pchange': ce.get('pChange', 0)
                    }
                
                # Put option data
                if 'PE' in item:
                    pe = item['PE']
                    strike_data['pe'] = {
                        'ltp': pe.get('lastPrice', 0),
                        'iv': pe.get('impliedVolatility', 0),
                        'oi': pe.get('openInterest', 0),
                        'change_oi': pe.get('changeinOpenInterest', 0),
                        'volume': pe.get('totalTradedVolume', 0),
                        'bid_price': pe.get('bidprice', 0),
                        'ask_price': pe.get('askPrice', 0),
                        'change': pe.get('change', 0),
                        'pchange': pe.get('pChange', 0)
                    }
                
                # Only add if has both CE and PE
                if 'ce' in strike_data and 'pe' in strike_data:
                    strikes.append(strike_data)
            
            return {
                'symbol': symbol,
                'spot_price': underlying_value,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'strikes': strikes
            }
            
        except Exception as e:
            logger.error(f"Error parsing option chain: {e}")
            return {
                'symbol': symbol,
                'spot_price': 0,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'strikes': []
            }
    
    def save_option_chain(self, data: Dict):
        """Save parsed option chain data to JSON file."""
        symbol = data['symbol']
        today = datetime.now()
        
        # Create directory structure
        save_dir = BASE_DIR / 'data' / 'option_analytics' / symbol / today.strftime('%Y') / today.strftime('%m_%B') / today.strftime('%d')
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # Save IV/OI snapshot
        filepath = save_dir / 'iv_oi_snapshot.json'
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        
        logger.info(f"✅ Saved {symbol} data: {len(data['strikes'])} strikes to {filepath.relative_to(BASE_DIR)}")
        
        return filepath
    
    def calculate_pcr(self, strikes: List[Dict]) -> float:
        """Calculate Put-Call Ratio from OI data."""
        total_ce_oi = sum(s['ce']['oi'] for s in strikes if 'ce' in s)
        total_pe_oi = sum(s['pe']['oi'] for s in strikes if 'pe' in s)
        
        if total_ce_oi > 0:
            pcr = round(total_pe_oi / total_ce_oi, 2)
        else:
            pcr = 0
        
        return pcr


def main():
    """Main execution."""
    logger.info("="*60)
    logger.info("NSE OPTION CHAIN SCRAPER START")
    logger.info("="*60)
    
    scraper = NSEOptionChainScraper()
    
    symbols = ['NIFTY', 'BANKNIFTY']
    
    for symbol in symbols:
        logger.info(f"\n📊 Processing {symbol}...")
        
        # Fetch from NSE
        raw_data = scraper.fetch_option_chain(symbol)
        
        if not raw_data:
            logger.error(f"❌ Failed to fetch {symbol} data")
            continue
        
        # Parse data
        parsed_data = scraper.parse_option_chain(raw_data, symbol)
        
        if not parsed_data['strikes']:
            logger.error(f"❌ No strikes data for {symbol}")
            continue
        
        # Calculate PCR
        pcr = scraper.calculate_pcr(parsed_data['strikes'])
        parsed_data['pcr'] = pcr
        
        # Save
        filepath = scraper.save_option_chain(parsed_data)
        
        logger.info(f"  Spot: {parsed_data['spot_price']}")
        logger.info(f"  Strikes: {len(parsed_data['strikes'])}")
        logger.info(f"  PCR: {pcr}")
        
        # Polite delay between requests
        time.sleep(2)
    
    logger.info("="*60)
    logger.info("NSE SCRAPER COMPLETED")
    logger.info("="*60)


if __name__ == "__main__":
    main()
