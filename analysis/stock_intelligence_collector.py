"""
Stock Intelligence - Unified Data Collection
=============================================
Collects and saves all stock options intelligence data to organized folders.

Folder Structure:
- stock_intelligence/
  ├── option_chains/{symbol}/{date}/     # Raw option chain data
  ├── daily_movers/{date}/               # Gainers/losers
  ├── oi_spurts/{date}/                  # OI spurt analysis
  ├── predictions/{date}/                # Next-day predictions
  ├── movement_analysis/{date}/          # Why stocks moved
  └── reports/{date}/                    # Daily summary reports

Run: python stock_intelligence_collector.py
Schedule: 3:25 PM daily
"""

import json
import requests
import time
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# Setup
BASE_DIR = Path(__file__).parent
INTELLIGENCE_DIR = BASE_DIR / 'stock_intelligence'
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"stock_intelligence_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("StockIntelligence")

# NSE Configuration
NSE_BASE_URL = "https://www.nseindia.com"
NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://www.nseindia.com',
}

# Top F&O Stocks
FNO_STOCKS = [
    "RELIANCE", "HDFCBANK", "ICICIBANK", "INFY", "TCS", 
    "SBIN", "AXISBANK", "KOTAKBANK", "BAJFINANCE", "TATAMOTORS",
    "TATASTEEL", "WIPRO", "HCLTECH", "SUNPHARMA", "MARUTI",
    "HINDUNILVR", "ITC", "ONGC", "POWERGRID", "NTPC"
]

# Sector mapping
SECTORS = {
    "RELIANCE": "ENERGY", "HDFCBANK": "BANKING", "ICICIBANK": "BANKING",
    "INFY": "IT", "TCS": "IT", "SBIN": "BANKING", "AXISBANK": "BANKING",
    "KOTAKBANK": "BANKING", "BAJFINANCE": "NBFC", "TATAMOTORS": "AUTO",
    "TATASTEEL": "METALS", "WIPRO": "IT", "HCLTECH": "IT",
    "SUNPHARMA": "PHARMA", "MARUTI": "AUTO", "HINDUNILVR": "FMCG",
    "ITC": "FMCG", "ONGC": "ENERGY", "POWERGRID": "ENERGY", "NTPC": "ENERGY"
}


class NSESession:
    """Manages NSE session for API calls."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(NSE_HEADERS)
        self.initialized = False
    
    def initialize(self) -> bool:
        if self.initialized:
            return True
        try:
            logger.info("Initializing NSE session...")
            response = self.session.get(NSE_BASE_URL, timeout=15)
            if response.status_code == 200:
                self.initialized = True
                logger.info("✅ NSE session initialized")
                time.sleep(2)
                return True
            return False
        except Exception as e:
            logger.error(f"Session init error: {e}")
            return False
    
    def get(self, url: str, params: dict = None) -> Optional[Dict]:
        if not self.initialize():
            return None
        try:
            response = self.session.get(url, params=params, timeout=15)
            if response.status_code == 200:
                return response.json()
            logger.warning(f"API returned {response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Request error: {e}")
            return None


class StockIntelligenceCollector:
    """Unified collector for all stock intelligence data."""
    
    def __init__(self):
        self.nse = NSESession()
        self.today = datetime.now().strftime('%Y-%m-%d')
        self._ensure_dirs()
    
    def _ensure_dirs(self):
        """Create directory structure."""
        dirs = ['option_chains', 'daily_movers', 'oi_spurts', 'predictions', 'movement_analysis', 'reports']
        for d in dirs:
            (INTELLIGENCE_DIR / d / self.today).mkdir(parents=True, exist_ok=True)
    
    def _save(self, category: str, filename: str, data: dict) -> Path:
        """Save data to appropriate folder."""
        filepath = INTELLIGENCE_DIR / category / self.today / filename
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        return filepath
    
    # =========================================================================
    # STEP 1: COLLECT OPTION CHAINS
    # =========================================================================
    def collect_option_chains(self, symbols: List[str] = None) -> Dict:
        """Collect option chain data for F&O stocks."""
        logger.info("=" * 60)
        logger.info("STEP 1: Collecting Option Chains")
        logger.info("=" * 60)
        
        symbols = symbols or FNO_STOCKS[:10]  # Start with top 10
        results = {'collected': [], 'failed': [], 'timestamp': self.today}
        
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"[{i}/{len(symbols)}] Fetching {symbol}...")
            
            url = f"{NSE_BASE_URL}/api/option-chain-equities"
            data = self.nse.get(url, {'symbol': symbol})
            
            if data:
                # Parse and save
                records = data.get('records', {})
                parsed = {
                    'symbol': symbol,
                    'spot_price': records.get('underlyingValue', 0),
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'expiry_dates': records.get('expiryDates', []),
                    'strikes': self._parse_strikes(records.get('data', []))
                }
                
                # Save per-symbol
                self._save('option_chains', f'{symbol}.json', parsed)
                results['collected'].append(symbol)
                logger.info(f"  ✅ {symbol}: {len(parsed['strikes'])} strikes")
            else:
                results['failed'].append(symbol)
                logger.warning(f"  ❌ {symbol}: Failed")
            
            time.sleep(2)  # Rate limiting
        
        logger.info(f"Collected: {len(results['collected'])}, Failed: {len(results['failed'])}")
        return results
    
    def _parse_strikes(self, data: List) -> List[Dict]:
        """Parse strike data from option chain."""
        strikes = []
        for item in data:
            strike = {
                'strike': item.get('strikePrice'),
                'expiry': item.get('expiryDate')
            }
            
            if 'CE' in item:
                ce = item['CE']
                strike['ce'] = {
                    'ltp': ce.get('lastPrice', 0),
                    'iv': ce.get('impliedVolatility', 0),
                    'oi': ce.get('openInterest', 0),
                    'change_oi': ce.get('changeinOpenInterest', 0),
                    'volume': ce.get('totalTradedVolume', 0)
                }
            
            if 'PE' in item:
                pe = item['PE']
                strike['pe'] = {
                    'ltp': pe.get('lastPrice', 0),
                    'iv': pe.get('impliedVolatility', 0),
                    'oi': pe.get('openInterest', 0),
                    'change_oi': pe.get('changeinOpenInterest', 0),
                    'volume': pe.get('totalTradedVolume', 0)
                }
            
            if 'ce' in strike or 'pe' in strike:
                strikes.append(strike)
        
        return strikes
    
    # =========================================================================
    # STEP 2: COLLECT GAINERS/LOSERS
    # =========================================================================
    def collect_gainers_losers(self) -> Dict:
        """Collect top gainers and losers."""
        logger.info("=" * 60)
        logger.info("STEP 2: Collecting Gainers/Losers")
        logger.info("=" * 60)
        
        result = {
            'date': self.today,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'gainers': [],
            'losers': [],
            'trending': []
        }
        
        # FNO Gainers
        url = f"{NSE_BASE_URL}/api/live-analysis-fno-gainers"
        data = self.nse.get(url)
        if data and 'data' in data:
            for g in data['data'][:10]:
                result['gainers'].append({
                    'symbol': g.get('symbol', ''),
                    'ltp': g.get('ltp', 0),
                    'change': g.get('change', 0),
                    'change_pct': round(g.get('pChange', 0), 2),
                    'volume': g.get('totalTradedVolume', 0),
                    'sector': SECTORS.get(g.get('symbol', ''), 'OTHER')
                })
        
        time.sleep(1)
        
        # FNO Losers
        url = f"{NSE_BASE_URL}/api/live-analysis-fno-losers"
        data = self.nse.get(url)
        if data and 'data' in data:
            for l in data['data'][:10]:
                result['losers'].append({
                    'symbol': l.get('symbol', ''),
                    'ltp': l.get('ltp', 0),
                    'change': l.get('change', 0),
                    'change_pct': round(l.get('pChange', 0), 2),
                    'volume': l.get('totalTradedVolume', 0),
                    'sector': SECTORS.get(l.get('symbol', ''), 'OTHER')
                })
        
        # Save
        self._save('daily_movers', 'gainers_losers.json', result)
        
        logger.info(f"  Gainers: {len(result['gainers'])}")
        logger.info(f"  Losers: {len(result['losers'])}")
        
        if result['gainers']:
            logger.info(f"  Top Gainer: {result['gainers'][0]['symbol']} +{result['gainers'][0]['change_pct']}%")
        if result['losers']:
            logger.info(f"  Top Loser: {result['losers'][0]['symbol']} {result['losers'][0]['change_pct']}%")
        
        return result
    
    # =========================================================================
    # STEP 3: DETECT OI SPURTS
    # =========================================================================
    def detect_oi_spurts(self) -> Dict:
        """Detect significant OI changes."""
        logger.info("=" * 60)
        logger.info("STEP 3: Detecting OI Spurts")
        logger.info("=" * 60)
        
        result = {
            'date': self.today,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'long_buildups': [],
            'short_buildups': [],
            'long_unwindings': [],
            'short_coverings': [],
            'total_spurts': 0,
            'market_sentiment': 'NEUTRAL'
        }
        
        # Load today's option chains
        chains_dir = INTELLIGENCE_DIR / 'option_chains' / self.today
        
        if not chains_dir.exists():
            logger.warning("No option chain data found")
            self._save('oi_spurts', 'analysis.json', result)
            return result
        
        for chain_file in chains_dir.glob('*.json'):
            with open(chain_file, 'r') as f:
                data = json.load(f)
            
            symbol = data.get('symbol', '')
            spot = data.get('spot_price', 0)
            
            for strike in data.get('strikes', []):
                # Check CE OI change
                if 'ce' in strike:
                    ce = strike['ce']
                    oi = ce.get('oi', 0)
                    change_oi = ce.get('change_oi', 0)
                    
                    if oi > 0 and abs(change_oi) > oi * 0.15:  # >15% change
                        spurt = {
                            'symbol': symbol,
                            'strike': strike['strike'],
                            'expiry': strike['expiry'],
                            'option_type': 'CE',
                            'oi': oi,
                            'oi_change': change_oi,
                            'oi_change_pct': round((change_oi / oi) * 100, 1),
                            'premium': ce.get('ltp', 0)
                        }
                        
                        if change_oi > 0:
                            result['long_buildups'].append(spurt)
                        else:
                            result['long_unwindings'].append(spurt)
                
                # Check PE OI change
                if 'pe' in strike:
                    pe = strike['pe']
                    oi = pe.get('oi', 0)
                    change_oi = pe.get('change_oi', 0)
                    
                    if oi > 0 and abs(change_oi) > oi * 0.15:
                        spurt = {
                            'symbol': symbol,
                            'strike': strike['strike'],
                            'expiry': strike['expiry'],
                            'option_type': 'PE',
                            'oi': oi,
                            'oi_change': change_oi,
                            'oi_change_pct': round((change_oi / oi) * 100, 1),
                            'premium': pe.get('ltp', 0)
                        }
                        
                        if change_oi > 0:
                            result['short_buildups'].append(spurt)
                        else:
                            result['short_coverings'].append(spurt)
        
        # Sort by OI change
        for key in ['long_buildups', 'short_buildups', 'long_unwindings', 'short_coverings']:
            result[key].sort(key=lambda x: abs(x['oi_change_pct']), reverse=True)
            result[key] = result[key][:10]  # Keep top 10
        
        result['total_spurts'] = sum(len(result[k]) for k in ['long_buildups', 'short_buildups', 'long_unwindings', 'short_coverings'])
        
        # Determine sentiment
        bullish = len(result['long_buildups']) + len(result['short_coverings'])
        bearish = len(result['short_buildups']) + len(result['long_unwindings'])
        
        if bullish > bearish + 2:
            result['market_sentiment'] = 'BULLISH'
        elif bearish > bullish + 2:
            result['market_sentiment'] = 'BEARISH'
        
        # Save
        self._save('oi_spurts', 'analysis.json', result)
        
        logger.info(f"  Total Spurts: {result['total_spurts']}")
        logger.info(f"  Long Buildups: {len(result['long_buildups'])}")
        logger.info(f"  Short Buildups: {len(result['short_buildups'])}")
        logger.info(f"  Market Sentiment: {result['market_sentiment']}")
        
        return result
    
    # =========================================================================
    # STEP 4: GENERATE PREDICTIONS
    # =========================================================================
    def generate_predictions(self) -> Dict:
        """Generate next-day predictions."""
        logger.info("=" * 60)
        logger.info("STEP 4: Generating Predictions")
        logger.info("=" * 60)
        
        result = {
            'date': self.today,
            'for_date': (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d'),
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'predictions': [],
            'top_bullish': [],
            'top_bearish': []
        }
        
        # Load OI spurts and gainers/losers
        oi_file = INTELLIGENCE_DIR / 'oi_spurts' / self.today / 'analysis.json'
        gl_file = INTELLIGENCE_DIR / 'daily_movers' / self.today / 'gainers_losers.json'
        
        oi_data = {}
        gl_data = {}
        
        if oi_file.exists():
            with open(oi_file, 'r') as f:
                oi_data = json.load(f)
        
        if gl_file.exists():
            with open(gl_file, 'r') as f:
                gl_data = json.load(f)
        
        # Build predictions
        candidates = set()
        
        # Add from OI spurts
        for category in ['long_buildups', 'short_buildups']:
            for spurt in oi_data.get(category, [])[:5]:
                candidates.add(spurt['symbol'])
        
        # Add from gainers/losers
        for g in gl_data.get('gainers', [])[:5]:
            candidates.add(g['symbol'])
        for l in gl_data.get('losers', [])[:5]:
            candidates.add(l['symbol'])
        
        for symbol in candidates:
            # Analyze signals
            bullish_score = 0
            bearish_score = 0
            reasons = []
            
            # OI signals
            for spurt in oi_data.get('long_buildups', []):
                if spurt['symbol'] == symbol:
                    bullish_score += 0.3
                    reasons.append(f"CE OI buildup at {spurt['strike']}")
            
            for spurt in oi_data.get('short_buildups', []):
                if spurt['symbol'] == symbol:
                    bearish_score += 0.3
                    reasons.append(f"PE OI buildup at {spurt['strike']}")
            
            # Gainer/loser signals
            for g in gl_data.get('gainers', []):
                if g['symbol'] == symbol:
                    if g['change_pct'] > 3:
                        bullish_score += 0.3
                        reasons.append(f"Today's gainer +{g['change_pct']}%")
            
            for l in gl_data.get('losers', []):
                if l['symbol'] == symbol:
                    if l['change_pct'] < -3:
                        bearish_score += 0.3
                        reasons.append(f"Today's loser {l['change_pct']}%")
            
            # Determine direction
            if bullish_score > bearish_score + 0.1:
                direction = 'BULLISH'
                confidence = min(0.85, 0.5 + bullish_score)
            elif bearish_score > bullish_score + 0.1:
                direction = 'BEARISH'
                confidence = min(0.85, 0.5 + bearish_score)
            else:
                direction = 'RANGE_BOUND'
                confidence = 0.4
            
            if confidence >= 0.4:
                result['predictions'].append({
                    'symbol': symbol,
                    'direction': direction,
                    'confidence': round(confidence, 2),
                    'reasons': reasons[:3],
                    'target_pct': round(1.5 + confidence, 1),
                    'stop_loss_pct': round(1 + (1 - confidence), 1),
                    'strategy': f"Buy {'Call' if direction == 'BULLISH' else 'Put' if direction == 'BEARISH' else 'Straddle'}"
                })
        
        # Sort by confidence
        result['predictions'].sort(key=lambda x: x['confidence'], reverse=True)
        result['top_bullish'] = [p for p in result['predictions'] if p['direction'] == 'BULLISH'][:3]
        result['top_bearish'] = [p for p in result['predictions'] if p['direction'] == 'BEARISH'][:3]
        
        # Save
        self._save('predictions', 'predictions.json', result)
        
        logger.info(f"  Total Predictions: {len(result['predictions'])}")
        logger.info(f"  Top Bullish: {[p['symbol'] for p in result['top_bullish']]}")
        logger.info(f"  Top Bearish: {[p['symbol'] for p in result['top_bearish']]}")
        
        return result
    
    # =========================================================================
    # STEP 5: GENERATE REPORT
    # =========================================================================
    def generate_report(self) -> Dict:
        """Generate daily summary report."""
        logger.info("=" * 60)
        logger.info("STEP 5: Generating Daily Report")
        logger.info("=" * 60)
        
        report = {
            'date': self.today,
            'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'summary': {}
        }
        
        # Load all data
        for category in ['option_chains', 'daily_movers', 'oi_spurts', 'predictions']:
            cat_dir = INTELLIGENCE_DIR / category / self.today
            if cat_dir.exists():
                files = list(cat_dir.glob('*.json'))
                report['summary'][category] = f"{len(files)} files"
        
        # Save report
        self._save('reports', 'daily_summary.json', report)
        
        logger.info("  Report generated successfully")
        
        return report
    
    # =========================================================================
    # RUN ALL
    # =========================================================================
    def run_all(self) -> Dict:
        """Run complete data collection pipeline."""
        logger.info("=" * 60)
        logger.info("🚀 STOCK INTELLIGENCE COLLECTOR")
        logger.info(f"📅 Date: {self.today}")
        logger.info("=" * 60)
        
        results = {}
        
        try:
            # Step 1: Option Chains
            results['option_chains'] = self.collect_option_chains()
            
            # Step 2: Gainers/Losers
            results['gainers_losers'] = self.collect_gainers_losers()
            
            # Step 3: OI Spurts
            results['oi_spurts'] = self.detect_oi_spurts()
            
            # Step 4: Predictions
            results['predictions'] = self.generate_predictions()
            
            # Step 5: Report
            results['report'] = self.generate_report()
            
            logger.info("=" * 60)
            logger.info("✅ ALL STEPS COMPLETED SUCCESSFULLY")
            logger.info(f"📁 Data saved to: stock_intelligence/{self.today}/")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"Error during collection: {e}")
            results['error'] = str(e)
        
        return results


def main():
    """Main execution."""
    collector = StockIntelligenceCollector()
    results = collector.run_all()
    
    print(f"\n📊 Collection Summary:")
    print(f"  • Option chains: {len(results.get('option_chains', {}).get('collected', []))} stocks")
    print(f"  • Gainers: {len(results.get('gainers_losers', {}).get('gainers', []))}")
    print(f"  • Losers: {len(results.get('gainers_losers', {}).get('losers', []))}")
    print(f"  • OI Spurts: {results.get('oi_spurts', {}).get('total_spurts', 0)}")
    print(f"  • Predictions: {len(results.get('predictions', {}).get('predictions', []))}")
    print(f"\n📁 Data saved to: stock_intelligence/{collector.today}/")


if __name__ == "__main__":
    main()
