#!/usr/bin/env python3
"""
Pre-Market Scraper
Runs daily at 9:05 AM IST.
Fetches global market setups (S&P 500, Nasdaq, US VIX, Brent Crude, USD/INR)
and previous closing stats for Nifty and BankNifty using yfinance.
"""
import os
import json
import sys
from datetime import datetime, timezone, timedelta
import yfinance as yf

# IST Timezone setup
IST = timezone(timedelta(hours=5, minutes=30))

# Define base paths relative to script location
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "pre_market_clues")

# Tickers to query
TICKERS = {
    "SP500": "^GSPC",
    "Nasdaq": "^IXIC",
    "US_VIX": "^VIX",
    "Brent_Crude": "BZ=F",
    "USD_INR": "INR=X",
    "Nifty_50": "^NSEI",
    "Bank_Nifty": "^NSEBANK"
}

def fetch_ticker_data(name, symbol):
    """Fetch recent data for a ticker using yfinance."""
    print(f"Fetching data for {name} ({symbol})...")
    ticker = yf.Ticker(symbol)
    # Fetch last 5 days to handle weekends/holidays
    hist = ticker.history(period="5d")
    
    if hist.empty:
        print(f"⚠️ No data found for {name} ({symbol})")
        return None
        
    # Get last two rows to calculate change
    latest_row = hist.iloc[-1]
    prev_row = hist.iloc[-2] if len(hist) > 1 else latest_row
    
    close_val = latest_row["Close"]
    prev_close = prev_row["Close"]
    change = close_val - prev_close
    pct_change = (change / prev_close) * 100 if prev_close != 0 else 0
    
    return {
        "symbol": symbol,
        "open": latest_row["Open"],
        "high": latest_row["High"],
        "low": latest_row["Low"],
        "close": close_val,
        "volume": int(latest_row["Volume"]) if "Volume" in latest_row else 0,
        "change": change,
        "pct_change": pct_change,
        "date": latest_row.name.strftime("%Y-%m-%d")
    }

def main():
    now_ist = datetime.now(IST)
    today_str = now_ist.strftime("%Y-%m-%d")
    year_str = now_ist.strftime("%Y")
    month_str = now_ist.strftime("%B")  # e.g., 'June'
    
    # Target directory structure: data/pre_market_clues/{Year}/{Month}/
    target_dir = os.path.join(DATA_DIR, year_str, month_str)
    os.makedirs(target_dir, exist_ok=True)
    target_file = os.path.join(target_dir, f"{today_str}.json")
    
    print(f"=== Starting Pre-Market Scraper for {today_str} IST ===")
    
    pre_market_data = {
        "timestamp": now_ist.strftime("%Y-%m-%d %H:%M:%S IST"),
        "clues": {}
    }
    
    for name, symbol in TICKERS.items():
        try:
            data = fetch_ticker_data(name, symbol)
            if data:
                pre_market_data["clues"][name] = data
        except Exception as e:
            print(f"❌ Error fetching {name}: {e}")
            
    # Save output
    with open(target_file, "w") as f:
        json.dump(pre_market_data, f, indent=4)
        
    print(f"✅ Pre-market clues successfully saved to: {target_file}")

if __name__ == "__main__":
    main()
