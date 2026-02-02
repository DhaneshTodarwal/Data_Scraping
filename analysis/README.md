# Analysis Module

A completely separate module for analyzing collected NIFTY/BANKNIFTY data.

## Structure

```
analysis/
├── __init__.py
├── config.py           # Configuration and paths
├── features/           # Feature engineering
│   ├── __init__.py
│   ├── technical.py    # Technical indicators
│   └── options.py      # Options-specific features
├── strategies/         # Trading strategies
│   └── __init__.py
├── backtest/           # Backtesting engine
│   └── __init__.py
└── output/             # Analysis results (gitignored)
```

## Important

This module ONLY READS from the `data/` folder.
It NEVER modifies any existing files or scripts.
