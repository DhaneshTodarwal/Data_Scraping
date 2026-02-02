#!/usr/bin/env python3
"""
Compare Different RR Ratios
============================
Tests multiple configurations to find optimal parameters.
"""
import sys
from pathlib import Path
from datetime import datetime
import json
import pandas as pd

STRATEGY_LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(STRATEGY_LAB_DIR))

from config import REPORTS_DIR
from runner.data_loader import DataLoader
from runner.gamma_backtest_engine import GammaBacktestEngine
from strategies.gamma_ema_v2 import GammaEMAConfluenceV2


def test_config(symbol: str, config_name: str, sl_pct: float, target_pct: float, 
                entry_start: str = '11:00', sideways_mins: int = 10):
    """Test a specific configuration."""
    
    loader = DataLoader()
    expiry_dates = loader.get_available_expiry_dates(symbol)
    
    if not expiry_dates:
        return None
    
    # Create strategy with custom config
    strategy = GammaEMAConfluenceV2({
        'stop_loss_pct': sl_pct,
        'target_pct': target_pct,
        'entry_time_start': entry_start,
        'sideways_exit_minutes': sideways_mins,
    })
    
    all_trades = []
    total_signals = 0
    
    for year, month, day in expiry_dates:
        month_num = int(month.split('_')[0]) if '_' in month else 1
        index_date = f"{year}-{month_num:02d}-{day:02d}"
        
        index_df = loader.load_index_data(symbol, index_date)
        if index_df is None or index_df.empty:
            continue
        
        strikes_data = loader.load_strikes_data(symbol, year, month, day)
        if not strikes_data['CE'] and not strikes_data['PE']:
            continue
        
        signals = strategy.generate_signals(index_df, strikes_data, symbol)
        total_signals += len(signals)
        
        if not signals:
            continue
        
        engine_config = {
            'initial_capital': 100000,
            'stop_loss_pct': sl_pct,
            'target_pct': target_pct,
            'trail_start_rr': 1.5,
            'breakeven_trigger': 50,
            'sideways_exit_minutes': sideways_mins,
        }
        
        engine = GammaBacktestEngine(symbol, engine_config)
        result = engine.run(signals, strikes_data)
        all_trades.extend(result.get('trades', []))
    
    if not all_trades:
        return None
    
    df = pd.DataFrame(all_trades)
    
    winners = df[df['pnl'] > 0]
    
    return {
        'config': config_name,
        'sl_pct': sl_pct,
        'target_pct': target_pct,
        'rr_ratio': target_pct / sl_pct,
        'total_signals': total_signals,
        'total_trades': len(df),
        'winners': len(winners),
        'losers': len(df) - len(winners),
        'win_rate': len(winners) / len(df) * 100,
        'total_pnl': df['pnl'].sum(),
        'avg_pnl': df['pnl'].mean(),
        'max_win': df['pnl'].max(),
        'max_loss': df['pnl'].min(),
        'profit_factor': abs(winners['pnl'].sum() / df[df['pnl'] < 0]['pnl'].sum()) if len(df[df['pnl'] < 0]) > 0 else float('inf'),
    }


def main():
    symbol = 'NIFTY'
    
    print(f"\n{'='*80}")
    print(f"   🔬 GAMMA-EMA STRATEGY OPTIMIZATION - TESTING MULTIPLE RR CONFIGURATIONS")
    print(f"{'='*80}\n")
    
    # Test different configurations
    configs = [
        # (name, sl%, target%)
        ('Original (25%SL / 1:4 RR)', 25, 100),
        ('V2 (35%SL / 1:2 RR)', 35, 70),
        ('Conservative (30%SL / 1:1.5 RR)', 30, 45),
        ('Moderate (35%SL / 1:1 RR)', 35, 35),
        ('Aggressive (25%SL / 1:3 RR)', 25, 75),
        ('Tight SL (20%SL / 1:2 RR)', 20, 40),
        ('Wide SL (40%SL / 1:2 RR)', 40, 80),
    ]
    
    results = []
    
    for name, sl, target in configs:
        print(f"Testing: {name}...", end=" ", flush=True)
        result = test_config(symbol, name, sl, target)
        if result:
            results.append(result)
            print(f"✓ Win Rate: {result['win_rate']:.1f}%, P&L: ₹{result['total_pnl']:,.0f}")
        else:
            print("✗ Failed")
    
    # Display results table
    print(f"\n{'='*80}")
    print(f"   📊 RESULTS COMPARISON")
    print(f"{'='*80}\n")
    
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values('total_pnl', ascending=False)
    
    print(f"{'Config':<35} {'RR':>6} {'Trades':>7} {'Win %':>7} {'Total P&L':>12} {'Avg P&L':>10} {'PF':>6}")
    print("-" * 90)
    
    for _, row in results_df.iterrows():
        print(f"{row['config']:<35} {row['rr_ratio']:>6.2f} {row['total_trades']:>7} {row['win_rate']:>6.1f}% {row['total_pnl']:>11,.0f} {row['avg_pnl']:>10,.0f} {row['profit_factor']:>6.2f}")
    
    print(f"\n{'='*80}")
    
    # Best configuration
    best = results_df.iloc[0]
    print(f"""
🏆 BEST CONFIGURATION: {best['config']}
   
   Risk-Reward Ratio: 1:{best['rr_ratio']:.1f}
   Stop Loss: {best['sl_pct']:.0f}%
   Target: {best['target_pct']:.0f}%
   
   Total Trades: {best['total_trades']}
   Win Rate: {best['win_rate']:.1f}%
   Total P&L: ₹{best['total_pnl']:,.0f}
   Profit Factor: {best['profit_factor']:.2f}
""")
    
    # Save comparison results
    output_file = REPORTS_DIR / 'rr_comparison_results.csv'
    results_df.to_csv(output_file, index=False)
    print(f"📁 Results saved to: {output_file}")


if __name__ == "__main__":
    main()
