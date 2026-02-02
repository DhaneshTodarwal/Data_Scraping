# Strategy Lab - Isolated Strategy Testing Framework

A completely **isolated** environment for testing trading strategies without affecting your existing data collection system.

## 🔒 Safety Guarantee

- ✅ All writes go ONLY to `strategy_lab/reports/`
- ✅ Data directory is accessed **READ-ONLY**
- ✅ No modifications to `analysis/`, `scripts/`, or `data/`
- ✅ Independent Python modules with no shared state

## 📁 Structure

```
strategy_lab/
├── README.md              # This file
├── config.py              # Lab configuration
├── run_backtest.py        # Main entry point
├── run_gamma_strategy.py  # Gamma-EMA strategy runner
├── strategies/            # Custom strategies
│   ├── base_strategy.py   # Strategy template
│   └── gamma_ema_confluence.py  # Gamma-EMA strategy
├── runner/                # Execution engine
│   ├── data_loader.py     # Read-only data loader
│   ├── backtest_engine.py # Backtesting logic
│   └── gamma_backtest_engine.py # Advanced backtest
├── reports/               # Generated reports (auto-created)
└── comparisons/           # Strategy comparison reports
```

## 🚀 Quick Start

```bash
# Run Gamma-EMA strategy on NIFTY
python3 run_gamma_strategy.py --symbol NIFTY

# Run on SENSEX
python3 run_gamma_strategy.py --symbol SENSEX

# Run on all supported symbols
python3 run_gamma_strategy.py --symbol all
```

## 📊 Available Data

| Symbol | Days Available | Date Range |
|--------|---------------|------------|
| NIFTY | 8 expiry days | Jan 16-29, 2026 |
| BANKNIFTY | 8+ days | Jan 16-29, 2026 |
| SENSEX | 2 days | Jan 27, 29, 2026 |
