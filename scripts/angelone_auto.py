"""
Angel One Automated Data Collector
===================================
Fully automated NIFTY/BANKNIFTY OHLCV data collection.
No manual TOTP entry required!

Usage:
    python3 angelone_auto.py           # Collect data
    python3 angelone_auto.py test      # Test connection

Created: 2026-01-16
"""

import os
import csv
import pyotp
from pathlib import Path
from datetime import datetime, timedelta
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
TOTP_SECRET = os.getenv('ANGEL_TOTP_SECRET')

# Data directory
DATA_DIR = Path(__file__).parent.parent / 'data' / 'options_ohlcv'
DATA_DIR.mkdir(parents=True, exist_ok=True)


class AngelOneAuto:
    """Fully automated Angel One data collector."""
    
    def __init__(self):
        self.smart_api = SmartConnect(api_key=API_KEY)
        self.logged_in = False
        self.totp = pyotp.TOTP(TOTP_SECRET)
    
    def login(self):
        """Auto login with TOTP generation."""
        try:
            # Generate TOTP automatically
            totp_code = self.totp.now()
            print(f"[Auto] Generated TOTP: {totp_code}")
            
            data = self.smart_api.generateSession(
                clientCode=CLIENT_ID,
                password=PIN,
                totp=totp_code
            )
            
            if data.get('status'):
                self.logged_in = True
                print(f"✅ Auto-logged in as {CLIENT_ID}")
                return True
            else:
                print(f"❌ Login failed: {data.get('message')}")
                return False
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def get_ltp(self, symbol='NIFTY'):
        """Get current LTP."""
        if not self.logged_in:
            return None
        
        tokens = {
            'NIFTY': ('NSE', 'NIFTY', '99926000'),
            'BANKNIFTY': ('NSE', 'BANKNIFTY', '99926009'),
        }
        
        if symbol not in tokens:
            return None
        
        try:
            exch, sym, token = tokens[symbol]
            data = self.smart_api.ltpData(exch, sym, token)
            if data.get('status'):
                return data['data']['ltp']
        except:
            pass
        return None
    
    def get_historical(self, exchange, token, interval='ONE_MINUTE', days=5):
        """Fetch historical OHLCV data."""
        if not self.logged_in:
            return []
        
        now = datetime.now()
        from_date = (now - timedelta(days=days)).strftime('%Y-%m-%d 09:15')
        to_date = now.strftime('%Y-%m-%d %H:%M')
        
        params = {
            'exchange': exchange,
            'symboltoken': str(token),
            'interval': interval,
            'fromdate': from_date,
            'todate': to_date
        }
        
        try:
            result = self.smart_api.getCandleData(params)
            if result.get('status') and result.get('data'):
                return result['data']
        except Exception as e:
            print(f"Error: {e}")
        
        return []
    
    def collect_all(self):
        """Collect NIFTY and BANKNIFTY data."""
        print("\n" + "="*60)
        print("AUTOMATED DATA COLLECTION")
        print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*60)
        
        results = {}
        date_str = datetime.now().strftime('%Y%m%d')
        
        # NIFTY
        print("\n📊 Fetching NIFTY 1-minute data...")
        nifty_data = self.get_historical('NSE', '99926000', 'ONE_MINUTE', 5)
        if nifty_data:
            filepath = DATA_DIR / f'nifty_1min_{date_str}.csv'
            self._save_csv(nifty_data, filepath)
            results['nifty'] = len(nifty_data)
            print(f"✅ NIFTY: {len(nifty_data)} candles saved")
        
        # BANKNIFTY
        print("\n📊 Fetching BANKNIFTY 1-minute data...")
        banknifty_data = self.get_historical('NSE', '99926009', 'ONE_MINUTE', 5)
        if banknifty_data:
            filepath = DATA_DIR / f'banknifty_1min_{date_str}.csv'
            self._save_csv(banknifty_data, filepath)
            results['banknifty'] = len(banknifty_data)
            print(f"✅ BANKNIFTY: {len(banknifty_data)} candles saved")
        
        return results
    
    def _save_csv(self, data, filepath):
        """Save data to CSV."""
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            writer.writerows(data)
    
    def logout(self):
        """Logout."""
        try:
            self.smart_api.terminateSession(CLIENT_ID)
            self.logged_in = False
        except:
            pass


def test_connection():
    """Test automated connection."""
    print("\n" + "="*60)
    print("ANGEL ONE - AUTOMATED CONNECTION TEST")
    print("="*60)
    
    print(f"\nAPI Key: {'✅' if API_KEY else '❌'}")
    print(f"Client ID: {'✅' if CLIENT_ID else '❌'}")
    print(f"PIN: {'✅' if PIN else '❌'}")
    print(f"TOTP Secret: {'✅' if TOTP_SECRET else '❌'}")
    
    if not all([API_KEY, CLIENT_ID, PIN, TOTP_SECRET]):
        print("\n❌ Missing credentials!")
        return False
    
    collector = AngelOneAuto()
    
    if collector.login():
        nifty = collector.get_ltp('NIFTY')
        banknifty = collector.get_ltp('BANKNIFTY')
        
        print(f"\n📈 NIFTY: {nifty}")
        print(f"📈 BANKNIFTY: {banknifty}")
        
        collector.logout()
        print("\n✅ Automated connection working!")
        return True
    
    return False


def main():
    """Run automated collection."""
    collector = AngelOneAuto()
    
    if collector.login():
        nifty = collector.get_ltp('NIFTY')
        banknifty = collector.get_ltp('BANKNIFTY')
        
        print(f"\n📈 NIFTY: {nifty}")
        print(f"📈 BANKNIFTY: {banknifty}")
        
        results = collector.collect_all()
        
        print("\n" + "="*60)
        print("✅ COLLECTION COMPLETE")
        print("="*60)
        
        collector.logout()
    else:
        print("❌ Failed to login")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        test_connection()
    else:
        main()
