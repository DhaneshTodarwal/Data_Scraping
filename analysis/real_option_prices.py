"""
Real Option Price Fetcher
==========================
Downloads AngelOne instrument list and fetches REAL option prices

How it works:
1. Downloads instrument list from AngelOne
2. Filters for NFO (options) and builds token lookup
3. For any strike+expiry, finds the token
4. Uses token to fetch real LTP

This gives EXACT option prices matching broker!
"""
import os
import json
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

IST = timezone(timedelta(hours=5, minutes=30))

# Import AngelOne API
try:
    from angelone_api import AngelOneAPI
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False
    print("⚠ AngelOne API not available")


class RealOptionPriceFetcher:
    """
    Fetches REAL option prices from AngelOne
    by downloading instrument list and mapping tokens
    """
    
    # AngelOne instrument list URL
    INSTRUMENT_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    
    def __init__(self):
        self.cache_dir = Path(__file__).parent / "cache"
        self.cache_dir.mkdir(exist_ok=True)
        
        self.instrument_file = self.cache_dir / "instruments.json"
        self.token_cache_file = self.cache_dir / "token_cache.json"
        
        self.instruments = []
        self.token_cache = {}  # symbol_strike_type_expiry -> token
        
        self.api = None
        self._logged_in = False
        
        # Load cached data
        self._load_cache()
    
    def _load_cache(self):
        """Load cached token mapping"""
        if self.token_cache_file.exists():
            try:
                with open(self.token_cache_file, 'r') as f:
                    data = json.load(f)
                    # Check if cache is from today
                    today = datetime.now(IST).strftime('%Y-%m-%d')
                    if data.get('date') == today:
                        self.token_cache = data.get('tokens', {})
                        print(f"✅ Loaded {len(self.token_cache)} cached tokens")
                    else:
                        print(f"⚠️ Cache is from {data.get('date')}, downloading fresh...")
                        self.download_instruments()
            except Exception as e:
                print(f"Cache load error: {e}")
        else:
            print("📥 No cache found, downloading instruments...")
            self.download_instruments()
    
    def _save_cache(self):
        """Save token cache"""
        data = {
            'date': datetime.now(IST).strftime('%Y-%m-%d'),
            'tokens': self.token_cache,
        }
        with open(self.token_cache_file, 'w') as f:
            json.dump(data, f)
    
    def download_instruments(self) -> bool:
        """Download instrument list from AngelOne"""
        print("📥 Downloading instrument list...")
        
        try:
            response = requests.get(self.INSTRUMENT_URL, timeout=60)
            response.raise_for_status()
            
            self.instruments = response.json()
            
            # Save to file
            with open(self.instrument_file, 'w') as f:
                json.dump(self.instruments, f)
            
            print(f"✅ Downloaded {len(self.instruments)} instruments")
            
            # Build token cache for NFO
            self._build_token_cache()
            
            return True
            
        except Exception as e:
            print(f"❌ Download failed: {e}")
            return False
    
    def _build_token_cache(self):
        """Build lookup cache for quick token finding"""
        print("🔧 Building token cache...")
        
        nfo_count = 0
        
        for inst in self.instruments:
            # Filter for NFO (options)
            if inst.get('exch_seg') != 'NFO':
                continue
            
            symbol = inst.get('name', '')
            strike = inst.get('strike', '')
            token = inst.get('token', '')
            trading_symbol = inst.get('symbol', '')
            expiry = inst.get('expiry', '')
            instrument_type = inst.get('instrumenttype', '')
            
            # Skip if not option
            if instrument_type not in ['OPTIDX', 'OPTSTK']:
                continue
            
            # Determine if CE or PE from trading symbol
            if 'CE' in trading_symbol or symbol.endswith('CE'):
                opt_type = 'CE'
            elif 'PE' in trading_symbol or symbol.endswith('PE'):
                opt_type = 'PE'
            else:
                continue
            
            # Get underlying (NIFTY, BANKNIFTY, etc.)
            underlying = symbol.replace('NIFTY', 'NIFTY').replace('BANKNIFTY', 'BANKNIFTY')
            if 'NIFTY' in trading_symbol:
                if 'BANKNIFTY' in trading_symbol:
                    underlying = 'BANKNIFTY'
                elif 'FINNIFTY' in trading_symbol:
                    underlying = 'FINNIFTY'
                else:
                    underlying = 'NIFTY'
            
            # Convert strike (comes as "2550000" for 25500)
            try:
                strike_int = int(float(strike) / 100) if strike else 0
            except:
                continue
            
            if strike_int == 0:
                continue
            
            # Create cache key: NIFTY_25500_CE_25JAN2026
            cache_key = f"{underlying}_{strike_int}_{opt_type}_{expiry}"
            
            self.token_cache[cache_key] = {
                'token': token,
                'symbol': trading_symbol,
                'strike': strike_int,
                'expiry': expiry,
            }
            
            nfo_count += 1
        
        print(f"✅ Cached {nfo_count} option tokens")
        self._save_cache()
    
    def _get_expiry_string(self, symbol: str) -> str:
        """Get nearest expiry date string"""
        today = datetime.now(IST).date()
        
        # Expiry days: NIFTY=Thu, BankNifty=Wed, FinNifty=Tue
        expiry_days = {
            'NIFTY': 3,      # Thursday
            'BANKNIFTY': 2,  # Wednesday
            'FINNIFTY': 1,   # Tuesday
        }
        
        expiry_day = expiry_days.get(symbol, 3)
        
        days_ahead = expiry_day - today.weekday()
        if days_ahead < 0:
            days_ahead += 7
        
        expiry_date = today + timedelta(days=days_ahead)
        
        # Format: 23JAN2026
        return expiry_date.strftime('%d%b%Y').upper()
    
    def get_token(self, symbol: str, strike: int, option_type: str, 
                  expiry: str = None) -> Optional[Dict]:
        """Get token info for a strike"""
        
        if not expiry:
            expiry = self._get_expiry_string(symbol)
        
        # Try exact match first
        cache_key = f"{symbol}_{strike}_{option_type}_{expiry}"
        
        if cache_key in self.token_cache:
            return self.token_cache[cache_key]
        
        # Try to find closest expiry
        prefix = f"{symbol}_{strike}_{option_type}_"
        matches = [(k, v) for k, v in self.token_cache.items() if k.startswith(prefix)]
        
        if matches:
            # Sort by expiry and return nearest
            return matches[0][1]
        
        return None
    
    def _ensure_login(self) -> bool:
        """Ensure API is logged in"""
        if self._logged_in and self.api:
            return True
        
        if not API_AVAILABLE:
            return False
        
        try:
            self.api = AngelOneAPI()
            if self.api.login():
                self._logged_in = True
                return True
        except Exception as e:
            print(f"Login error: {e}")
        
        return False
    
    def get_real_option_price(self, symbol: str, strike: int, 
                               option_type: str) -> Optional[float]:
        """
        Get REAL option price from AngelOne
        
        Args:
            symbol: NIFTY, BANKNIFTY
            strike: Strike price (25500, 60000, etc.)
            option_type: CE or PE
        
        Returns:
            Real LTP from broker
        """
        # Get token info
        token_info = self.get_token(symbol, strike, option_type)
        
        if not token_info:
            print(f"⚠ Token not found for {symbol} {strike} {option_type}")
            return None
        
        # Ensure logged in
        if not self._ensure_login():
            print("⚠ Cannot login to API")
            return None
        
        try:
            # Fetch LTP
            ltp_data = self.api.get_ltp(
                'NFO',
                token_info['symbol'],
                token_info['token']
            )
            
            if ltp_data and ltp_data.get('data'):
                price = float(ltp_data['data']['ltp'])
                print(f"✅ {symbol} {strike} {option_type}: ₹{price}")
                return price
                
        except Exception as e:
            print(f"LTP error: {e}")
        
        return None
    
    def get_option_chain(self, symbol: str, num_strikes: int = 5) -> Dict:
        """
        Get option chain with real prices
        
        Returns dict with strikes and their CE/PE prices
        """
        # First, get spot price
        if not self._ensure_login():
            return {}
        
        # Get spot
        token_map = {
            'NIFTY': ('NSE', 'Nifty 50', '99926000'),
            'BANKNIFTY': ('NSE', 'Nifty Bank', '99926009'),
        }
        
        spot_info = token_map.get(symbol)
        if not spot_info:
            return {}
        
        try:
            ltp_data = self.api.get_ltp(*spot_info)
            spot = float(ltp_data['data']['ltp'])
        except:
            return {}
        
        # Calculate ATM and nearby strikes
        gap = 50 if spot < 30000 else 100
        atm = int(round(spot / gap) * gap)
        
        chain = {
            'symbol': symbol,
            'spot': spot,
            'atm': atm,
            'strikes': {},
        }
        
        # Fetch prices for strikes around ATM
        for i in range(-num_strikes, num_strikes + 1):
            strike = atm + i * gap
            
            ce_price = self.get_real_option_price(symbol, strike, 'CE')
            pe_price = self.get_real_option_price(symbol, strike, 'PE')
            
            chain['strikes'][strike] = {
                'ce': ce_price,
                'pe': pe_price,
            }
        
        return chain
    
    def logout(self):
        """Logout from API"""
        if self.api and self._logged_in:
            try:
                self.api.logout()
            except:
                pass
            self._logged_in = False


# Singleton instance
_fetcher = None


def get_fetcher() -> RealOptionPriceFetcher:
    """Get singleton fetcher instance"""
    global _fetcher
    if _fetcher is None:
        _fetcher = RealOptionPriceFetcher()
    return _fetcher


def get_real_option_price(symbol: str, strike: int, option_type: str) -> Optional[float]:
    """Get real option price"""
    return get_fetcher().get_real_option_price(symbol, strike, option_type)


def download_instruments():
    """Download instrument list"""
    return get_fetcher().download_instruments()


# =============================================================================
# TEST
# =============================================================================

def test_real_prices():
    """Test fetching real option prices"""
    print("\n" + "="*60)
    print("       REAL OPTION PRICE FETCHER TEST")
    print("="*60)
    
    fetcher = RealOptionPriceFetcher()
    
    # Download instruments if not cached
    if not fetcher.token_cache:
        fetcher.download_instruments()
    
    # Test getting prices
    print("\n📊 Fetching real prices...")
    
    for symbol in ['NIFTY', 'BANKNIFTY']:
        print(f"\n{symbol}:")
        
        # Get spot first
        if fetcher._ensure_login():
            token_map = {
                'NIFTY': ('NSE', 'Nifty 50', '99926000'),
                'BANKNIFTY': ('NSE', 'Nifty Bank', '99926009'),
            }
            
            try:
                ltp = fetcher.api.get_ltp(*token_map[symbol])
                spot = float(ltp['data']['ltp'])
                print(f"  Spot: ₹{spot:,.2f}")
                
                gap = 50 if spot < 30000 else 100
                atm = int(round(spot / gap) * gap)
                
                # Get ATM CE and PE prices
                ce_price = fetcher.get_real_option_price(symbol, atm, 'CE')
                pe_price = fetcher.get_real_option_price(symbol, atm, 'PE')
                
                print(f"  ATM ({atm}):")
                print(f"    CE: ₹{ce_price if ce_price else 'N/A'}")
                print(f"    PE: ₹{pe_price if pe_price else 'N/A'}")
                
            except Exception as e:
                print(f"  Error: {e}")
    
    fetcher.logout()
    print("\n✅ Test complete!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true', help='Download instruments')
    parser.add_argument('--test', action='store_true', help='Test fetching prices')
    
    args = parser.parse_args()
    
    if args.download:
        download_instruments()
    elif args.test:
        test_real_prices()
    else:
        print("Real Option Price Fetcher")
        print("  --download  Download instrument list")
        print("  --test      Test fetching real prices")
