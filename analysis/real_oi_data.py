"""
Real OI Data Fetcher
=====================
Fetches REAL Open Interest from AngelOne option chain

Why this matters:
- Real OI shows actual market positioning
- PCR (Put Call Ratio) from real data
- Max pain calculation from real OI
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from angelone_api import AngelOneAPI
    API_OK = True
except ImportError:
    API_OK = False


class RealOIFetcher:
    """Fetch real OI data from AngelOne"""
    
    def __init__(self):
        self.api = None
        self._logged_in = False
        self._cache = {}
        self._cache_time = None
        self._cache_duration = timedelta(minutes=3)
    
    def _ensure_login(self) -> bool:
        """Ensure API is logged in"""
        if self._logged_in and self.api:
            return True
        
        if not API_OK:
            return False
        
        try:
            self.api = AngelOneAPI()
            if self.api.login():
                self._logged_in = True
                return True
        except:
            pass
        
        return False
    
    def get_option_chain(self, symbol: str, num_strikes: int = 5) -> Optional[Dict]:
        """
        Get option chain with real OI data
        
        Returns dict with:
        - strikes: {strike: {ce_oi, pe_oi, ce_price, pe_price}}
        - total_ce_oi, total_pe_oi
        - pcr (Put Call Ratio)
        - max_pain
        """
        if not self._ensure_login():
            return None
        
        # Check cache
        cache_key = f"{symbol}_{num_strikes}"
        if cache_key in self._cache and self._cache_time:
            if datetime.now(IST) - self._cache_time < self._cache_duration:
                return self._cache[cache_key]
        
        # Get spot price first
        token_map = {
            'NIFTY': ('NSE', 'Nifty 50', '99926000'),
            'BANKNIFTY': ('NSE', 'Nifty Bank', '99926009'),
        }
        
        spot_info = token_map.get(symbol)
        if not spot_info:
            return None
        
        try:
            ltp = self.api.get_ltp(*spot_info)
            spot = float(ltp['data']['ltp'])
        except:
            return None
        
        # Calculate ATM and nearby strikes
        gap = 50 if spot < 30000 else 100
        atm = int(round(spot / gap) * gap)
        
        chain = {
            'symbol': symbol,
            'spot': spot,
            'atm': atm,
            'strikes': {},
            'total_ce_oi': 0,
            'total_pe_oi': 0,
            'pcr': 0,
            'max_pain': atm,
        }
        
        # Try to fetch OI from option chain API
        try:
            # AngelOne doesn't provide direct OI in LTP
            # We'll use an alternative approach: fetch market depth for each strike
            
            # For now, get LTP which sometimes includes OI
            from real_option_prices import get_fetcher
            fetcher = get_fetcher()
            
            for i in range(-num_strikes, num_strikes + 1):
                strike = atm + i * gap
                
                # Get token info
                ce_token = fetcher.get_token(symbol, strike, 'CE')
                pe_token = fetcher.get_token(symbol, strike, 'PE')
                
                ce_oi = 0
                pe_oi = 0
                ce_price = 0
                pe_price = 0
                
                if ce_token:
                    try:
                        # Fetch full quote which may include OI
                        quote = self.api.smart_api.getMarketData(
                            mode='FULL',
                            exchangeTokens={'NFO': [ce_token['token']]}
                        )
                        if quote and quote.get('data'):
                            data = quote['data']['fetched'][0]
                            ce_price = float(data.get('ltp', 0))
                            ce_oi = int(data.get('opnInterest', 0))
                    except:
                        pass
                
                if pe_token:
                    try:
                        quote = self.api.smart_api.getMarketData(
                            mode='FULL',
                            exchangeTokens={'NFO': [pe_token['token']]}
                        )
                        if quote and quote.get('data'):
                            data = quote['data']['fetched'][0]
                            pe_price = float(data.get('ltp', 0))
                            pe_oi = int(data.get('opnInterest', 0))
                    except:
                        pass
                
                chain['strikes'][strike] = {
                    'ce_oi': ce_oi,
                    'pe_oi': pe_oi,
                    'ce_price': ce_price,
                    'pe_price': pe_price,
                }
                
                chain['total_ce_oi'] += ce_oi
                chain['total_pe_oi'] += pe_oi
            
            # Calculate PCR
            if chain['total_ce_oi'] > 0:
                chain['pcr'] = chain['total_pe_oi'] / chain['total_ce_oi']
            
            # Calculate Max Pain
            chain['max_pain'] = self._calculate_max_pain(chain['strikes'], spot, gap)
            
            # Cache
            self._cache[cache_key] = chain
            self._cache_time = datetime.now(IST)
            
            return chain
            
        except Exception as e:
            print(f"OI fetch error: {e}")
            return None
    
    def _calculate_max_pain(self, strikes: Dict, spot: float, gap: int) -> int:
        """Calculate max pain strike"""
        if not strikes:
            return int(round(spot / gap) * gap)
        
        min_pain = float('inf')
        max_pain_strike = int(round(spot / gap) * gap)
        
        for strike, data in strikes.items():
            # Calculate pain at this strike
            ce_pain = sum(
                max(0, strike - s) * d['ce_oi']
                for s, d in strikes.items()
            )
            pe_pain = sum(
                max(0, s - strike) * d['pe_oi']
                for s, d in strikes.items()
            )
            total_pain = ce_pain + pe_pain
            
            if total_pain < min_pain:
                min_pain = total_pain
                max_pain_strike = strike
        
        return max_pain_strike
    
    def get_pcr(self, symbol: str) -> Optional[float]:
        """Get Put Call Ratio"""
        chain = self.get_option_chain(symbol)
        if chain:
            return chain['pcr']
        return None
    
    def get_max_pain(self, symbol: str) -> Optional[int]:
        """Get max pain strike"""
        chain = self.get_option_chain(symbol)
        if chain:
            return chain['max_pain']
        return None
    
    def get_oi_analysis(self, symbol: str) -> Dict:
        """Get complete OI analysis"""
        chain = self.get_option_chain(symbol)
        
        if not chain:
            return {
                'symbol': symbol,
                'data_available': False,
                'message': 'OI data unavailable',
            }
        
        # Determine bias from PCR
        pcr = chain['pcr']
        if pcr > 1.2:
            bias = 'BULLISH'
            bias_msg = 'High PCR - Bears covered, expect up move'
        elif pcr < 0.8:
            bias = 'BEARISH'
            bias_msg = 'Low PCR - Bulls exposed, expect down move'
        else:
            bias = 'NEUTRAL'
            bias_msg = 'Neutral PCR - No clear direction'
        
        # Max pain analysis
        spot = chain['spot']
        max_pain = chain['max_pain']
        mp_diff = abs(spot - max_pain)
        mp_pct = mp_diff / spot * 100
        
        if mp_pct < 0.3:
            mp_msg = f'Spot near max pain ({max_pain}) - Favorable for Iron Condor'
        else:
            mp_msg = f'Max pain at {max_pain}, spot may gravitate there'
        
        return {
            'symbol': symbol,
            'data_available': True,
            'spot': spot,
            'atm': chain['atm'],
            'total_ce_oi': chain['total_ce_oi'],
            'total_pe_oi': chain['total_pe_oi'],
            'pcr': pcr,
            'pcr_bias': bias,
            'pcr_message': bias_msg,
            'max_pain': max_pain,
            'max_pain_message': mp_msg,
        }


# Singleton
_fetcher = None


def get_oi_fetcher() -> RealOIFetcher:
    global _fetcher
    if _fetcher is None:
        _fetcher = RealOIFetcher()
    return _fetcher


def get_real_pcr(symbol: str) -> Optional[float]:
    """Get real PCR"""
    return get_oi_fetcher().get_pcr(symbol)


def get_real_max_pain(symbol: str) -> Optional[int]:
    """Get real max pain"""
    return get_oi_fetcher().get_max_pain(symbol)


def get_oi_analysis(symbol: str) -> Dict:
    """Get OI analysis"""
    return get_oi_fetcher().get_oi_analysis(symbol)


if __name__ == "__main__":
    print("="*60)
    print("       REAL OI DATA FETCHER")
    print("="*60)
    
    for symbol in ['NIFTY', 'BANKNIFTY']:
        print(f"\n{symbol}:")
        
        analysis = get_oi_analysis(symbol)
        
        if analysis['data_available']:
            print(f"  Spot: ₹{analysis['spot']:,.2f}")
            print(f"  Total CE OI: {analysis['total_ce_oi']:,}")
            print(f"  Total PE OI: {analysis['total_pe_oi']:,}")
            print(f"  PCR: {analysis['pcr']:.2f} ({analysis['pcr_bias']})")
            print(f"  Max Pain: {analysis['max_pain']}")
            print(f"  Bias: {analysis['pcr_message']}")
        else:
            print(f"  {analysis['message']}")
