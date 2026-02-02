"""
Gainers & Losers Tracker
=========================
Tracks and stores daily top movers in F&O segment.

Features:
- Stock-level top gainers/losers
- Option-level top movers (by premium % change)
- Historical tracking for pattern detection
- Identifies stocks appearing multiple days (trending)

Data Source: NSE India
Schedule: 3:30 PM daily (at market close)
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
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"gainers_losers_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("GainersLosers")

# NSE URLs
NSE_BASE_URL = "https://www.nseindia.com"
FNO_GAINERS_URL = f"{NSE_BASE_URL}/api/live-analysis-fno-gainers"
FNO_LOSERS_URL = f"{NSE_BASE_URL}/api/live-analysis-fno-losers"
EQUITY_GAINERS_URL = f"{NSE_BASE_URL}/api/live-analysis-variations?index=gainers"
EQUITY_LOSERS_URL = f"{NSE_BASE_URL}/api/live-analysis-variations?index=loosers"  # NSE spelling

NSE_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Referer': 'https://www.nseindia.com',
}


@dataclass
class StockMover:
    """Stock that moved significantly"""
    symbol: str
    ltp: float
    change: float
    change_pct: float
    volume: int
    previous_close: float


@dataclass
class OptionMover:
    """Option contract that moved significantly"""
    symbol: str
    strike: int
    option_type: str  # CE or PE
    expiry: str
    ltp: float
    change: float
    change_pct: float
    volume: int
    oi: int
    oi_change: int


@dataclass
class DailyMovers:
    """Daily movers summary"""
    date: str
    timestamp: str
    top_stock_gainers: List[Dict]
    top_stock_losers: List[Dict]
    top_option_gainers: List[Dict]
    top_option_losers: List[Dict]
    trending_stocks: List[str]  # Appeared multiple days
    summary: Dict


class GainersLosersTracker:
    """Tracks daily top movers in F&O segment."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(NSE_HEADERS)
        self.cookies_initialized = False
        self.data_dir = BASE_DIR / 'data' / 'daily_analysis'
        
    def _initialize_cookies(self) -> bool:
        """Initialize NSE session."""
        if self.cookies_initialized:
            return True
            
        try:
            logger.info("Initializing NSE session...")
            response = self.session.get(NSE_BASE_URL, timeout=15)
            
            if response.status_code == 200:
                self.cookies_initialized = True
                logger.info("✅ Session initialized")
                time.sleep(2)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Init error: {e}")
            return False
    
    def _fetch_data(self, url: str) -> Optional[Dict]:
        """Fetch data from NSE API."""
        if not self._initialize_cookies():
            return None
            
        try:
            response = self.session.get(url, timeout=15)
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"API returned {response.status_code} for {url}")
                return None
        except Exception as e:
            logger.error(f"Fetch error: {e}")
            return None
    
    def fetch_fno_gainers(self) -> List[Dict]:
        """Fetch F&O segment top gainers."""
        data = self._fetch_data(FNO_GAINERS_URL)
        if data and 'data' in data:
            return data['data'][:20]  # Top 20
        return []
    
    def fetch_fno_losers(self) -> List[Dict]:
        """Fetch F&O segment top losers."""
        data = self._fetch_data(FNO_LOSERS_URL)
        if data and 'data' in data:
            return data['data'][:20]
        return []
    
    def fetch_equity_gainers(self) -> List[Dict]:
        """Fetch equity top gainers."""
        data = self._fetch_data(EQUITY_GAINERS_URL)
        if data and 'NIFTY' in data:
            return data['NIFTY']['data'][:20]
        return []
    
    def fetch_equity_losers(self) -> List[Dict]:
        """Fetch equity top losers."""
        data = self._fetch_data(EQUITY_LOSERS_URL)
        if data and 'NIFTY' in data:
            return data['NIFTY']['data'][:20]
        return []
    
    def parse_stock_mover(self, data: Dict) -> Dict:
        """Parse stock mover data."""
        return {
            'symbol': data.get('symbol', ''),
            'ltp': data.get('ltp', 0),
            'change': data.get('change', 0),
            'change_pct': round(data.get('pChange', 0), 2),
            'volume': data.get('totalTradedVolume', 0),
            'previous_close': data.get('previousClose', 0),
            'high': data.get('dayHigh', 0),
            'low': data.get('dayLow', 0),
            'open': data.get('open', 0)
        }
    
    def get_historical_movers(self, days: int = 5) -> Dict[str, int]:
        """Get stocks that appeared in movers list in past N days."""
        stock_counts = {}
        today = datetime.now()
        
        for i in range(1, days + 1):
            check_date = today - timedelta(days=i)
            filepath = self.data_dir / check_date.strftime('%Y-%m-%d') / 'gainers_losers.json'
            
            if filepath.exists():
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                    
                    for gainer in data.get('top_stock_gainers', []):
                        sym = gainer.get('symbol', '')
                        stock_counts[sym] = stock_counts.get(sym, 0) + 1
                    
                    for loser in data.get('top_stock_losers', []):
                        sym = loser.get('symbol', '')
                        stock_counts[sym] = stock_counts.get(sym, 0) + 1
                        
                except Exception as e:
                    logger.warning(f"Error reading {filepath}: {e}")
        
        return stock_counts
    
    def identify_trending_stocks(self, current_gainers: List, current_losers: List, historical: Dict[str, int]) -> List[Dict]:
        """Identify stocks appearing multiple days."""
        trending = []
        
        current_symbols = set()
        for g in current_gainers:
            current_symbols.add(g.get('symbol', ''))
        for l in current_losers:
            current_symbols.add(l.get('symbol', ''))
        
        for symbol in current_symbols:
            if symbol in historical and historical[symbol] >= 2:
                trending.append({
                    'symbol': symbol,
                    'appearances': historical[symbol] + 1,  # +1 for today
                    'interpretation': 'Trending stock - may continue momentum or reverse'
                })
        
        trending.sort(key=lambda x: x['appearances'], reverse=True)
        return trending
    
    def analyze_movers(self, gainers: List[Dict], losers: List[Dict]) -> Dict:
        """Analyze the movers for patterns."""
        analysis = {
            'avg_gainer_change': 0,
            'avg_loser_change': 0,
            'max_gainer': None,
            'max_loser': None,
            'sector_breakdown': {},
            'volatility_signal': ''
        }
        
        if gainers:
            analysis['avg_gainer_change'] = round(
                sum(g.get('change_pct', 0) for g in gainers) / len(gainers), 2
            )
            analysis['max_gainer'] = {
                'symbol': gainers[0].get('symbol'),
                'change_pct': gainers[0].get('change_pct')
            }
        
        if losers:
            analysis['avg_loser_change'] = round(
                sum(l.get('change_pct', 0) for l in losers) / len(losers), 2
            )
            analysis['max_loser'] = {
                'symbol': losers[0].get('symbol'),
                'change_pct': losers[0].get('change_pct')
            }
        
        # Volatility assessment
        total_abs_change = abs(analysis['avg_gainer_change']) + abs(analysis['avg_loser_change'])
        if total_abs_change > 6:
            analysis['volatility_signal'] = 'HIGH - Large moves, potential opportunity'
        elif total_abs_change > 3:
            analysis['volatility_signal'] = 'MEDIUM - Normal market day'
        else:
            analysis['volatility_signal'] = 'LOW - Quiet day, may breakout tomorrow'
        
        return analysis
    
    def collect_daily_movers(self) -> DailyMovers:
        """Collect all daily movers data."""
        logger.info("=" * 50)
        logger.info("COLLECTING DAILY MOVERS")
        logger.info("=" * 50)
        
        # Fetch data
        fno_gainers = self.fetch_fno_gainers()
        time.sleep(1)
        fno_losers = self.fetch_fno_losers()
        time.sleep(1)
        
        # Parse gainers
        stock_gainers = [self.parse_stock_mover(g) for g in fno_gainers if g]
        stock_losers = [self.parse_stock_mover(l) for l in fno_losers if l]
        
        # Get historical data
        historical = self.get_historical_movers(days=5)
        
        # Identify trending stocks
        trending = self.identify_trending_stocks(stock_gainers, stock_losers, historical)
        
        # Analyze
        analysis = self.analyze_movers(stock_gainers, stock_losers)
        
        movers = DailyMovers(
            date=datetime.now().strftime('%Y-%m-%d'),
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            top_stock_gainers=stock_gainers[:10],
            top_stock_losers=stock_losers[:10],
            top_option_gainers=[],  # Will be populated by options scraper
            top_option_losers=[],
            trending_stocks=[t['symbol'] for t in trending],
            summary=analysis
        )
        
        return movers
    
    def save_movers(self, movers: DailyMovers) -> Path:
        """Save movers data to file."""
        save_dir = self.data_dir / movers.date
        save_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = save_dir / 'gainers_losers.json'
        
        with open(filepath, 'w') as f:
            json.dump(asdict(movers), f, indent=2)
        
        logger.info(f"💾 Saved to {filepath.relative_to(BASE_DIR)}")
        return filepath
    
    def get_prediction_candidates(self, movers: DailyMovers) -> List[Dict]:
        """Get stocks likely to move next day based on patterns."""
        candidates = []
        
        # Trending stocks with momentum
        trending = movers.trending_stocks
        
        for gainer in movers.top_stock_gainers[:5]:
            symbol = gainer['symbol']
            change_pct = gainer['change_pct']
            
            if symbol in trending:
                candidates.append({
                    'symbol': symbol,
                    'direction': 'BULLISH' if change_pct > 3 else 'NEUTRAL',
                    'reason': f'Trending gainer ({change_pct}%)',
                    'confidence': 'HIGH' if change_pct > 5 else 'MEDIUM'
                })
        
        for loser in movers.top_stock_losers[:5]:
            symbol = loser['symbol']
            change_pct = loser['change_pct']
            
            if symbol in trending:
                candidates.append({
                    'symbol': symbol,
                    'direction': 'BEARISH' if change_pct < -3 else 'NEUTRAL',
                    'reason': f'Trending loser ({change_pct}%)',
                    'confidence': 'HIGH' if change_pct < -5 else 'MEDIUM'
                })
        
        return candidates


def main():
    """Main execution."""
    logger.info("=" * 60)
    logger.info("GAINERS/LOSERS TRACKER START")
    logger.info("=" * 60)
    
    tracker = GainersLosersTracker()
    
    # Collect today's movers
    movers = tracker.collect_daily_movers()
    
    # Save data
    filepath = tracker.save_movers(movers)
    
    # Print summary
    logger.info("\n📈 TOP GAINERS:")
    for i, g in enumerate(movers.top_stock_gainers[:5], 1):
        logger.info(f"  {i}. {g['symbol']}: +{g['change_pct']}%")
    
    logger.info("\n📉 TOP LOSERS:")
    for i, l in enumerate(movers.top_stock_losers[:5], 1):
        logger.info(f"  {i}. {l['symbol']}: {l['change_pct']}%")
    
    logger.info(f"\n📊 Market: {movers.summary.get('volatility_signal', 'N/A')}")
    
    if movers.trending_stocks:
        logger.info(f"\n🔥 Trending: {', '.join(movers.trending_stocks[:5])}")
    
    # Get prediction candidates
    candidates = tracker.get_prediction_candidates(movers)
    if candidates:
        logger.info("\n🎯 TOMORROW WATCH:")
        for c in candidates:
            logger.info(f"  {c['symbol']}: {c['direction']} ({c['reason']})")
    
    logger.info("=" * 60)
    logger.info("TRACKER COMPLETED")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
