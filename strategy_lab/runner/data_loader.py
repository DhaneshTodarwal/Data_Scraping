"""
Data Loader for Strategy Lab
==============================
READ-ONLY access to historical data.
Never modifies source files.
"""
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import sys

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import INDEX_OHLCV_DIR, STRIKES_OHLCV_DIR, AVAILABLE_SYMBOLS


class DataLoader:
    """
    Read-only data loader for backtesting.
    Loads index OHLCV and options strike data.
    """
    
    def __init__(self):
        self.index_dir = INDEX_OHLCV_DIR
        self.strikes_dir = STRIKES_OHLCV_DIR
    
    def get_available_dates(self, symbol: str) -> List[str]:
        """Get all available trading dates for a symbol."""
        dates = []
        
        # Check index data
        for year_dir in sorted(self.index_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                symbol_dir = month_dir / symbol
                if symbol_dir.exists():
                    for csv_file in sorted(symbol_dir.glob("*.csv")):
                        date_str = csv_file.stem  # e.g., "2026-01-16"
                        dates.append(date_str)
        
        return sorted(dates)
    
    def get_available_expiry_dates(self, symbol: str) -> List[Tuple[int, str, int]]:
        """Get all available expiry dates with options data."""
        expiry_dates = []
        
        symbol_dir = self.strikes_dir / symbol
        if not symbol_dir.exists():
            return []
        
        for year_dir in sorted(symbol_dir.iterdir()):
            if not year_dir.is_dir():
                continue
            year = int(year_dir.name)
            
            for month_dir in sorted(year_dir.iterdir()):
                if not month_dir.is_dir():
                    continue
                month = month_dir.name  # e.g., "01_January"
                
                for day_dir in sorted(month_dir.iterdir()):
                    if not day_dir.is_dir():
                        continue
                    day = int(day_dir.name)
                    expiry_dates.append((year, month, day))
        
        return expiry_dates
    
    def load_index_data(self, symbol: str, date: str) -> Optional[pd.DataFrame]:
        """
        Load index OHLCV data for a specific date.
        Returns DataFrame with columns: timestamp, open, high, low, close, volume
        """
        # Parse date to find correct path
        dt = datetime.strptime(date, "%Y-%m-%d")
        year = dt.year
        month = dt.strftime("%b")  # "Jan", "Feb", etc.
        
        file_path = self.index_dir / str(year) / month / symbol / f"{date}.csv"
        
        if not file_path.exists():
            print(f"⚠️ Index data not found: {file_path}")
            return None
        
        df = pd.read_csv(file_path)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        return df
    
    def load_strikes_data(self, symbol: str, year: int, month: str, day: int) -> Dict[str, Dict[int, pd.DataFrame]]:
        """
        Load all strike data for a specific expiry day.
        Returns: {'CE': {strike: df, ...}, 'PE': {strike: df, ...}}
        """
        result = {'CE': {}, 'PE': {}}
        
        base_dir = self.strikes_dir / symbol / str(year) / month / str(day)
        
        if not base_dir.exists():
            print(f"⚠️ Strikes data not found: {base_dir}")
            return result
        
        for option_type in ['CE', 'PE']:
            type_dir = base_dir / option_type
            if not type_dir.exists():
                continue
            
            for csv_file in sorted(type_dir.glob("*.csv")):
                try:
                    strike = int(csv_file.stem)  # e.g., "25400" -> 25400
                    df = pd.read_csv(csv_file)
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    result[option_type][strike] = df
                except (ValueError, Exception) as e:
                    print(f"⚠️ Error loading {csv_file}: {e}")
        
        return result
    
    def load_all_index_data(self, symbol: str) -> pd.DataFrame:
        """Load all available index data for a symbol, concatenated."""
        dates = self.get_available_dates(symbol)
        
        all_dfs = []
        for date in dates:
            df = self.load_index_data(symbol, date)
            if df is not None and not df.empty:
                df['date'] = date
                all_dfs.append(df)
        
        if not all_dfs:
            return pd.DataFrame()
        
        return pd.concat(all_dfs, ignore_index=True).sort_values('timestamp')
    
    def get_atm_strike(self, spot_price: float, symbol: str = 'NIFTY') -> int:
        """Calculate ATM strike for given spot price."""
        from config import STRIKE_GAPS
        gap = STRIKE_GAPS.get(symbol, 50)
        return round(spot_price / gap) * gap
    
    def print_data_summary(self):
        """Print summary of available data."""
        print("\n" + "="*60)
        print("📊 AVAILABLE DATA SUMMARY")
        print("="*60)
        
        for symbol in AVAILABLE_SYMBOLS:
            dates = self.get_available_dates(symbol)
            expiries = self.get_available_expiry_dates(symbol)
            
            print(f"\n{symbol}:")
            print(f"  Index Data: {len(dates)} days")
            if dates:
                print(f"    Range: {dates[0]} to {dates[-1]}")
            print(f"  Options Data: {len(expiries)} expiry days")
        
        print("\n" + "="*60)


if __name__ == "__main__":
    # Test data loader
    loader = DataLoader()
    loader.print_data_summary()
