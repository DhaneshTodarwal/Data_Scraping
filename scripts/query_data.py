"""
Data Query Utility
==================
Quick and easy access to collected options data.

Usage Examples:
    # Get NIFTY data for a specific date
    python query_data.py --symbol NIFTY --date 2026-01-16
    
    # Get specific strike data
    python query_data.py --symbol NIFTY --strike 25700 --type CE --date 2026-01-16
    
    # Get last 7 days summary
    python query_data.py --summary --days 7

Created: 2026-01-16
"""

import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import json


class DataQuery:
    """Query collected options data easily."""
    
    def __init__(self, base_dir=None):
        if base_dir is None:
            self.base_dir = Path(__file__).parent.parent
        else:
            self.base_dir = Path(base_dir)
        
        self.data_dir = self.base_dir / 'data'
    
    def get_index_data(self, symbol: str, date: str):
        """Get index 1-min OHLCV data."""
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        year = date_obj.strftime('%Y')
        month = date_obj.strftime('%b')
        
        filepath = self.data_dir / 'index_ohlcv' / year / month / symbol / f"{date}.csv"
        
        if not filepath.exists():
            print(f"❌ No data found for {symbol} on {date}")
            return None
        
        df = pd.read_csv(filepath)
        return df
    
    def get_strike_data(self, symbol: str, strike: int, option_type: str, date: str):
        """Get specific strike OHLCV data."""
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        year = date_obj.strftime('%Y')
        month_num = date_obj.strftime('%m')
        month_name = date_obj.strftime('%B')
        day = date_obj.strftime('%d')
        
        month_folder = f"{month_num}_{month_name}"
        filepath = self.data_dir / 'strikes_ohlcv' / symbol / year / month_folder / day / option_type / f"{strike}.csv"
        
        if not filepath.exists():
            print(f"❌ No data found for {symbol} {strike} {option_type} on {date}")
            return None
        
        df = pd.read_csv(filepath)
        return df
    
    def get_available_strikes(self, symbol: str, date: str, option_type: str):
        """List all available strikes for a date."""
        date_obj = datetime.strptime(date, '%Y-%m-%d')
        year = date_obj.strftime('%Y')
        month_num = date_obj.strftime('%m')
        month_name = date_obj.strftime('%B')
        day = date_obj.strftime('%d')
        
        month_folder = f"{month_num}_{month_name}"
        dir_path = self.data_dir / 'strikes_ohlcv' / symbol / year / month_folder / day / option_type
        
        if not dir_path.exists():
            return []
        
        strikes = [int(f.stem) for f in dir_path.glob('*.csv')]
        return sorted(strikes)
    
    def get_metadata_summary(self, days: int = 7):
        """Get metadata summary for last N days."""
        metadata_dir = self.data_dir / 'metadata'
        
        if not metadata_dir.exists():
            print("❌ No metadata found")
            return None
        
        summaries = []
        for meta_file in sorted(metadata_dir.glob('*.json'))[-days:]:
            with open(meta_file, 'r') as f:
                summaries.append(json.load(f))
        
        return summaries


def main():
    parser = argparse.ArgumentParser(description='Query options data')
    parser.add_argument('--symbol', choices=['NIFTY', 'BANKNIFTY'], help='Symbol')
    parser.add_argument('--date', help='Date (YYYY-MM-DD)')
    parser.add_argument('--strike', type=int, help='Strike price')
    parser.add_argument('--type', choices=['CE', 'PE'], help='Option type')
    parser.add_argument('--summary', action='store_true', help='Show summary')
    parser.add_argument('--days', type=int, default=7, help='Days for summary')
    parser.add_argument('--list-strikes', action='store_true', help='List available strikes')
    
    args = parser.parse_args()
    query = DataQuery()
    
    if args.summary:
        # Show summary
        summaries = query.get_metadata_summary(args.days)
        if summaries:
            print(f"\n📊 Summary (Last {args.days} days)")
            print("="*60)
            for s in summaries:
                print(f"Date: {s['date']}")
                print(f"  NIFTY LTP: {s['nifty']['ltp']}, ATM: {s['nifty']['atm']}")
                print(f"  BANKNIFTY LTP: {s['banknifty']['ltp']}, ATM: {s['banknifty']['atm']}")
                print(f"  Files: {s['total_files']}, Status: {s['status']}")
                print()
    
    elif args.list_strikes:
        # List strikes
        if not all([args.symbol, args.date, args.type]):
            print("❌ Need --symbol, --date, and --type for listing strikes")
            return
        
        strikes = query.get_available_strikes(args.symbol, args.date, args.type)
        print(f"\n📋 Available {args.symbol} {args.type} strikes on {args.date}:")
        print(', '.join(map(str, strikes)))
    
    elif args.strike:
        # Get strike data
        if not all([args.symbol, args.date, args.type]):
            print("❌ Need --symbol, --date, and --type for strike data")
            return
        
        df = query.get_strike_data(args.symbol, args.strike, args.type, args.date)
        if df is not None:
            print(f"\n📊 {args.symbol} {args.strike} {args.type} on {args.date}")
            print("="*60)
            print(df.head(10))
            print(f"\nTotal candles: {len(df)}")
    
    else:
        # Get index data
        if not all([args.symbol, args.date]):
            print("❌ Need --symbol and --date for index data")
            return
        
        df = query.get_index_data(args.symbol, args.date)
        if df is not None:
            print(f"\n📊 {args.symbol} Index on {args.date}")
            print("="*60)
            print(df.head(10))
            print(f"\nTotal candles: {len(df)}")


if __name__ == "__main__":
    main()
