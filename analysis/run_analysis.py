#!/usr/bin/env python3
"""
Main Analysis Runner
Run this script to analyze your collected data

Usage:
    python run_analysis.py --symbol NIFTY --date 2026-01-16
    python run_analysis.py --symbol NIFTY --date 2026-01-16 --backtest
    python run_analysis.py --symbol NIFTY --date 2026-01-16 --filter-style moderate
    python run_analysis.py --symbol NIFTY --date 2026-01-16 --options-buying
    python run_analysis.py --symbol NIFTY --date 2026-01-16 --options-selling
"""
import argparse
import sys
from pathlib import Path

# Add analysis module to path
sys.path.insert(0, str(Path(__file__).parent))

from features.technical import process_date, load_index_data, TechnicalFeatures
from features.options import process_options_date, OptionsFeatures
from strategies.signal_generator import SignalGenerator
from strategies.filter_configs import get_config
from strategies.option_buying.buying_strategies import (
    MomentumBreakoutBuy, TrendFollowingBuy, ORBOptionBuy
)
from strategies.option_selling.selling_strategies import (
    ShortStraddleSell, ShortStrangleSell, IronCondorSell, CreditSpreadSell
)
from backtest.engine import Backtester
from config import FEATURES_OUTPUT, SIGNALS_OUTPUT, BACKTEST_OUTPUT


def run_feature_engineering(symbol: str, date: str) -> tuple:
    """Run feature engineering on index data"""
    print(f"\n📊 Processing {symbol} for {date}...")
    
    # Technical features
    print("  → Generating technical features...")
    features_df = process_date(symbol, date)
    print(f"  ✓ Generated {len(features_df.columns)} technical indicators")
    
    # Options features
    print("  → Generating options features...")
    try:
        options_df = process_options_date(symbol, date)
        print(f"  ✓ Generated {len(options_df)} options snapshots")
    except Exception as e:
        print(f"  ⚠ Options data not available: {e}")
        options_df = None
    
    return features_df, options_df


def run_signal_generation(features_df, symbol: str, date: str, filter_style: str = 'moderate'):
    """Generate trading signals with configurable filters"""
    print(f"\n🎯 Generating signals (filter: {filter_style})...")
    
    config = get_config(filter_style)
    generator = SignalGenerator(features_df, config)
    
    # Run multiple strategies
    generator.ema_crossover_signal(9, 21)
    generator.ema_crossover_signal(9, 15)  # Additional EMA pair
    generator.rsi_reversal_signal(35, 65)  # More relaxed RSI
    generator.bollinger_breakout_signal()
    
    signals_df = generator.to_dataframe()
    print(f"  ✓ Generated {len(signals_df)} signals")
    
    # Save signals
    if not signals_df.empty:
        generator.save_signals(f'{symbol}_{date}_signals.csv')
        print(f"  ✓ Saved to {SIGNALS_OUTPUT}")
    
    return signals_df


def run_options_buying_strategies(features_df, symbol: str, date: str):
    """Run option buying strategies"""
    print(f"\n📈 Running Option BUYING Strategies...")
    
    all_signals = []
    
    # 1. Momentum Breakout
    print("  → Momentum Breakout...")
    momentum = MomentumBreakoutBuy(features_df)
    momentum.generate_signals()
    momentum_df = momentum.to_dataframe()
    print(f"    ✓ {len(momentum_df)} signals")
    if not momentum_df.empty:
        momentum_df['strategy'] = 'Momentum Breakout'
        all_signals.append(momentum_df)
    
    # 2. Trend Following
    print("  → Trend Following...")
    trend = TrendFollowingBuy(features_df)
    trend.generate_signals()
    trend_df = trend.to_dataframe()
    print(f"    ✓ {len(trend_df)} signals")
    if not trend_df.empty:
        trend_df['strategy'] = 'Trend Following'
        all_signals.append(trend_df)
    
    # 3. ORB (Opening Range Breakout)
    print("  → Opening Range Breakout...")
    orb = ORBOptionBuy(features_df)
    orb.generate_signals()
    orb_df = orb.to_dataframe()
    print(f"    ✓ {len(orb_df)} signals")
    if not orb_df.empty:
        orb_df['strategy'] = 'ORB'
        all_signals.append(orb_df)
    
    # Combine and save
    if all_signals:
        import pandas as pd
        combined = pd.concat(all_signals, ignore_index=True)
        output_path = SIGNALS_OUTPUT / f'{symbol}_{date}_option_buying.csv'
        combined.to_csv(output_path, index=False)
        print(f"\n  ✓ Total: {len(combined)} option buying signals saved")
        return combined
    
    return None


def run_options_selling_strategies(features_df, symbol: str, date: str):
    """Run option selling strategies"""
    print(f"\n📉 Running Option SELLING Strategies...")
    
    all_signals = []
    
    # 1. Short Straddle
    print("  → Short Straddle...")
    straddle = ShortStraddleSell(features_df)
    straddle.generate_signals()
    straddle_df = straddle.to_dataframe()
    print(f"    ✓ {len(straddle_df)} signals")
    if not straddle_df.empty:
        all_signals.append(straddle_df)
    
    # 2. Short Strangle
    print("  → Short Strangle...")
    strangle = ShortStrangleSell(features_df)
    strangle.generate_signals()
    strangle_df = strangle.to_dataframe()
    print(f"    ✓ {len(strangle_df)} signals")
    if not strangle_df.empty:
        all_signals.append(strangle_df)
    
    # 3. Iron Condor
    print("  → Iron Condor...")
    condor = IronCondorSell(features_df)
    condor.generate_signals()
    condor_df = condor.to_dataframe()
    print(f"    ✓ {len(condor_df)} signals")
    if not condor_df.empty:
        all_signals.append(condor_df)
    
    # 4. Credit Spread
    print("  → Credit Spread...")
    spread = CreditSpreadSell(features_df)
    spread.generate_signals()
    spread_df = spread.to_dataframe()
    print(f"    ✓ {len(spread_df)} signals")
    if not spread_df.empty:
        all_signals.append(spread_df)
    
    # Combine and save
    if all_signals:
        import pandas as pd
        combined = pd.concat(all_signals, ignore_index=True)
        output_path = SIGNALS_OUTPUT / f'{symbol}_{date}_option_selling.csv'
        combined.to_csv(output_path, index=False)
        print(f"\n  ✓ Total: {len(combined)} option selling signals saved")
        return combined
    
    return None


def run_backtest(signals_df, prices_df, symbol: str, date: str):
    """Run backtest on signals"""
    print(f"\n🧪 Running backtest...")
    
    if signals_df is None or signals_df.empty:
        print("  ⚠ No signals to backtest")
        return None
    
    backtester = Backtester(signals_df, prices_df, symbol=symbol)
    result = backtester.run()
    
    # Print report
    print(backtester.generate_report(result))
    
    # Save results
    backtester.save_results(result, f'{symbol}_{date}')
    print(f"  ✓ Results saved to {BACKTEST_OUTPUT}")
    
    return result


def main():
    parser = argparse.ArgumentParser(description='Analyze trading data')
    parser.add_argument('--symbol', type=str, default='NIFTY', 
                        help='Symbol to analyze (NIFTY or BANKNIFTY)')
    parser.add_argument('--date', type=str, required=True,
                        help='Date to analyze (YYYY-MM-DD)')
    parser.add_argument('--backtest', action='store_true',
                        help='Run backtest on generated signals')
    parser.add_argument('--features-only', action='store_true',
                        help='Only generate features, skip signals')
    parser.add_argument('--filter-style', type=str, default='moderate',
                        choices=['strict', 'moderate', 'relaxed', 'scalping', 'swing'],
                        help='Filter strictness level')
    parser.add_argument('--options-buying', action='store_true',
                        help='Run option buying strategies')
    parser.add_argument('--options-selling', action='store_true',
                        help='Run option selling strategies')
    parser.add_argument('--all-strategies', action='store_true',
                        help='Run all strategy types')
    
    args = parser.parse_args()
    
    print("="*60)
    print("         PROFESSIONAL TRADING ANALYSIS")
    print("="*60)
    print(f"Symbol: {args.symbol}")
    print(f"Date:   {args.date}")
    print(f"Filter: {args.filter_style}")
    print("="*60)
    
    try:
        # Step 1: Feature Engineering
        features_df, options_df = run_feature_engineering(args.symbol, args.date)
        
        if args.features_only:
            print("\n✅ Feature engineering complete!")
            return
        
        # Step 2: Signal Generation (base signals)
        signals_df = run_signal_generation(features_df, args.symbol, args.date, args.filter_style)
        
        # Step 3: Options Strategies
        if args.all_strategies or args.options_buying:
            run_options_buying_strategies(features_df, args.symbol, args.date)
        
        if args.all_strategies or args.options_selling:
            run_options_selling_strategies(features_df, args.symbol, args.date)
        
        # Step 4: Backtesting (optional)
        if args.backtest and signals_df is not None and not signals_df.empty:
            prices_df = load_index_data(
                args.symbol, 
                int(args.date.split('-')[0]),
                {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                 7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}[int(args.date.split('-')[1])],
                args.date
            )
            run_backtest(signals_df, prices_df, args.symbol, args.date)
        
        print("\n✅ Analysis complete!")
        
    except FileNotFoundError as e:
        print(f"\n❌ Error: {e}")
        print("Make sure you have data collected for this date.")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
