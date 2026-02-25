import os, sys
from pathlib import Path

# Set up paths and load env
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

# Parse .env directly since python-dotenv might not be installed
env_vars = {}
with open(BASE_DIR / '.env') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            k, v = line.strip().split('=', 1)
            env_vars[k] = v.strip('"\'')

from SmartApi import SmartConnect

api_key = env_vars.get('ANGEL_API_KEY')
client_code = env_vars.get('ANGEL_CLIENT_ID')
password = env_vars.get('ANGEL_PIN')
totp_secret = env_vars.get('ANGEL_TOTP_SECRET')

smart_api = SmartConnect(api_key=api_key)

try:
    import pyotp
    import logging
    logging.basicConfig(level=logging.ERROR)
    
    # Login
    totp = pyotp.TOTP(totp_secret).now()
    data = smart_api.generateSession(client_code, password, totp)
    print(f"Login Status: {data['status']}")
    
    # RELIANCE token is 2885
    from datetime import datetime
    now = datetime.now()
    from_date = now.replace(hour=9, minute=15, second=0).strftime('%Y-%m-%d %H:%M')
    to_date = now.strftime('%Y-%m-%d %H:%M')
    
    params = {
        'exchange': 'NSE',
        'symboltoken': '2885',  # RELIANCE
        'interval': 'ONE_MINUTE',
        'fromdate': from_date,
        'todate': to_date
    }
    print(f"Params: {params}")
    
    resp = smart_api.getCandleData(params)
    print(f"Response Status: {resp.get('status', 'No status found')}")
    print(f"Data length: {len(resp.get('data', [])) if resp.get('data') else 0}")
    print(f"Full response: {resp}")
    
except Exception as e:
    print(f"Error: {e}")
