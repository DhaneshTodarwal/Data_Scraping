"""
Stock Options Scraper for F&O Stocks
=====================================
Fetches option chain data for F&O stocks from NSE India.

Features:
- Collects IV, OI, Volume, Change in OI for all strikes
- Supports top 50 F&O stocks by liquidity
- Stores historical data for analysis
- Identifies OI patterns (buildup/unwinding)

Schedule: 3:25 PM daily (before market close)
"""

import json
import requests
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# Setup
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"stock_options_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("StockOptionsScraper")

# NSE Configuration
NSE_BASE_URL = "https://www.nseindia.com"
OPTION_CHAIN_URL = f"{NSE_BASE_URL}/api/option-chain-equities"

NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://www.nseindia.com/option-chain',
    'X-Requested-With': 'XMLHttpRequest'
}

# Top F&O stocks by liquidity (curated list)
# These stocks have high options volume and are ideal for OI analysis
FNO_STOCKS = [
    # Banking & Financial
    "HDFCBANK", "ICICIBANK", "SBIN", "AXISBANK", "KOTAKBANK",
    "BAJFINANCE", "BAJAJFINSV", "INDUSINDBK", "BANKBARODA", "PNB",
    
    # IT
    "TCS", "INFY", "WIPRO", "HCLTECH", "TECHM", "LTI",
    
    # Reliance & Conglomerates
    "RELIANCE", "TATASTEEL", "TATAPOWER", "TATAMOTORS", "ADANIENT",
    "ADANIPORTS", "HINDALCO", "JINDALSTEL", "JSWSTEEL",
    
    # Pharma
    "SUNPHARMA", "DRREDDY", "CIPLA", "DIVISLAB", "APOLLOHOSP",
    
    # Auto
    "MARUTI", "M&M", "BAJAJ-AUTO", "HEROMOTOCO", "EICHERMOT",
    
    # FMCG & Consumer
    "HINDUNILVR", "ITC", "NESTLEIND", "BRITANNIA", "TITAN",
    
    # Energy & Infrastructure
    "ONGC", "POWERGRID", "NTPC", "COALINDIA", "BPCL",
    
    # Others
    "ASIANPAINT", "ULTRACEMCO", "GRASIM", "SBILIFE", "HDFCLIFE"
]

# Lot sizes for F&O stocks (approximate, update as needed)
LOT_SIZES = {
    "RELIANCE": 250, "HDFCBANK": 550, "ICICIBANK": 700, "INFY": 300,
    "TCS": 125, "SBIN": 1500, "AXISBANK": 600, "KOTAKBANK": 400,
    "BAJFINANCE": 125, "TATAMOTORS": 1425, "TATASTEEL": 550,
    # Default for others
    "DEFAULT": 500
}


@dataclass
class OptionData:
    """Option strike data"""
    strike: int
    expiry: str
    ltp: float
    iv: float
    oi: int
    change_oi: int
    volume: int
    bid: float
    ask: float
    change_pct: float


@dataclass
class StockOptionChain:
    """Complete option chain for a stock"""
    symbol: str
    spot_price: float
    timestamp: str
    expiry_dates: List[str]
    calls: List[Dict]
    puts: List[Dict]
    pcr: float
    total_call_oi: int
    total_put_oi: int
    max_call_oi_strike: int
    max_put_oi_strike: int


class StockOptionsScraper:
    """Scraper for F&O stock option chains."""
    
    def __init__(self, stocks: List[str] = None):
        self.session = requests.Session()
        self.session.headers.update(NSE_HEADERS)
        self.cookies_initialized = False
        self.stocks = stocks or FNO_STOCKS
        
    def _initialize_cookies(self) -> bool:
        """Initialize session cookies."""
        if self.cookies_initialized:
            return True
            
        try:
            logger.info("Initializing NSE session...")
            response = self.session.get(NSE_BASE_URL, timeout=15)
            
            if response.status_code == 200:
                self.cookies_initialized = True
                logger.info(f"✅ Session initialized (cookies: {len(self.session.cookies)})")
                time.sleep(2)
                return True
            else:
                logger.error(f"Failed to initialize: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error initializing: {e}")
            return False
    
    def fetch_option_chain(self, symbol: str) -> Optional[Dict]:
        """Fetch option chain for a stock."""
        if not self._initialize_cookies():
            return None
            
        try:
            logger.info(f"Fetching {symbol} option chain...")
            
            response = self.session.get(
                OPTION_CHAIN_URL,
                params={'symbol': symbol},
                timeout=15
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"✅ {symbol} fetched successfully")
                return data
            else:
                logger.warning(f"{symbol} returned {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Error fetching {symbol}: {e}")
            return None
    
    def parse_option_chain(self, raw_data: Dict, symbol: str) -> Optional[StockOptionChain]:
        """Parse raw NSE data into structured format."""
        try:
            records = raw_data.get('records', {})
            underlying = records.get('underlyingValue', 0)
            expiry_dates = records.get('expiryDates', [])
            data = records.get('data', [])
            
            calls = []
            puts = []
            total_call_oi = 0
            total_put_oi = 0
            max_call_oi = 0
            max_put_oi = 0
            max_call_strike = 0
            max_put_strike = 0
            
            for item in data:
                strike = item.get('strikePrice')
                expiry = item.get('expiryDate')
                
                # Parse Call data
                if 'CE' in item:
                    ce = item['CE']
                    call_data = {
                        'strike': strike,
                        'expiry': expiry,
                        'ltp': ce.get('lastPrice', 0),
                        'iv': ce.get('impliedVolatility', 0),
                        'oi': ce.get('openInterest', 0),
                        'change_oi': ce.get('changeinOpenInterest', 0),
                        'volume': ce.get('totalTradedVolume', 0),
                        'bid': ce.get('bidprice', 0),
                        'ask': ce.get('askPrice', 0),
                        'change_pct': ce.get('pChange', 0)
                    }
                    calls.append(call_data)
                    total_call_oi += call_data['oi']
                    
                    if call_data['oi'] > max_call_oi:
                        max_call_oi = call_data['oi']
                        max_call_strike = strike
                
                # Parse Put data
                if 'PE' in item:
                    pe = item['PE']
                    put_data = {
                        'strike': strike,
                        'expiry': expiry,
                        'ltp': pe.get('lastPrice', 0),
                        'iv': pe.get('impliedVolatility', 0),
                        'oi': pe.get('openInterest', 0),
                        'change_oi': pe.get('changeinOpenInterest', 0),
                        'volume': pe.get('totalTradedVolume', 0),
                        'bid': pe.get('bidprice', 0),
                        'ask': pe.get('askPrice', 0),
                        'change_pct': pe.get('pChange', 0)
                    }
                    puts.append(put_data)
                    total_put_oi += put_data['oi']
                    
                    if put_data['oi'] > max_put_oi:
                        max_put_oi = put_data['oi']
                        max_put_strike = strike
            
            # Calculate PCR
            pcr = round(total_put_oi / total_call_oi, 2) if total_call_oi > 0 else 0
            
            return StockOptionChain(
                symbol=symbol,
                spot_price=underlying,
                timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                expiry_dates=expiry_dates,
                calls=calls,
                puts=puts,
                pcr=pcr,
                total_call_oi=total_call_oi,
                total_put_oi=total_put_oi,
                max_call_oi_strike=max_call_strike,
                max_put_oi_strike=max_put_strike
            )
            
        except Exception as e:
            logger.error(f"Error parsing {symbol}: {e}")
            return None
    
    def save_option_chain(self, data: StockOptionChain) -> Path:
        """Save option chain data to JSON file."""
        today = datetime.now()
        
        # Create directory structure
        save_dir = BASE_DIR / 'data' / 'stock_options' / data.symbol / today.strftime('%Y-%m') / today.strftime('%d')
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # Save full option chain
        filepath = save_dir / f"option_chain_{today.strftime('%H-%M')}.json"
        
        with open(filepath, 'w') as f:
            json.dump(asdict(data), f, indent=2)
        
        logger.info(f"💾 Saved {data.symbol} to {filepath.relative_to(BASE_DIR)}")
        return filepath
    
    def identify_oi_patterns(self, data: StockOptionChain) -> Dict:
        """Identify significant OI patterns."""
        patterns = {
            'symbol': data.symbol,
            'spot': data.spot_price,
            'timestamp': data.timestamp,
            'call_buildups': [],
            'put_buildups': [],
            'call_unwindings': [],
            'put_unwindings': [],
            'summary': {}
        }
        
        # Find significant call OI changes
        for call in data.calls:
            oi_change = call.get('change_oi', 0)
            oi = call.get('oi', 0)
            
            if oi > 0 and abs(oi_change) > oi * 0.15:  # >15% change
                if oi_change > 0:
                    patterns['call_buildups'].append({
                        'strike': call['strike'],
                        'expiry': call['expiry'],
                        'oi_change': oi_change,
                        'oi_change_pct': round(oi_change / oi * 100, 1),
                        'ltp': call['ltp']
                    })
                else:
                    patterns['call_unwindings'].append({
                        'strike': call['strike'],
                        'expiry': call['expiry'],
                        'oi_change': oi_change,
                        'oi_change_pct': round(oi_change / oi * 100, 1),
                        'ltp': call['ltp']
                    })
        
        # Find significant put OI changes
        for put in data.puts:
            oi_change = put.get('change_oi', 0)
            oi = put.get('oi', 0)
            
            if oi > 0 and abs(oi_change) > oi * 0.15:
                if oi_change > 0:
                    patterns['put_buildups'].append({
                        'strike': put['strike'],
                        'expiry': put['expiry'],
                        'oi_change': oi_change,
                        'oi_change_pct': round(oi_change / oi * 100, 1),
                        'ltp': put['ltp']
                    })
                else:
                    patterns['put_unwindings'].append({
                        'strike': put['strike'],
                        'expiry': put['expiry'],
                        'oi_change': oi_change,
                        'oi_change_pct': round(oi_change / oi * 100, 1),
                        'ltp': put['ltp']
                    })
        
        # Summary
        net_call_buildup = len(patterns['call_buildups']) - len(patterns['call_unwindings'])
        net_put_buildup = len(patterns['put_buildups']) - len(patterns['put_unwindings'])
        
        if net_put_buildup > net_call_buildup:
            patterns['summary']['bias'] = 'BEARISH'
            patterns['summary']['reason'] = 'More put buildups than call buildups'
        elif net_call_buildup > net_put_buildup:
            patterns['summary']['bias'] = 'BULLISH'
            patterns['summary']['reason'] = 'More call buildups than put buildups (potential resistance)'
        else:
            patterns['summary']['bias'] = 'NEUTRAL'
            patterns['summary']['reason'] = 'Balanced OI activity'
        
        patterns['summary']['pcr'] = data.pcr
        patterns['summary']['max_call_oi_strike'] = data.max_call_oi_strike
        patterns['summary']['max_put_oi_strike'] = data.max_put_oi_strike
        
        return patterns
    
    def collect_all(self, delay: float = 3) -> List[Dict]:
        """Collect option chains for all configured stocks."""
        results = []
        successful = 0
        failed = 0
        
        logger.info(f"Starting collection for {len(self.stocks)} stocks...")
        
        for i, symbol in enumerate(self.stocks, 1):
            logger.info(f"[{i}/{len(self.stocks)}] Processing {symbol}...")
            
            try:
                raw_data = self.fetch_option_chain(symbol)
                
                if raw_data:
                    parsed = self.parse_option_chain(raw_data, symbol)
                    
                    if parsed:
                        self.save_option_chain(parsed)
                        patterns = self.identify_oi_patterns(parsed)
                        results.append(patterns)
                        successful += 1
                    else:
                        failed += 1
                else:
                    failed += 1
                
                # Delay between requests
                time.sleep(delay)
                
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
                failed += 1
        
        logger.info(f"\n📊 Collection Complete: {successful} success, {failed} failed")
        return results
    
    def get_top_oi_spurts(self, results: List[Dict], top_n: int = 10) -> Dict:
        """Get top OI spurts across all stocks."""
        all_spurts = []
        
        for result in results:
            symbol = result['symbol']
            
            # Collect all buildups
            for buildup in result.get('call_buildups', []):
                all_spurts.append({
                    'symbol': symbol,
                    'type': 'CALL_BUILDUP',
                    'strike': buildup['strike'],
                    'oi_change_pct': buildup['oi_change_pct'],
                    'interpretation': 'Resistance / Bearish if price near strike'
                })
            
            for buildup in result.get('put_buildups', []):
                all_spurts.append({
                    'symbol': symbol,
                    'type': 'PUT_BUILDUP',
                    'strike': buildup['strike'],
                    'oi_change_pct': buildup['oi_change_pct'],
                    'interpretation': 'Support / Bullish bias'
                })
        
        # Sort by OI change percentage
        all_spurts.sort(key=lambda x: abs(x['oi_change_pct']), reverse=True)
        
        return {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'top_spurts': all_spurts[:top_n],
            'total_spurts_detected': len(all_spurts)
        }


def main():
    """Main execution."""
    logger.info("=" * 60)
    logger.info("STOCK OPTIONS SCRAPER START")
    logger.info("=" * 60)
    
    # For initial testing, use a subset of stocks
    test_stocks = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "SBIN"]
    
    scraper = StockOptionsScraper(stocks=test_stocks)
    
    # Collect data
    results = scraper.collect_all()
    
    # Get top OI spurts
    if results:
        spurts = scraper.get_top_oi_spurts(results)
        
        # Save spurts summary
        today = datetime.now()
        spurts_dir = BASE_DIR / 'data' / 'daily_analysis' / today.strftime('%Y-%m-%d')
        spurts_dir.mkdir(parents=True, exist_ok=True)
        
        with open(spurts_dir / 'oi_spurts.json', 'w') as f:
            json.dump(spurts, f, indent=2)
        
        logger.info(f"\n🔥 Top OI Spurts Today:")
        for spurt in spurts['top_spurts'][:5]:
            logger.info(f"  {spurt['symbol']} {spurt['type']} @ {spurt['strike']} ({spurt['oi_change_pct']}%)")
    
    logger.info("=" * 60)
    logger.info("SCRAPER COMPLETED")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
