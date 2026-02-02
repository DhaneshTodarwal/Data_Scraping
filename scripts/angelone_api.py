"""
Angel One SmartAPI Integration
==============================
Fetch options OHLCV data, option chains, and historical data.

Created: 2026-01-16
"""

import os
import pyotp
from datetime import datetime, timedelta
from pathlib import Path
from SmartApi import SmartConnect

# Load environment variables
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
SECRET_KEY = os.getenv('ANGEL_SECRET_KEY')
CLIENT_ID = os.getenv('ANGEL_CLIENT_ID')
PIN = os.getenv('ANGEL_PIN')
TOTP_TOKEN = os.getenv('ANGEL_TOTP_SECRET', '')  # Optional - for TOTP auth


class AngelOneAPI:
    """Angel One SmartAPI wrapper for options data collection."""
    
    def __init__(self):
        self.api_key = API_KEY
        self.client_id = CLIENT_ID
        self.pin = PIN
        self.totp_token = TOTP_TOKEN
        self.smart_api = SmartConnect(api_key=self.api_key)
        self.auth_token = None
        self.feed_token = None
        self.logged_in = False
    
    def login(self, totp_code=None):
        """
        Login to Angel One API.
        
        Args:
            totp_code: 6-digit TOTP code (if TOTP is enabled)
        """
        try:
            # Generate TOTP if token is available
            if self.totp_token and not totp_code:
                totp = pyotp.TOTP(self.totp_token)
                totp_code = totp.now()
            
            if totp_code:
                data = self.smart_api.generateSession(
                    clientCode=self.client_id,
                    password=self.pin,
                    totp=totp_code
                )
            else:
                # Try without TOTP (may not work if TOTP is mandatory)
                data = self.smart_api.generateSession(
                    clientCode=self.client_id,
                    password=self.pin
                )
            
            if data.get('status'):
                self.auth_token = data['data']['jwtToken']
                self.feed_token = self.smart_api.getfeedToken()
                self.logged_in = True
                print(f"✅ Logged in successfully as {self.client_id}")
                return True
            else:
                print(f"❌ Login failed: {data.get('message', data)}")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def get_profile(self):
        """Get user profile."""
        if not self.logged_in:
            print("Not logged in")
            return None
        return self.smart_api.getProfile(self.smart_api.refresh_token)
    
    def search_symbol(self, exchange, symbol):
        """
        Search for instrument token.
        
        Args:
            exchange: NSE, NFO, BSE, etc.
            symbol: Trading symbol
        """
        try:
            # For options, use instrument list
            # Angel One uses a different approach - need to download instrument list
            return self.smart_api.searchScrip(exchange, symbol)
        except Exception as e:
            print(f"Search error: {e}")
            return None
    
    def get_ltp(self, exchange, symbol, token):
        """
        Get Last Traded Price.
        
        Args:
            exchange: NSE, NFO, etc.
            symbol: Trading symbol
            token: Instrument token
        """
        if not self.logged_in:
            print("Not logged in")
            return None
        
        try:
            data = self.smart_api.ltpData(exchange, symbol, token)
            return data
        except Exception as e:
            print(f"LTP error: {e}")
            return None
    
    def get_historical_data(self, exchange, symbol, token, interval, from_date, to_date):
        """
        Get historical candle data.
        
        Args:
            exchange: NSE, NFO, etc.
            symbol: Trading symbol
            token: Instrument token
            interval: ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, THIRTY_MINUTE, 
                     ONE_HOUR, ONE_DAY
            from_date: Start datetime (YYYY-MM-DD HH:MM)
            to_date: End datetime (YYYY-MM-DD HH:MM)
        
        Returns:
            list: Candle data [timestamp, open, high, low, close, volume]
        """
        if not self.logged_in:
            print("Not logged in")
            return None
        
        try:
            params = {
                "exchange": exchange,
                "symboltoken": token,
                "interval": interval,
                "fromdate": from_date,
                "todate": to_date
            }
            data = self.smart_api.getCandleData(params)
            return data
        except Exception as e:
            print(f"Historical data error: {e}")
            return None
    
    def get_option_chain(self, symbol="NIFTY"):
        """
        Note: Angel One doesn't provide direct option chain API.
        You need to use instrument list and filter.
        """
        print("Option chain requires instrument list download - use get_instruments()")
        return None
    
    def logout(self):
        """Logout from API."""
        try:
            self.smart_api.terminateSession(self.client_id)
            self.logged_in = False
            print("Logged out")
        except:
            pass


def test_connection():
    """Test Angel One API."""
    print("\n" + "="*60)
    print("ANGEL ONE API TEST")
    print("="*60)
    
    print(f"\nAPI Key: {'✅ Set' if API_KEY else '❌ Missing'}")
    print(f"Client ID: {'✅ Set' if CLIENT_ID else '❌ Missing'}")
    print(f"PIN: {'✅ Set' if PIN else '❌ Missing'}")
    print(f"TOTP Token: {'✅ Set' if TOTP_TOKEN else '⚠️ Not set (may need manual TOTP)'}")
    
    if not all([API_KEY, CLIENT_ID, PIN]):
        print("\n❌ Missing credentials!")
        return False
    
    print("\n[Attempting login...]")
    print("If TOTP is enabled, you'll need to enter it manually.")
    
    api = AngelOneAPI()
    
    # Try login without TOTP first
    if api.login():
        print("\n✅ API connection successful!")
        
        # Test LTP for NIFTY
        print("\n[Testing LTP fetch for NIFTY...]")
        # NIFTY token is 99926000 on NSE
        ltp = api.get_ltp('NSE', 'NIFTY', '99926000')
        if ltp:
            print(f"NIFTY LTP: {ltp}")
        
        api.logout()
        return True
    else:
        print("\n⚠️ Login failed - TOTP may be required")
        print("Run: python3 angelone_api.py auth")
        return False


def interactive_login():
    """Interactive login with TOTP."""
    print("\n" + "="*60)
    print("ANGEL ONE LOGIN")
    print("="*60)
    
    api = AngelOneAPI()
    
    totp_code = input("\nEnter your 6-digit TOTP code: ").strip()
    
    if api.login(totp_code):
        print("\n✅ Login successful!")
        return api
    else:
        print("\n❌ Login failed!")
        return None


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'auth':
        interactive_login()
    else:
        test_connection()
