"""
Historical Data Adapter
========================
Loads and converts JSON data from old-data-by-dj folder
to the format used by the analysis system
"""
import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import sys
sys.path.append(str(Path(__file__).parent))
from config import BASE_DIR


# Path to historical data
HISTORICAL_DATA_DIR = BASE_DIR / "old-data-by-dj"

# Symbol name mapping (folder names to standard names)
SYMBOL_MAP = {
    'Nifty': 'NIFTY',
    'Banknifty': 'BANKNIFTY',
    'Finnifty': 'FINNIFTY',
    'midcapnifty': 'MIDCAPNIFTY',
    'NIfty mid select': 'MIDCAPNIFTY',
    'Sensex': 'SENSEX',
}

# Reverse map
FOLDER_MAP = {v: k for k, v in SYMBOL_MAP.items()}


class HistoricalDataLoader:
    """Load and parse historical JSON data"""
    
    def __init__(self, base_path: Path = None):
        self.base_path = base_path or HISTORICAL_DATA_DIR
    
    def get_available_years(self) -> List[int]:
        """Get list of available years"""
        years = []
        for item in self.base_path.iterdir():
            if item.is_dir() and item.name.isdigit():
                years.append(int(item.name))
        return sorted(years)
    
    def get_available_symbols(self, year: int) -> List[str]:
        """Get available symbols for a year"""
        year_path = self.base_path / str(year)
        if not year_path.exists():
            return []
        
        symbols = []
        for item in year_path.iterdir():
            if item.is_dir():
                std_name = SYMBOL_MAP.get(item.name, item.name.upper())
                symbols.append(std_name)
        return sorted(set(symbols))
    
    def get_available_months(self, year: int, symbol: str) -> List[str]:
        """Get available months for a symbol in a year"""
        # Find the correct folder name
        folder_name = None
        year_path = self.base_path / str(year)
        for item in year_path.iterdir():
            if SYMBOL_MAP.get(item.name, item.name.upper()) == symbol:
                folder_name = item.name
                break
        
        if not folder_name:
            return []
        
        symbol_path = year_path / folder_name
        months = []
        for item in symbol_path.iterdir():
            if item.is_dir():
                months.append(item.name)
        return sorted(months)
    
    def get_available_expiry_days(self, year: int, symbol: str, month: str) -> List[int]:
        """Get available expiry days for a month"""
        symbol_path = self._get_symbol_path(year, symbol)
        if not symbol_path:
            return []
        
        month_path = symbol_path / month
        if not month_path.exists():
            return []
        
        days = set()
        for file in month_path.glob("*.json"):
            # Filename format: {day}_{CE/PE}_{strike}.json
            parts = file.stem.split('_')
            if len(parts) >= 3:
                try:
                    days.add(int(parts[0]))
                except ValueError:
                    pass
        return sorted(days)
    
    def _get_symbol_path(self, year: int, symbol: str) -> Optional[Path]:
        """Get the path to symbol folder"""
        year_path = self.base_path / str(year)
        if not year_path.exists():
            return None
        
        for item in year_path.iterdir():
            if SYMBOL_MAP.get(item.name, item.name.upper()) == symbol:
                return item
        return None
    
    def load_strike_data(self, year: int, symbol: str, month: str, 
                         day: int, option_type: str, strike: int) -> pd.DataFrame:
        """
        Load data for a specific strike
        Returns DataFrame with columns: timestamp, open, high, low, close, volume, oi
        """
        symbol_path = self._get_symbol_path(year, symbol)
        if not symbol_path:
            raise FileNotFoundError(f"Symbol {symbol} not found for year {year}")
        
        file_path = symbol_path / month / f"{day}_{option_type}_{strike}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        if data.get('status') != 'success':
            raise ValueError(f"Data status not success: {data.get('status')}")
        
        candles = data.get('data', {}).get('candles', [])
        if not candles:
            return pd.DataFrame()
        
        # Convert to DataFrame
        df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'oi'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        return df
    
    def load_expiry_day_data(self, year: int, symbol: str, month: str, 
                             day: int) -> Dict[str, Dict[int, pd.DataFrame]]:
        """
        Load all strike data for an expiry day
        Returns: {'CE': {strike: df, ...}, 'PE': {strike: df, ...}}
        """
        symbol_path = self._get_symbol_path(year, symbol)
        if not symbol_path:
            return {}
        
        month_path = symbol_path / month
        if not month_path.exists():
            return {}
        
        result = {'CE': {}, 'PE': {}}
        
        for file in month_path.glob(f"{day}_*.json"):
            parts = file.stem.split('_')
            if len(parts) >= 3:
                option_type = parts[1]
                try:
                    strike = int(parts[2])
                except ValueError:
                    continue
                
                try:
                    df = self.load_strike_data(year, symbol, month, day, option_type, strike)
                    if not df.empty:
                        result[option_type][strike] = df
                except Exception as e:
                    print(f"Error loading {file}: {e}")
        
        return result
    
    def get_summary(self) -> pd.DataFrame:
        """Get summary of all available data"""
        rows = []
        
        for year in self.get_available_years():
            for symbol in self.get_available_symbols(year):
                for month in self.get_available_months(year, symbol):
                    expiry_days = self.get_available_expiry_days(year, symbol, month)
                    
                    # Count files per day
                    symbol_path = self._get_symbol_path(year, symbol)
                    month_path = symbol_path / month
                    
                    for day in expiry_days:
                        ce_count = len(list(month_path.glob(f"{day}_CE_*.json")))
                        pe_count = len(list(month_path.glob(f"{day}_PE_*.json")))
                        
                        rows.append({
                            'year': year,
                            'symbol': symbol,
                            'month': month,
                            'expiry_day': day,
                            'ce_strikes': ce_count,
                            'pe_strikes': pe_count,
                        })
        
        return pd.DataFrame(rows)


def convert_to_csv(year: int, symbol: str, month: str, day: int, 
                   output_dir: Path = None) -> Dict[str, Path]:
    """
    Convert JSON data to CSV format compatible with analysis system
    """
    loader = HistoricalDataLoader()
    data = loader.load_expiry_day_data(year, symbol, month, day)
    
    if not output_dir:
        output_dir = HISTORICAL_DATA_DIR / "converted" / symbol / str(year) / month / str(day)
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    saved_files = {}
    
    for option_type in ['CE', 'PE']:
        type_dir = output_dir / option_type
        type_dir.mkdir(exist_ok=True)
        
        for strike, df in data.get(option_type, {}).items():
            file_path = type_dir / f"{strike}.csv"
            df.to_csv(file_path, index=False)
            saved_files[f"{option_type}_{strike}"] = file_path
    
    return saved_files


def get_expiry_dates_for_backtest(symbol: str = 'NIFTY', 
                                   year: int = None) -> List[Tuple[int, str, int]]:
    """
    Get list of (year, month, day) tuples for backtesting
    """
    loader = HistoricalDataLoader()
    result = []
    
    years = [year] if year else loader.get_available_years()
    
    for y in years:
        if symbol not in loader.get_available_symbols(y):
            continue
        
        for month in loader.get_available_months(y, symbol):
            for day in loader.get_available_expiry_days(y, symbol, month):
                result.append((y, month, day))
    
    return result


if __name__ == "__main__":
    # Test the loader
    loader = HistoricalDataLoader()
    
    print("="*60)
    print("HISTORICAL DATA SUMMARY")
    print("="*60)
    
    print("\nAvailable Years:", loader.get_available_years())
    
    for year in loader.get_available_years():
        print(f"\n{year}:")
        for symbol in loader.get_available_symbols(year):
            months = loader.get_available_months(year, symbol)
            total_expiries = sum(
                len(loader.get_available_expiry_days(year, symbol, m)) 
                for m in months
            )
            print(f"  {symbol}: {len(months)} months, {total_expiries} expiry days")
    
    print("\n" + "="*60)
    print("Sample Data Load Test")
    print("="*60)
    
    # Try to load one sample
    try:
        test_data = loader.load_expiry_day_data(2024, 'NIFTY', 'November', 7)
        ce_strikes = len(test_data.get('CE', {}))
        pe_strikes = len(test_data.get('PE', {}))
        print(f"\nNIFTY Nov 7, 2024: {ce_strikes} CE strikes, {pe_strikes} PE strikes")
        
        if test_data['CE']:
            sample_strike = list(test_data['CE'].keys())[0]
            sample_df = test_data['CE'][sample_strike]
            print(f"\nSample CE {sample_strike}:")
            print(f"  Rows: {len(sample_df)}")
            print(f"  Date range: {sample_df['timestamp'].min()} to {sample_df['timestamp'].max()}")
    except Exception as e:
        print(f"Error: {e}")
