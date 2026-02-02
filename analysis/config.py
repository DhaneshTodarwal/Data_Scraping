"""
Configuration for analysis module
All paths point to reading from existing data, output goes to analysis/output/
"""
import os
from pathlib import Path

# Base paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
OUTPUT_DIR = Path(__file__).parent / "output"

# Data source paths (READ ONLY)
INDEX_OHLCV_DIR = DATA_DIR / "index_ohlcv"
STRIKES_OHLCV_DIR = DATA_DIR / "strikes_ohlcv"
OPTIONS_DATA_DIR = BASE_DIR / "options_data"

# Output paths (WRITE ONLY)
FEATURES_OUTPUT = OUTPUT_DIR / "features"
SIGNALS_OUTPUT = OUTPUT_DIR / "signals"
BACKTEST_OUTPUT = OUTPUT_DIR / "backtest"

# Ensure output directories exist
for d in [OUTPUT_DIR, FEATURES_OUTPUT, SIGNALS_OUTPUT, BACKTEST_OUTPUT]:
    d.mkdir(parents=True, exist_ok=True)

# Trading constants
NIFTY_LOT_SIZE = 25
BANKNIFTY_LOT_SIZE = 15

# Market timing
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
FIRST_30_MIN_END = "09:45"
LAST_30_MIN_START = "15:00"

# Default risk parameters
DEFAULT_RISK_PER_TRADE = 1.0  # 1% of capital
DEFAULT_MAX_DAILY_LOSS = 2.0  # 2% of capital
DEFAULT_MAX_DRAWDOWN = 15.0   # 15% of capital
