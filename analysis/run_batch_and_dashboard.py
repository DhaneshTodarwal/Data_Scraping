#!/usr/bin/env python3
"""
Master Runner Script
=====================
Run batch backtests and generate dashboard with single command

Usage:
    python run_batch_and_dashboard.py
    python run_batch_and_dashboard.py --quick  (limited test)
    python run_batch_and_dashboard.py --symbols NIFTY BANKNIFTY
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backtest.batch_runner import run_batch_backtest
from dashboard.generate_report import generate_dashboard


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Run Batch Backtest + Dashboard')
    parser.add_argument('--symbols', type=str, nargs='+', default=None,
                        help='Symbols to test')
    parser.add_argument('--strategies', type=str, nargs='+', default=None,
                        help='Strategies to test')
    parser.add_argument('--year', type=int, default=2024, help='Year')
    parser.add_argument('--max-days', type=int, default=None, help='Max days per symbol')
    parser.add_argument('--quick', action='store_true', help='Quick test (5 days, 3 strategies)')
    parser.add_argument('--skip-dashboard', action='store_true', help='Skip dashboard generation')
    
    args = parser.parse_args()
    
    # Quick mode for testing
    if args.quick:
        args.max_days = 5
        args.strategies = ['short_straddle', 'short_strangle', 'iron_condor']
    
    print("\n" + "="*70)
    print("           BATCH BACKTEST + DASHBOARD GENERATOR")
    print("="*70)
    
    # Run batch backtest
    results, output_dir = run_batch_backtest(
        symbols=args.symbols,
        strategies=args.strategies,
        year=args.year,
        max_days=args.max_days
    )
    
    # Generate dashboard
    if not args.skip_dashboard and results is not None and not results.empty:
        print("\n📊 Generating Dashboard...")
        try:
            dashboard_path = generate_dashboard()
            print(f"\n🌐 Open dashboard in browser: file://{dashboard_path}")
        except Exception as e:
            print(f"⚠ Dashboard error: {e}")
    
    print("\n✅ Complete!")


if __name__ == "__main__":
    main()
