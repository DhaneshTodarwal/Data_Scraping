"""
Angel One Options Data Collector
================================
Fetches NIFTY and BANKNIFTY options OHLCV data.

Usage:
    python3 angelone_collector.py

Created: 2026-01-16
"""

import os
import json
import csv
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
CLIENT_ID = os.getenv('ANGEL_CLIENT_ID')
PIN = os.getenv('ANGEL_PIN')

# Data directory
DATA_DIR = Path(__file__).parent.parent / 'data' / 'options_ohlcv'
DATA_DIR.mkdir(parents=True, exist_ok=True)


class AngelOneCollector:
    """Collect options OHLCV data from Angel One."""
    
    def __init__(self):
        self.smart_api = SmartConnect(api_key=API_KEY)
        self.logged_in = False
    
    def login(self, totp):
        """Login with TOTP."""
        try:
            data = self.smart_api.generateSession(
                clientCode=CLIENT_ID,
                password=PIN,
                totp=totp
            )
            if data.get('status'):
                self.logged_in = True
                print(f"✅ Logged in as {CLIENT_ID}")
                return True
            else:
                print(f"❌ Login failed: {data.get('message')}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def get_nifty_ltp(self):
        """Get NIFTY current price."""
        if not self.logged_in:
            return None
        try:
            data = self.smart_api.ltpData('NSE', 'NIFTY', '99926000')
            if data.get('status'):
                return data['data']['ltp']
        except:
            pass
        return None
    
    def get_banknifty_ltp(self):
        """Get BANKNIFTY current price."""
        if not self.logged_in:
            return None
        try:
            data = self.smart_api.ltpData('NSE', 'BANKNIFTY', '99926009')
            if data.get('status'):
                return data['data']['ltp']
        except:
            pass
        return None
    
    def get_historical_data(self, exchange, token, interval='ONE_MINUTE', days=1):
        """
        Fetch historical OHLCV data.
        
        Args:
            exchange: NSE, NFO
            token: Instrument token
            interval: ONE_MINUTE, FIVE_MINUTE, FIFTEEN_MINUTE, ONE_DAY
            days: Number of days to fetch
        
        Returns:
            list: [[timestamp, open, high, low, close, volume], ...]
        """
        if not self.logged_in:
            print("Not logged in")
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
            print(f"Error fetching data: {e}")
        
        return []
    
    def get_nifty_candles(self, interval='ONE_MINUTE', days=5):
        """Get NIFTY index candles."""
        return self.get_historical_data('NSE', '99926000', interval, days)
    
    def get_banknifty_candles(self, interval='ONE_MINUTE', days=5):
        """Get BANKNIFTY index candles."""
        return self.get_historical_data('NSE', '99926009', interval, days)
    
    def save_to_csv(self, data, filename):
        """Save candle data to CSV."""
        filepath = DATA_DIR / filename
        
        with open(filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            writer.writerows(data)
        
        print(f"💾 Saved {len(data)} candles to {filepath}")
        return filepath
    
    def collect_index_data(self):
        """Collect NIFTY and BANKNIFTY index data."""
        print("\n" + "="*60)
        print("COLLECTING INDEX OHLCV DATA")
        print("="*60)
        
        # NIFTY
        print("\n📊 Fetching NIFTY 1-minute data (5 days)...")
        nifty_data = self.get_nifty_candles('ONE_MINUTE', 5)
        if nifty_data:
            date_str = datetime.now().strftime('%Y%m%d')
            self.save_to_csv(nifty_data, f'nifty_1min_{date_str}.csv')
        
        # BANKNIFTY
        print("\n📊 Fetching BANKNIFTY 1-minute data (5 days)...")
        banknifty_data = self.get_banknifty_candles('ONE_MINUTE', 5)
        if banknifty_data:
            date_str = datetime.now().strftime('%Y%m%d')
            self.save_to_csv(banknifty_data, f'banknifty_1min_{date_str}.csv')
        
        return {
            'nifty_candles': len(nifty_data),
            'banknifty_candles': len(banknifty_data)
        }
    
    def logout(self):
        """Logout."""
        try:
            self.smart_api.terminateSession(CLIENT_ID)
            self.logged_in = False
        except:
            pass


def main():
    """Interactive data collection."""
    print("\n" + "="*60)
    print("ANGEL ONE OPTIONS DATA COLLECTOR")
    print("="*60)
    
    print(f"\nData will be saved to: {DATA_DIR}")
    
    totp = input("\nEnter your TOTP code: ").strip()
    
    if not totp:
        print("❌ TOTP required")
        return
    
    collector = AngelOneCollector()
    
    if collector.login(totp):
        # Get current prices
        nifty_ltp = collector.get_nifty_ltp()
        banknifty_ltp = collector.get_banknifty_ltp()
        
        print(f"\n📈 NIFTY LTP: {nifty_ltp}")
        print(f"📈 BANKNIFTY LTP: {banknifty_ltp}")
        
        # Collect data
        result = collector.collect_index_data()
        
        print("\n" + "="*60)
        print("COLLECTION COMPLETE")
        print("="*60)
        print(f"NIFTY candles: {result['nifty_candles']}")
        print(f"BANKNIFTY candles: {result['banknifty_candles']}")
        
        collector.logout()
    else:
        print("❌ Failed to login")


if __name__ == "__main__":
    main()
