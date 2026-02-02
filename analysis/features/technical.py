"""
Technical Indicators & Feature Engineering
Reads from ../data/ and generates features for analysis
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict
import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import INDEX_OHLCV_DIR, FEATURES_OUTPUT


class TechnicalFeatures:
    """Generate technical indicators from OHLCV data"""
    
    def __init__(self, df: pd.DataFrame):
        """
        Initialize with OHLCV dataframe
        Expected columns: timestamp, open, high, low, close, volume
        """
        self.df = df.copy()
        self._prepare_data()
    
    def _prepare_data(self):
        """Parse timestamp and set as index"""
        if 'timestamp' in self.df.columns:
            self.df['timestamp'] = pd.to_datetime(self.df['timestamp'])
            self.df.set_index('timestamp', inplace=True)
    
    # ============== TREND INDICATORS ==============
    
    def sma(self, period: int, column: str = 'close') -> pd.Series:
        """Simple Moving Average"""
        return self.df[column].rolling(window=period).mean()
    
    def ema(self, period: int, column: str = 'close') -> pd.Series:
        """Exponential Moving Average"""
        return self.df[column].ewm(span=period, adjust=False).mean()
    
    def add_moving_averages(self, periods: List[int] = [9, 20, 50, 200]):
        """Add multiple SMAs and EMAs"""
        for p in periods:
            self.df[f'sma_{p}'] = self.sma(p)
            self.df[f'ema_{p}'] = self.ema(p)
        return self
    
    def trend_direction(self, fast: int = 9, slow: int = 21) -> pd.Series:
        """
        Returns: 1 (uptrend), -1 (downtrend), 0 (neutral)
        """
        fast_ema = self.ema(fast)
        slow_ema = self.ema(slow)
        return np.sign(fast_ema - slow_ema)
    
    # ============== VOLATILITY INDICATORS ==============
    
    def atr(self, period: int = 14) -> pd.Series:
        """Average True Range"""
        high = self.df['high']
        low = self.df['low']
        close = self.df['close']
        
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    def atr_percent(self, period: int = 14) -> pd.Series:
        """ATR as percentage of price"""
        return (self.atr(period) / self.df['close']) * 100
    
    def bollinger_bands(self, period: int = 20, std_dev: float = 2.0):
        """Bollinger Bands"""
        sma = self.sma(period)
        std = self.df['close'].rolling(window=period).std()
        
        self.df['bb_upper'] = sma + (std * std_dev)
        self.df['bb_middle'] = sma
        self.df['bb_lower'] = sma - (std * std_dev)
        self.df['bb_width'] = (self.df['bb_upper'] - self.df['bb_lower']) / self.df['bb_middle']
        return self
    
    # ============== MOMENTUM INDICATORS ==============
    
    def rsi(self, period: int = 14) -> pd.Series:
        """Relative Strength Index"""
        delta = self.df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def macd(self, fast: int = 12, slow: int = 26, signal: int = 9):
        """MACD indicator"""
        fast_ema = self.ema(fast)
        slow_ema = self.ema(slow)
        
        self.df['macd_line'] = fast_ema - slow_ema
        self.df['macd_signal'] = self.df['macd_line'].ewm(span=signal, adjust=False).mean()
        self.df['macd_histogram'] = self.df['macd_line'] - self.df['macd_signal']
        return self
    
    def stochastic(self, k_period: int = 14, d_period: int = 3):
        """Stochastic Oscillator"""
        low_min = self.df['low'].rolling(window=k_period).min()
        high_max = self.df['high'].rolling(window=k_period).max()
        
        self.df['stoch_k'] = 100 * (self.df['close'] - low_min) / (high_max - low_min)
        self.df['stoch_d'] = self.df['stoch_k'].rolling(window=d_period).mean()
        return self
    
    # ============== VOLUME INDICATORS ==============
    
    def volume_ratio(self, period: int = 20) -> pd.Series:
        """Volume relative to average"""
        avg_volume = self.df['volume'].rolling(window=period).mean()
        return self.df['volume'] / avg_volume
    
    def vwap(self) -> pd.Series:
        """Volume Weighted Average Price (intraday)"""
        typical_price = (self.df['high'] + self.df['low'] + self.df['close']) / 3
        return (typical_price * self.df['volume']).cumsum() / self.df['volume'].cumsum()
    
    # ============== SUPPORT/RESISTANCE ==============
    
    def pivot_points(self):
        """Standard Pivot Points (daily)"""
        pivot = (self.df['high'] + self.df['low'] + self.df['close']) / 3
        
        self.df['pivot'] = pivot
        self.df['r1'] = 2 * pivot - self.df['low']
        self.df['s1'] = 2 * pivot - self.df['high']
        self.df['r2'] = pivot + (self.df['high'] - self.df['low'])
        self.df['s2'] = pivot - (self.df['high'] - self.df['low'])
        return self
    
    # ============== CANDLE PATTERNS ==============
    
    def candle_body_size(self) -> pd.Series:
        """Candle body as % of range"""
        body = abs(self.df['close'] - self.df['open'])
        range_size = self.df['high'] - self.df['low']
        return body / range_size.replace(0, np.nan)
    
    def is_bullish_candle(self) -> pd.Series:
        """Returns True if close > open"""
        return self.df['close'] > self.df['open']
    
    def is_doji(self, threshold: float = 0.1) -> pd.Series:
        """Doji candle detection"""
        return self.candle_body_size() < threshold
    
    # ============== GENERATE ALL FEATURES ==============
    
    def generate_all(self) -> pd.DataFrame:
        """Generate comprehensive feature set"""
        # Add all indicators
        self.add_moving_averages([9, 15, 20, 50])
        self.bollinger_bands()
        self.macd()
        self.stochastic()
        self.pivot_points()
        
        # Add series features
        self.df['atr'] = self.atr()
        self.df['atr_pct'] = self.atr_percent()
        self.df['rsi'] = self.rsi()
        self.df['trend'] = self.trend_direction()
        self.df['volume_ratio'] = self.volume_ratio()
        self.df['vwap'] = self.vwap()
        self.df['body_size'] = self.candle_body_size()
        self.df['is_bullish'] = self.is_bullish_candle()
        
        return self.df


def load_index_data(symbol: str, year: int, month: str, date: str) -> pd.DataFrame:
    """
    Load index OHLCV data
    Example: load_index_data('NIFTY', 2026, 'Jan', '2026-01-16')
    """
    file_path = INDEX_OHLCV_DIR / str(year) / month / symbol / f"{date}.csv"
    if file_path.exists():
        return pd.read_csv(file_path)
    else:
        raise FileNotFoundError(f"Data not found: {file_path}")


def process_date(symbol: str, date: str) -> pd.DataFrame:
    """
    Process a single date and generate features
    Returns DataFrame with all technical indicators
    """
    # Parse date to get year and month
    parts = date.split('-')
    year = int(parts[0])
    month_num = int(parts[1])
    month_map = {1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun',
                 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec'}
    month = month_map[month_num]
    
    # Load data
    df = load_index_data(symbol, year, month, date)
    
    # Generate features
    features = TechnicalFeatures(df)
    result = features.generate_all()
    
    # Save to output
    output_path = FEATURES_OUTPUT / symbol / str(year)
    output_path.mkdir(parents=True, exist_ok=True)
    result.to_csv(output_path / f"{date}_features.csv")
    
    return result


if __name__ == "__main__":
    # Example usage
    try:
        df = process_date('NIFTY', '2026-01-16')
        print(f"Generated features: {len(df)} rows, {len(df.columns)} columns")
        print(f"Columns: {list(df.columns)}")
    except FileNotFoundError as e:
        print(f"Error: {e}")
