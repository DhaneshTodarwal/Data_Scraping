#!/usr/bin/env python3
"""
PURE WALK-FORWARD BACKTEST
==============================
This script provides honest, unbiased results by:
1. Splitting data into TRAINING (first 4 days) and TEST (last 4 days)
2. Parameters are decided ONLY from training data
3. Test results are TRUE OUT-OF-SAMPLE

This prevents curve-fitting and gives realistic performance expectations.
"""
import sys
from pathlib import Path
from datetime import datetime
import json
import pandas as pd
import numpy as np

STRATEGY_LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(STRATEGY_LAB_DIR))

from config import REPORTS_DIR
from runner.data_loader import DataLoader
from runner.gamma_backtest_engine import GammaBacktestEngine
from strategies.gamma_ema_v2 import GammaEMAConfluenceV2


def run_walkforward_test(symbol: str = 'NIFTY'):
    """
    Proper walk-forward testing:
    - Training Set (In-Sample): First 4 days for parameter optimization
    - Test Set (Out-of-Sample): Last 4 days for TRUE performance measurement
    """
    
    print(f"\n{'='*80}")
    print(f"   🔬 PURE WALK-FORWARD BACKTEST - HONEST RESULTS")
    print(f"{'='*80}")
    print(f"""
   ⚠️  IMPORTANT: This is the CORRECT way to backtest!
   
   Previous results were BIASED because we optimized parameters
   on the same data we tested on (data leakage/overfitting).
   
   This test splits data into:
   📚 TRAINING SET (First 4 days) - Used to decide parameters
   🧪 TEST SET (Last 4 days) - TRUE out-of-sample performance
   
   The TEST SET results are what you can actually expect in live trading!
""")
    print(f"{'='*80}\n")
    
    loader = DataLoader()
    expiry_dates = loader.get_available_expiry_dates(symbol)
    
    if not expiry_dates:
        print(f"⚠️ No data for {symbol}")
        return
    
    # Split into training (first half) and test (second half)
    mid_point = len(expiry_dates) // 2
    training_dates = expiry_dates[:mid_point]
    test_dates = expiry_dates[mid_point:]
    
    print(f"📊 Symbol: {symbol}")
    print(f"📅 Total Days: {len(expiry_dates)}")
    print(f"")
    print(f"📚 TRAINING SET (In-Sample): {len(training_dates)} days")
    for y, m, d in training_dates:
        print(f"   - {y}-{m.split('_')[0]}-{d:02d}")
    print(f"")
    print(f"🧪 TEST SET (Out-of-Sample): {len(test_dates)} days")
    for y, m, d in test_dates:
        print(f"   - {y}-{m.split('_')[0]}-{d:02d}")
    print(f"\n{'='*80}")
    
    # ========================================
    # PHASE 1: TRAINING (Parameter Selection)
    # ========================================
    print(f"\n📚 PHASE 1: TRAINING (Finding Best Parameters)")
    print(f"{'='*60}\n")
    
    # Test a few configurations on TRAINING data only
    configs_to_test = [
        ('Original (25%SL / 1:4 RR)', 25, 100),
        ('Wide SL (40%SL / 1:2 RR)', 40, 80),
        ('Conservative (30%SL / 1:1.5 RR)', 30, 45),
    ]
    
    training_results = {}
    
    for config_name, sl_pct, target_pct in configs_to_test:
        print(f"Testing {config_name} on training data...", end=" ")
        
        strategy = GammaEMAConfluenceV2({
            'stop_loss_pct': sl_pct,
            'target_pct': target_pct,
            'entry_time_start': '11:00',
            'sideways_exit_minutes': 10,
        })
        
        all_trades = []
        
        for year, month, day in training_dates:
            month_num = int(month.split('_')[0]) if '_' in month else 1
            index_date = f"{year}-{month_num:02d}-{day:02d}"
            
            index_df = loader.load_index_data(symbol, index_date)
            if index_df is None or index_df.empty:
                continue
            
            strikes_data = loader.load_strikes_data(symbol, year, month, day)
            if not strikes_data['CE'] and not strikes_data['PE']:
                continue
            
            signals = strategy.generate_signals(index_df, strikes_data, symbol)
            if not signals:
                continue
            
            engine_config = {
                'initial_capital': 100000,
                'stop_loss_pct': sl_pct,
                'target_pct': target_pct,
            }
            
            engine = GammaBacktestEngine(symbol, engine_config)
            result = engine.run(signals, strikes_data)
            all_trades.extend(result.get('trades', []))
        
        if all_trades:
            df = pd.DataFrame(all_trades)
            total_pnl = df['pnl'].sum()
            win_rate = len(df[df['pnl'] > 0]) / len(df) * 100
            training_results[config_name] = {
                'sl_pct': sl_pct,
                'target_pct': target_pct,
                'trades': len(df),
                'win_rate': win_rate,
                'pnl': total_pnl,
            }
            print(f"✓ P&L: ₹{total_pnl:,.0f}")
        else:
            print("✗ No trades")
    
    # Find best config from training
    best_config = max(training_results.items(), key=lambda x: x[1]['pnl'])
    best_name, best_params = best_config
    
    print(f"\n{'='*60}")
    print(f"   TRAINING RESULTS (IN-SAMPLE)")
    print(f"{'='*60}")
    print(f"{'Config':<35} {'Trades':>7} {'Win %':>7} {'P&L':>12}")
    print("-" * 65)
    for name, res in training_results.items():
        marker = " 👈 SELECTED" if name == best_name else ""
        print(f"{name:<35} {res['trades']:>7} {res['win_rate']:>6.1f}% {res['pnl']:>11,.0f}{marker}")
    
    print(f"\n🏆 Selected Parameters (based on training): {best_name}")
    print(f"   Stop Loss: {best_params['sl_pct']}%")
    print(f"   Target: {best_params['target_pct']}%")
    
    # ========================================
    # PHASE 2: TEST (Out-of-Sample Performance)
    # ========================================
    print(f"\n{'='*80}")
    print(f"🧪 PHASE 2: TEST (TRUE OUT-OF-SAMPLE - HONEST RESULTS)")
    print(f"{'='*80}\n")
    print(f"⚠️  These results are on UNSEEN data - this is what you can expect in live trading!\n")
    
    # Use selected parameters on TEST data
    strategy = GammaEMAConfluenceV2({
        'stop_loss_pct': best_params['sl_pct'],
        'target_pct': best_params['target_pct'],
        'entry_time_start': '11:00',
        'sideways_exit_minutes': 10,
    })
    
    test_trades = []
    daily_results = []
    
    for year, month, day in test_dates:
        month_num = int(month.split('_')[0]) if '_' in month else 1
        index_date = f"{year}-{month_num:02d}-{day:02d}"
        date_str = f"{year}-{month_num:02d}-{day:02d}"
        
        print(f"Testing: {date_str}...", end=" ")
        
        index_df = loader.load_index_data(symbol, index_date)
        if index_df is None or index_df.empty:
            print("⚠️ No data")
            continue
        
        strikes_data = loader.load_strikes_data(symbol, year, month, day)
        if not strikes_data['CE'] and not strikes_data['PE']:
            print("⚠️ No strikes")
            continue
        
        signals = strategy.generate_signals(index_df, strikes_data, symbol)
        if not signals:
            print("⚠️ No signals")
            continue
        
        engine_config = {
            'initial_capital': 100000,
            'stop_loss_pct': best_params['sl_pct'],
            'target_pct': best_params['target_pct'],
        }
        
        engine = GammaBacktestEngine(symbol, engine_config)
        result = engine.run(signals, strikes_data)
        
        day_pnl = sum(t['pnl'] for t in result.get('trades', []))
        day_trades = len(result.get('trades', []))
        day_winners = len([t for t in result.get('trades', []) if t['pnl'] > 0])
        
        daily_results.append({
            'date': date_str,
            'trades': day_trades,
            'winners': day_winners,
            'pnl': day_pnl,
        })
        
        test_trades.extend(result.get('trades', []))
        
        status = "✓" if day_pnl > 0 else "✗"
        print(f"{status} {day_trades} trades, P&L: ₹{day_pnl:,.0f}")
    
    # ========================================
    # FINAL RESULTS
    # ========================================
    print(f"\n{'='*80}")
    print(f"   📊 FINAL OUT-OF-SAMPLE RESULTS (HONEST PERFORMANCE)")
    print(f"{'='*80}\n")
    
    if test_trades:
        df = pd.DataFrame(test_trades)
        total_trades = len(df)
        winners = len(df[df['pnl'] > 0])
        losers = len(df[df['pnl'] < 0])
        total_pnl = df['pnl'].sum()
        win_rate = winners / total_trades * 100 if total_trades > 0 else 0
        avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
        max_win = df['pnl'].max()
        max_loss = df['pnl'].min()
        
        profit_trades = df[df['pnl'] > 0]['pnl'].sum()
        loss_trades = abs(df[df['pnl'] < 0]['pnl'].sum())
        profit_factor = profit_trades / loss_trades if loss_trades > 0 else float('inf')
        
        print(f"   📈 CONFIG USED (selected from training)")
        print(f"      Stop Loss: {best_params['sl_pct']}%")
        print(f"      Target: {best_params['target_pct']}%")
        print(f"      Entry Window: 11:00 - 15:15")
        print(f"")
        print(f"   📊 TRADE STATISTICS")
        print(f"      Days Tested:      {len(test_dates)}")
        print(f"      Total Trades:     {total_trades}")
        print(f"      Winners:          {winners}")
        print(f"      Losers:           {losers}")
        print(f"      Win Rate:         {win_rate:.1f}%")
        print(f"")
        print(f"   💰 PROFIT & LOSS")
        print(f"      Total P&L:        ₹{total_pnl:,.0f}")
        print(f"      Avg P&L/Trade:    ₹{avg_pnl:,.0f}")
        print(f"      Max Win:          ₹{max_win:,.0f}")
        print(f"      Max Loss:         ₹{max_loss:,.0f}")
        print(f"      Profit Factor:    {profit_factor:.2f}")
        print(f"")
        print(f"   📅 DAILY BREAKDOWN")
        profitable_days = 0
        for dr in daily_results:
            status = "✓" if dr['pnl'] > 0 else "✗"
            if dr['pnl'] > 0:
                profitable_days += 1
            print(f"      {dr['date']}: {dr['trades']:2} trades, ₹{dr['pnl']:>8,.0f} {status}")
        
        print(f"\n      Profitable Days: {profitable_days}/{len(daily_results)}")
        
        # Save results
        output_dir = REPORTS_DIR / f"PURE_Walkforward_{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save summary
        summary = {
            'test_type': 'WALK_FORWARD_OUT_OF_SAMPLE',
            'symbol': symbol,
            'training_days': len(training_dates),
            'test_days': len(test_dates),
            'selected_config': {
                'stop_loss_pct': best_params['sl_pct'],
                'target_pct': best_params['target_pct'],
            },
            'results': {
                'total_trades': total_trades,
                'winners': winners,
                'losers': losers,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'avg_pnl': avg_pnl,
                'profit_factor': profit_factor,
            },
            'daily_results': daily_results,
        }
        
        with open(output_dir / 'summary.json', 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        df.to_csv(output_dir / 'trades.csv', index=False)
        
        print(f"\n📁 Pure results saved to: {output_dir}")
        
        print(f"""
{'='*80}
   ⚠️  IMPORTANT NOTES ON THESE RESULTS
{'='*80}

   1. These are TRUE OUT-OF-SAMPLE results on unseen data
   2. Parameters were chosen BEFORE seeing test data
   3. This is what you can realistically expect in live trading
   
   4. HOWEVER, with only {len(test_dates)} test days, statistical
      significance is limited. More data = more reliable results.
   
   5. Actual live trading may differ due to:
      - Slippage
      - Order execution delays
      - Different market conditions
      
{'='*80}
""")
        
        return summary
    
    return None


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='NIFTY')
    args = parser.parse_args()
    
    run_walkforward_test(args.symbol.upper())


if __name__ == "__main__":
    main()
