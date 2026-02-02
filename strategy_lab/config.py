"""
Strategy Lab Configuration
===========================
Isolated configuration for strategy testing.
All paths are READ-ONLY except for reports output.
"""
from pathlib import Path

# Base paths
STRATEGY_LAB_DIR = Path(__file__).parent
PROJECT_ROOT = STRATEGY_LAB_DIR.parent

# DATA PATHS (READ-ONLY)
DATA_DIR = PROJECT_ROOT / "data"
INDEX_OHLCV_DIR = DATA_DIR / "index_ohlcv"
STRIKES_OHLCV_DIR = DATA_DIR / "strikes_ohlcv"

# OUTPUT PATHS (WRITE ONLY - all outputs go here)
REPORTS_DIR = STRATEGY_LAB_DIR / "reports"
COMPARISONS_DIR = STRATEGY_LAB_DIR / "comparisons"

# Ensure output directories exist
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
COMPARISONS_DIR.mkdir(parents=True, exist_ok=True)

# Trading constants
LOT_SIZES = {
    'NIFTY': 25,
    'BANKNIFTY': 15,
    'SENSEX': 10,
}

STRIKE_GAPS = {
    'NIFTY': 50,
    'BANKNIFTY': 100,
    'SENSEX': 100,
}

# Default backtest parameters
DEFAULT_CONFIG = {
    'initial_capital': 100000,  # ₹1 lakh
    'risk_per_trade': 1.0,      # 1% of capital
    'max_daily_loss': 3.0,      # 3% of capital
    'slippage_pct': 0.1,        # 0.1% slippage
    'commission_per_lot': 20,   # ₹20 per lot
}

# Market timing
MARKET_OPEN = "09:15"
MARKET_CLOSE = "15:30"
FIRST_30_MIN_END = "09:45"
LAST_30_MIN_START = "15:00"

# Available symbols
AVAILABLE_SYMBOLS = ['NIFTY', 'BANKNIFTY', 'SENSEX']
