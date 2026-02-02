#!/usr/bin/env python3
"""
COMPREHENSIVE DATA ANALYSIS & WALK-FORWARD TEST
=================================================
Uses ALL available data with proper 60/40 train-test split.
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


def print_data_summary():
    """Print comprehensive data summary."""
    loader = DataLoader()
    
    print(f"\n{'='*80}")
    print(f"   📊 COMPLETE DATA INVENTORY")
    print(f"{'='*80}\n")
    
    symbols = ['NIFTY', 'BANKNIFTY', 'SENSEX']
    all_data = {}
    
    for symbol in symbols:
        expiry_dates = loader.get_available_expiry_dates(symbol)
        index_dates = loader.get_available_dates(symbol)
        
        all_data[symbol] = {
            'expiry_dates': expiry_dates,
            'index_dates': index_dates,
        }
        
        print(f"📈 {symbol}")
        print(f"   Options Data (Expiry Days): {len(expiry_dates)}")
        for y, m, d in expiry_dates:
            month_num = int(m.split('_')[0]) if '_' in m else 1
            print(f"      - {y}-{month_num:02d}-{d:02d}")
        print(f"   Index Data Days: {len(index_dates)}")
        print()
    
    return all_data


def run_comprehensive_test():
    """
    Run comprehensive walk-forward test on all available symbols.
    Split: 60% training, 40% testing
    """
    
    print(f"\n{'='*80}")
    print(f"   🔬 COMPREHENSIVE WALK-FORWARD BACKTEST")
    print(f"   Using ALL Available Data with 60/40 Train-Test Split")
    print(f"{'='*80}\n")
    
    loader = DataLoader()
    all_results = {}
    
    symbols = ['NIFTY', 'BANKNIFTY']  # Skip SENSEX due to only 2 days
    
    for symbol in symbols:
        print(f"\n{'='*60}")
        print(f"   Testing: {symbol}")
        print(f"{'='*60}\n")
        
        expiry_dates = loader.get_available_expiry_dates(symbol)
        
        if len(expiry_dates) < 4:
            print(f"⚠️ Insufficient data for {symbol} ({len(expiry_dates)} days)")
            continue
        
        # 60/40 split
        split_idx = int(len(expiry_dates) * 0.6)
        training_dates = expiry_dates[:split_idx]
        test_dates = expiry_dates[split_idx:]
        
        print(f"📚 TRAINING SET: {len(training_dates)} days (60%)")
        for y, m, d in training_dates:
            month_num = int(m.split('_')[0]) if '_' in m else 1
            print(f"   - {y}-{month_num:02d}-{d:02d}")
        
        print(f"\n🧪 TEST SET: {len(test_dates)} days (40%)")
        for y, m, d in test_dates:
            month_num = int(m.split('_')[0]) if '_' in m else 1
            print(f"   - {y}-{month_num:02d}-{d:02d}")
        
        print(f"\n{'='*60}")
        print(f"   PHASE 1: TRAINING (Parameter Optimization)")
        print(f"{'='*60}\n")
        
        # Test multiple configurations on training data
        configs = [
            ('25% SL / 1:4 RR (100% target)', 25, 100),
            ('30% SL / 1:3 RR (90% target)', 30, 90),
            ('35% SL / 1:2 RR (70% target)', 35, 70),
            ('40% SL / 1:2 RR (80% target)', 40, 80),
        ]
        
        training_results = {}
        
        for config_name, sl_pct, target_pct in configs:
            print(f"Testing {config_name}...", end=" ", flush=True)
            
            strategy = GammaEMAConfluenceV2({
                'stop_loss_pct': sl_pct,
                'target_pct': target_pct,
                'entry_time_start': '11:00',
                'sideways_exit_minutes': 10,
            })
            
            train_trades = []
            
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
                
                engine = GammaBacktestEngine(symbol, {
                    'initial_capital': 100000,
                    'stop_loss_pct': sl_pct,
                    'target_pct': target_pct,
                })
                result = engine.run(signals, strikes_data)
                train_trades.extend(result.get('trades', []))
            
            if train_trades:
                df = pd.DataFrame(train_trades)
                pnl = df['pnl'].sum()
                win_rate = len(df[df['pnl'] > 0]) / len(df) * 100
                training_results[config_name] = {
                    'sl_pct': sl_pct,
                    'target_pct': target_pct,
                    'trades': len(df),
                    'win_rate': win_rate,
                    'pnl': pnl,
                }
                print(f"✓ {len(df)} trades, Win: {win_rate:.1f}%, P&L: ₹{pnl:,.0f}")
            else:
                print("✗ No trades")
        
        # Select best config
        best_config = max(training_results.items(), key=lambda x: x[1]['pnl'])
        best_name, best_params = best_config
        
        print(f"\n🏆 BEST CONFIG (from training): {best_name}")
        print(f"   SL: {best_params['sl_pct']}%, Target: {best_params['target_pct']}%")
        
        # ========================================
        # PHASE 2: OUT-OF-SAMPLE TEST
        # ========================================
        print(f"\n{'='*60}")
        print(f"   PHASE 2: OUT-OF-SAMPLE TEST (HONEST RESULTS)")
        print(f"{'='*60}\n")
        
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
            
            print(f"Testing: {date_str}...", end=" ", flush=True)
            
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
            
            engine = GammaBacktestEngine(symbol, {
                'initial_capital': 100000,
                'stop_loss_pct': best_params['sl_pct'],
                'target_pct': best_params['target_pct'],
            })
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
        
        # Calculate final results
        if test_trades:
            df = pd.DataFrame(test_trades)
            total_trades = len(df)
            winners = len(df[df['pnl'] > 0])
            total_pnl = df['pnl'].sum()
            win_rate = winners / total_trades * 100 if total_trades > 0 else 0
            
            profit_trades = df[df['pnl'] > 0]['pnl'].sum()
            loss_trades = abs(df[df['pnl'] < 0]['pnl'].sum())
            profit_factor = profit_trades / loss_trades if loss_trades > 0 else float('inf')
            
            all_results[symbol] = {
                'training_days': len(training_dates),
                'test_days': len(test_dates),
                'selected_config': best_name,
                'sl_pct': best_params['sl_pct'],
                'target_pct': best_params['target_pct'],
                'total_trades': total_trades,
                'winners': winners,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'profit_factor': profit_factor,
                'daily_results': daily_results,
            }
            
            print(f"\n📊 {symbol} OUT-OF-SAMPLE RESULTS")
            print(f"   Config: {best_name}")
            print(f"   Trades: {total_trades}")
            print(f"   Win Rate: {win_rate:.1f}%")
            print(f"   Total P&L: ₹{total_pnl:,.0f}")
            print(f"   Profit Factor: {profit_factor:.2f}")
    
    # ========================================
    # COMBINED SUMMARY
    # ========================================
    print(f"\n{'='*80}")
    print(f"   📊 FINAL SUMMARY - PURE OUT-OF-SAMPLE RESULTS")
    print(f"{'='*80}\n")
    
    print(f"{'Symbol':<12} {'Config':<30} {'Trades':>7} {'Win %':>7} {'P&L':>12} {'PF':>6}")
    print("-" * 80)
    
    total_pnl = 0
    total_trades = 0
    
    for symbol, res in all_results.items():
        print(f"{symbol:<12} {res['selected_config']:<30} {res['total_trades']:>7} {res['win_rate']:>6.1f}% {res['total_pnl']:>11,.0f} {res['profit_factor']:>6.2f}")
        total_pnl += res['total_pnl']
        total_trades += res['total_trades']
    
    print("-" * 80)
    print(f"{'COMBINED':<42} {total_trades:>7} {'':>7} {total_pnl:>11,.0f}")
    
    # Save results
    output_dir = REPORTS_DIR / f"COMPREHENSIVE_Test_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / 'summary.json', 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\n📁 Results saved to: {output_dir}")
    
    print(f"""
{'='*80}
   ⚠️  IMPORTANT NOTES
{'='*80}

   1. These are TRUE OUT-OF-SAMPLE results
   2. Training: First 60% of data ({len(training_dates)} days per symbol)
   3. Testing: Last 40% of data ({len(test_dates)} days per symbol)
   4. Parameters were decided BEFORE seeing test data
   
   5. DATA AVAILABLE:
      - NIFTY: 8 expiry days (Jan 16-29, 2026)
      - BANKNIFTY: 8 expiry days (Jan 16-29, 2026)
      - SENSEX: Only 2 days (skipped - too little data)
   
   6. For more reliable results, collect more historical data!
   
{'='*80}
""")
    
    return all_results


def main():
    print_data_summary()
    run_comprehensive_test()


if __name__ == "__main__":
    main()
