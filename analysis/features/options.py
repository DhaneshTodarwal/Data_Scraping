"""
Options-Specific Features
Reads options data from ../data/strikes_ohlcv/ and generates options metrics
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from scipy.stats import norm
import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import STRIKES_OHLCV_DIR, INDEX_OHLCV_DIR, FEATURES_OUTPUT


class OptionsFeatures:
    """Generate options-specific features from strikes data"""
    
    def __init__(self, symbol: str, date: str):
        """
        Initialize with symbol and date
        symbol: 'NIFTY' or 'BANKNIFTY'
        date: 'YYYY-MM-DD' format
        """
        self.symbol = symbol
        self.date = date
        self.spot_data = None
        self.ce_data = {}
        self.pe_data = {}
        self._load_data()
    
    def _parse_date_path(self) -> Path:
        """Convert date to directory path"""
        parts = self.date.split('-')
        year = parts[0]
        month = int(parts[1])
        day = parts[2]
        month_map = {1: '01_January', 2: '02_February', 3: '03_March', 
                     4: '04_April', 5: '05_May', 6: '06_June',
                     7: '07_July', 8: '08_August', 9: '09_September',
                     10: '10_October', 11: '11_November', 12: '12_December'}
        return STRIKES_OHLCV_DIR / self.symbol / year / month_map[month] / day
    
    def _load_data(self):
        """Load all strike data for the date"""
        base_path = self._parse_date_path()
        
        # Load CE strikes
        ce_path = base_path / "CE"
        if ce_path.exists():
            for csv_file in ce_path.glob("*.csv"):
                strike = int(csv_file.stem)
                self.ce_data[strike] = pd.read_csv(csv_file)
                self.ce_data[strike]['timestamp'] = pd.to_datetime(
                    self.ce_data[strike]['timestamp']
                )
        
        # Load PE strikes
        pe_path = base_path / "PE"
        if pe_path.exists():
            for csv_file in pe_path.glob("*.csv"):
                strike = int(csv_file.stem)
                self.pe_data[strike] = pd.read_csv(csv_file)
                self.pe_data[strike]['timestamp'] = pd.to_datetime(
                    self.pe_data[strike]['timestamp']
                )
        
        # Load spot data
        self._load_spot_data()
    
    def _load_spot_data(self):
        """Load underlying index data"""
        parts = self.date.split('-')
        year = int(parts[0])
        month_num = int(parts[1])
        month_map = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
                     7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
        month = month_map[month_num]
        
        spot_path = INDEX_OHLCV_DIR / str(year) / month / self.symbol / f"{self.date}.csv"
        if spot_path.exists():
            self.spot_data = pd.read_csv(spot_path)
            self.spot_data['timestamp'] = pd.to_datetime(self.spot_data['timestamp'])
    
    def get_available_strikes(self) -> Dict[str, List[int]]:
        """Get all available strikes"""
        return {
            'CE': sorted(self.ce_data.keys()),
            'PE': sorted(self.pe_data.keys())
        }
    
    def get_atm_strike(self, spot_price: float) -> int:
        """Find ATM strike for given spot price"""
        all_strikes = set(self.ce_data.keys()) | set(self.pe_data.keys())
        if not all_strikes:
            return int(round(spot_price / 50) * 50)  # Round to nearest 50
        return min(all_strikes, key=lambda x: abs(x - spot_price))
    
    # ============== PREMIUM FEATURES ==============
    
    def straddle_premium(self, strike: int, timestamp: Optional[pd.Timestamp] = None) -> float:
        """Calculate straddle premium at a strike"""
        ce_premium = self._get_premium(strike, 'CE', timestamp)
        pe_premium = self._get_premium(strike, 'PE', timestamp)
        return ce_premium + pe_premium
    
    def strangle_premium(self, ce_strike: int, pe_strike: int, 
                         timestamp: Optional[pd.Timestamp] = None) -> float:
        """Calculate strangle premium"""
        ce_premium = self._get_premium(ce_strike, 'CE', timestamp)
        pe_premium = self._get_premium(pe_strike, 'PE', timestamp)
        return ce_premium + pe_premium
    
    def _get_premium(self, strike: int, option_type: str, 
                     timestamp: Optional[pd.Timestamp] = None) -> float:
        """Get option premium at specific time"""
        data = self.ce_data if option_type == 'CE' else self.pe_data
        if strike not in data:
            return 0.0
        
        df = data[strike]
        if timestamp:
            row = df[df['timestamp'] == timestamp]
            if not row.empty:
                return row['close'].iloc[0]
        
        # Return last close if no timestamp specified
        return df['close'].iloc[-1] if not df.empty else 0.0
    
    # ============== VOLATILITY FEATURES ==============
    
    def implied_move(self, timestamp: Optional[pd.Timestamp] = None) -> float:
        """
        Calculate expected move based on ATM straddle premium
        Rule of thumb: Straddle price ≈ Expected 1 SD move
        """
        if self.spot_data is None:
            return 0.0
        
        if timestamp:
            spot_row = self.spot_data[self.spot_data['timestamp'] == timestamp]
            spot = spot_row['close'].iloc[0] if not spot_row.empty else None
        else:
            spot = self.spot_data['close'].iloc[-1]
        
        if spot is None:
            return 0.0
        
        atm = self.get_atm_strike(spot)
        straddle = self.straddle_premium(atm, timestamp)
        
        return (straddle / spot) * 100  # As percentage
    
    def put_call_ratio(self, timestamp: Optional[pd.Timestamp] = None) -> float:
        """Calculate Put-Call ratio based on volume"""
        ce_volume = 0
        pe_volume = 0
        
        for strike, df in self.ce_data.items():
            if timestamp:
                row = df[df['timestamp'] == timestamp]
                ce_volume += row['volume'].iloc[0] if not row.empty else 0
            else:
                ce_volume += df['volume'].sum()
        
        for strike, df in self.pe_data.items():
            if timestamp:
                row = df[df['timestamp'] == timestamp]
                pe_volume += row['volume'].iloc[0] if not row.empty else 0
            else:
                pe_volume += df['volume'].sum()
        
        return pe_volume / ce_volume if ce_volume > 0 else 0.0
    
    # ============== GREEKS APPROXIMATION ==============
    
    @staticmethod
    def black_scholes_delta(spot: float, strike: float, time_to_expiry: float,
                            volatility: float, risk_free_rate: float = 0.05,
                            option_type: str = 'CE') -> float:
        """
        Calculate Delta using Black-Scholes
        time_to_expiry: in years (e.g., 7 days = 7/365)
        volatility: annualized (e.g., 0.15 for 15%)
        """
        if time_to_expiry <= 0 or volatility <= 0:
            return 0.0
        
        d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * volatility**2) * time_to_expiry) / \
             (volatility * np.sqrt(time_to_expiry))
        
        if option_type == 'CE':
            return norm.cdf(d1)
        else:
            return norm.cdf(d1) - 1
    
    @staticmethod
    def estimate_iv(option_price: float, spot: float, strike: float,
                    time_to_expiry: float, risk_free_rate: float = 0.05,
                    option_type: str = 'CE') -> float:
        """
        Estimate Implied Volatility using Newton-Raphson method
        """
        if option_price <= 0 or spot <= 0 or time_to_expiry <= 0:
            return 0.0
        
        # Initial guess
        iv = 0.20
        
        for _ in range(100):
            # Calculate BS price
            d1 = (np.log(spot / strike) + (risk_free_rate + 0.5 * iv**2) * time_to_expiry) / \
                 (iv * np.sqrt(time_to_expiry))
            d2 = d1 - iv * np.sqrt(time_to_expiry)
            
            if option_type == 'CE':
                bs_price = spot * norm.cdf(d1) - strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
            else:
                bs_price = strike * np.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)
            
            # Vega
            vega = spot * norm.pdf(d1) * np.sqrt(time_to_expiry)
            
            if abs(vega) < 1e-10:
                break
            
            # Newton-Raphson update
            diff = option_price - bs_price
            if abs(diff) < 0.01:
                break
            
            iv = iv + diff / vega
            iv = max(0.01, min(iv, 5.0))  # Clamp between 1% and 500%
        
        return iv
    
    # ============== GENERATE FEATURES ==============
    
    def generate_options_features(self) -> pd.DataFrame:
        """Generate time-series of options features"""
        if self.spot_data is None:
            return pd.DataFrame()
        
        results = []
        
        for _, row in self.spot_data.iterrows():
            ts = row['timestamp']
            spot = row['close']
            atm = self.get_atm_strike(spot)
            
            features = {
                'timestamp': ts,
                'spot': spot,
                'atm_strike': atm,
                'atm_ce_premium': self._get_premium(atm, 'CE', ts),
                'atm_pe_premium': self._get_premium(atm, 'PE', ts),
                'straddle_premium': self.straddle_premium(atm, ts),
                'implied_move_pct': self.implied_move(ts),
                'pcr': self.put_call_ratio(ts),
            }
            results.append(features)
        
        return pd.DataFrame(results)
    
    def save_features(self, df: pd.DataFrame):
        """Save features to output directory"""
        output_path = FEATURES_OUTPUT / self.symbol / "options"
        output_path.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path / f"{self.date}_options_features.csv", index=False)


def process_options_date(symbol: str, date: str) -> pd.DataFrame:
    """Process options data for a date and generate features"""
    options = OptionsFeatures(symbol, date)
    df = options.generate_options_features()
    options.save_features(df)
    return df


if __name__ == "__main__":
    # Example usage
    try:
        df = process_options_date('NIFTY', '2026-01-16')
        print(f"Generated options features: {len(df)} rows")
        print(df.head())
    except Exception as e:
        print(f"Error: {e}")
