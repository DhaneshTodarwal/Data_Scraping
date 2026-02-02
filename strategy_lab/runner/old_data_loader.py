#!/usr/bin/env python3
"""
Old Data Loader
================
Loads JSON data from old-data-by-dj folder.
Format: {status: success, data: {candles: [[timestamp, o, h, l, c, vol, oi], ...]}}
"""
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import os

OLD_DATA_DIR = Path("/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping/old-data-by-dj")


class OldDataLoader:
    """Loader for old JSON format data."""
    
    def __init__(self):
        self.data_dir = OLD_DATA_DIR
    
    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols from old data."""
        symbols = set()
        for year_dir in self.data_dir.iterdir():
            if not year_dir.is_dir():
                continue
            for symbol_dir in year_dir.iterdir():
                if symbol_dir.is_dir() and symbol_dir.name not in ['__pycache__']:
                    symbols.add(symbol_dir.name.upper())
        return sorted(list(symbols))
    
    def get_available_expiry_dates(self, symbol: str) -> List[Tuple[int, str, int]]:
        """Get all available expiry dates for a symbol."""
        expiry_dates = []
        
        # Normalize symbol name (case insensitive)
        symbol_variants = [symbol, symbol.title(), symbol.lower(), symbol.upper()]
        
        for year_dir in sorted(self.data_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            year = int(year_dir.name)
            
            for symbol_dir in year_dir.iterdir():
                if symbol_dir.name.upper() not in [s.upper() for s in symbol_variants]:
                    continue
                
                for month_dir in sorted(symbol_dir.iterdir()):
                    if not month_dir.is_dir():
                        continue
                    month = month_dir.name
                    
                    # Get unique expiry days from filenames
                    days = set()
                    for json_file in month_dir.glob("*.json"):
                        try:
                            day = int(json_file.stem.split('_')[0])
                            days.add(day)
                        except:
                            continue
                    
                    for day in sorted(days):
                        expiry_dates.append((year, month, day))
        
        return expiry_dates
    
    def load_strikes_data(self, symbol: str, year: int, month: str, day: int) -> Dict[str, Dict[int, pd.DataFrame]]:
        """Load all strike data for a specific expiry day."""
        result = {'CE': {}, 'PE': {}}
        
        # Find the correct path
        symbol_variants = [symbol, symbol.title(), symbol.lower(), symbol.upper()]
        data_path = None
        
        for variant in symbol_variants:
            potential_path = self.data_dir / str(year) / variant / month
            if potential_path.exists():
                data_path = potential_path
                break
        
        if data_path is None:
            print(f"⚠️ Data path not found for {symbol}/{year}/{month}")
            return result
        
        # Load all JSON files for this day
        for json_file in data_path.glob(f"{day}_*.json"):
            try:
                parts = json_file.stem.split('_')
                if len(parts) != 3:
                    continue
                
                file_day, option_type, strike = parts
                if int(file_day) != day:
                    continue
                
                strike = int(strike)
                option_type = option_type.upper()
                
                if option_type not in ['CE', 'PE']:
                    continue
                
                # Load JSON
                with open(json_file, 'r') as f:
                    data = json.load(f)
                
                if data.get('status') != 'success':
                    continue
                
                candles = data.get('data', {}).get('candles', [])
                if not candles:
                    continue
                
                # Convert to DataFrame
                df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                # Filter for only the expiry day
                expiry_date = datetime(year, self._month_to_num(month), day)
                df = df[df['timestamp'].dt.date == expiry_date.date()]
                
                if not df.empty:
                    result[option_type][strike] = df
                    
            except Exception as e:
                continue
        
        return result
    
    def _month_to_num(self, month: str) -> int:
        """Convert month name to number."""
        month_map = {
            'jan': 1, 'january': 1, 'JAN': 1,
            'feb': 2, 'february': 2, 'FEB': 2,
            'mar': 3, 'march': 3, 'MAR': 3,
            'apr': 4, 'april': 4, 'APR': 4,
            'may': 5, 'MAY': 5,
            'jun': 6, 'june': 6, 'JUN': 6,
            'jul': 7, 'july': 7, 'JUL': 7,
            'aug': 8, 'august': 8, 'AUG': 8,
            'sep': 9, 'september': 9, 'SEP': 9,
            'oct': 10, 'october': 10, 'OCT': 10,
            'nov': 11, 'november': 11, 'NOV': 11,
            'dec': 12, 'december': 12, 'DEC': 12,
        }
        return month_map.get(month.lower(), 1)
    
    def print_data_summary(self):
        """Print summary of available data."""
        print("\n" + "="*70)
        print("📊 OLD DATA (old-data-by-dj) SUMMARY")
        print("="*70)
        
        symbols = self.get_available_symbols()
        print(f"\nAvailable Symbols: {symbols}")
        
        total_days = 0
        
        for symbol in symbols:
            expiry_dates = self.get_available_expiry_dates(symbol)
            total_days += len(expiry_dates)
            
            print(f"\n{symbol}: {len(expiry_dates)} expiry days")
            
            # Group by year-month
            by_month = {}
            for y, m, d in expiry_dates:
                key = f"{y}-{m}"
                if key not in by_month:
                    by_month[key] = []
                by_month[key].append(d)
            
            for key, days in sorted(by_month.items()):
                print(f"   {key}: {days}")
        
        print(f"\n{'='*70}")
        print(f"TOTAL: {total_days} expiry days across {len(symbols)} symbols")
        print("="*70)
        
        return symbols


if __name__ == "__main__":
    loader = OldDataLoader()
    loader.print_data_summary()
