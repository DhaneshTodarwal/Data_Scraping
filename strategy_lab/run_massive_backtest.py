#!/usr/bin/env python3
"""
MASSIVE WALK-FORWARD BACKTEST
==============================
Uses ALL 101+ expiry days from old-data-by-dj for proper statistical testing.
60/40 train-test split.
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
from runner.old_data_loader import OldDataLoader
from runner.gamma_backtest_engine import GammaBacktestEngine
from strategies.gamma_ema_v2 import GammaEMAConfluenceV2


def generate_synthetic_index_data(strikes_data: dict, year: int, month: str, day: int) -> pd.DataFrame:
    """
    Generate index data from options data.
    Since we don't have index OHLCV, we estimate from option strikes.
    """
    # Get all timestamps from options data
    all_timestamps = set()
    all_strikes = []
    
    for opt_type in ['CE', 'PE']:
        for strike, df in strikes_data[opt_type].items():
            all_strikes.append(strike)
            all_timestamps.update(df['timestamp'].tolist())
    
    if not all_timestamps:
        return pd.DataFrame()
    
    # ATM strike is approximate index value
    atm_strike = int(np.median(all_strikes))
    
    # Create index dataframe
    timestamps = sorted(all_timestamps)
    df = pd.DataFrame({'timestamp': timestamps})
    
    # Approximate index as ATM strike (rough estimate)
    df['open'] = atm_strike
    df['high'] = atm_strike + 50
    df['low'] = atm_strike - 50
    df['close'] = atm_strike
    df['volume'] = 1000
    
    return df


def run_massive_backtest():
    """Run walk-forward test on ALL available data."""
    
    print(f"\n{'='*80}")
    print(f"   🚀 MASSIVE WALK-FORWARD BACKTEST")
    print(f"   Using 101+ Expiry Days from Old Data")
    print(f"{'='*80}\n")
    
    loader = OldDataLoader()
    
    # Focus on main symbols with most data
    symbols_to_test = ['NIFTY', 'BANKNIFTY', 'SENSEX']
    
    all_results = {}
    
    for symbol in symbols_to_test:
        print(f"\n{'='*70}")
        print(f"📈 Testing: {symbol}")
        print(f"{'='*70}\n")
        
        expiry_dates = loader.get_available_expiry_dates(symbol)
        
        if len(expiry_dates) < 6:
            print(f"⚠️ Insufficient data for {symbol} ({len(expiry_dates)} days, need at least 6)")
            continue
        
        # 60/40 split
        split_idx = int(len(expiry_dates) * 0.6)
        training_dates = expiry_dates[:split_idx]
        test_dates = expiry_dates[split_idx:]
        
        print(f"📚 TRAINING: {len(training_dates)} days (60%)")
        print(f"🧪 TEST: {len(test_dates)} days (40%)")
        
        # ===============================================
        # PHASE 1: TRAINING
        # ===============================================
        print(f"\n--- PHASE 1: TRAINING (Parameter Optimization) ---\n")
        
        configs = [
            ('25% SL / 1:4 RR', 25, 100),
            ('30% SL / 1:3 RR', 30, 90),
            ('35% SL / 1:2 RR', 35, 70),
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
                strikes_data = loader.load_strikes_data(symbol, year, month, day)
                if not strikes_data['CE'] and not strikes_data['PE']:
                    continue
                
                # Generate synthetic index data
                index_df = generate_synthetic_index_data(strikes_data, year, month, day)
                if index_df.empty:
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
        
        if not training_results:
            print(f"⚠️ No training results for {symbol}")
            continue
        
        # Select best config
        best_config = max(training_results.items(), key=lambda x: x[1]['pnl'])
        best_name, best_params = best_config
        
        print(f"\n🏆 BEST CONFIG: {best_name} (P&L: ₹{best_params['pnl']:,.0f})")
        
        # ===============================================
        # PHASE 2: OUT-OF-SAMPLE TEST
        # ===============================================
        print(f"\n--- PHASE 2: OUT-OF-SAMPLE TEST (HONEST RESULTS) ---\n")
        
        strategy = GammaEMAConfluenceV2({
            'stop_loss_pct': best_params['sl_pct'],
            'target_pct': best_params['target_pct'],
            'entry_time_start': '11:00',
            'sideways_exit_minutes': 10,
        })
        
        test_trades = []
        daily_results = []
        
        for year, month, day in test_dates:
            date_str = f"{year}-{month}-{day:02d}"
            
            strikes_data = loader.load_strikes_data(symbol, year, month, day)
            if not strikes_data['CE'] and not strikes_data['PE']:
                continue
            
            index_df = generate_synthetic_index_data(strikes_data, year, month, day)
            if index_df.empty:
                continue
            
            signals = strategy.generate_signals(index_df, strikes_data, symbol)
            if not signals:
                continue
            
            engine = GammaBacktestEngine(symbol, {
                'initial_capital': 100000,
                'stop_loss_pct': best_params['sl_pct'],
                'target_pct': best_params['target_pct'],
            })
            result = engine.run(signals, strikes_data)
            
            day_pnl = sum(t['pnl'] for t in result.get('trades', []))
            day_trades = len(result.get('trades', []))
            
            daily_results.append({
                'date': date_str,
                'trades': day_trades,
                'pnl': day_pnl,
            })
            
            test_trades.extend(result.get('trades', []))
            
            status = "✓" if day_pnl > 0 else "✗"
            print(f"   {date_str}: {day_trades:2} trades, ₹{day_pnl:>8,.0f} {status}")
        
        if test_trades:
            df = pd.DataFrame(test_trades)
            total_trades = len(df)
            winners = len(df[df['pnl'] > 0])
            total_pnl = df['pnl'].sum()
            win_rate = winners / total_trades * 100 if total_trades > 0 else 0
            
            profit_trades = df[df['pnl'] > 0]['pnl'].sum() if len(df[df['pnl'] > 0]) > 0 else 0
            loss_trades = abs(df[df['pnl'] < 0]['pnl'].sum()) if len(df[df['pnl'] < 0]) > 0 else 0
            profit_factor = profit_trades / loss_trades if loss_trades > 0 else float('inf')
            
            profitable_days = len([d for d in daily_results if d['pnl'] > 0])
            
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
                'profitable_days': profitable_days,
                'daily_results': daily_results,
            }
            
            print(f"\n📊 {symbol} OUT-OF-SAMPLE SUMMARY")
            print(f"   Days: {len(test_dates)} | Trades: {total_trades}")
            print(f"   Win Rate: {win_rate:.1f}% | P&L: ₹{total_pnl:,.0f}")
            print(f"   Profit Factor: {profit_factor:.2f}")
            print(f"   Profitable Days: {profitable_days}/{len(daily_results)}")
    
    # ========================================
    # FINAL SUMMARY
    # ========================================
    print(f"\n{'='*80}")
    print(f"   📊 FINAL SUMMARY - MASSIVE OUT-OF-SAMPLE RESULTS")
    print(f"{'='*80}\n")
    
    total_pnl = 0
    total_trades = 0
    total_days = 0
    
    print(f"{'Symbol':<12} {'Config':<20} {'Days':>5} {'Trades':>7} {'Win %':>7} {'P&L':>12} {'PF':>6}")
    print("-" * 85)
    
    for symbol, res in all_results.items():
        print(f"{symbol:<12} {res['selected_config']:<20} {res['test_days']:>5} {res['total_trades']:>7} {res['win_rate']:>6.1f}% {res['total_pnl']:>11,.0f} {res['profit_factor']:>6.2f}")
        total_pnl += res['total_pnl']
        total_trades += res['total_trades']
        total_days += res['test_days']
    
    print("-" * 85)
    print(f"{'COMBINED':<32} {total_days:>5} {total_trades:>7} {'':>7} {total_pnl:>11,.0f}")
    
    # Save results
    output_dir = REPORTS_DIR / f"MASSIVE_Backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / 'summary.json', 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\n📁 Results saved to: {output_dir}")
    
    print(f"""
{'='*80}
   ✅ THIS IS THE PURE OUT-OF-SAMPLE RESULT
{'='*80}

   • Training: 60% of data (parameters selected)
   • Testing: 40% of data (UNSEEN, honest results)
   • Combined: {total_days} test days, {total_trades} trades
   • Net P&L: ₹{total_pnl:,.0f}
   
{'='*80}
""")
    
    return all_results


if __name__ == "__main__":
    run_massive_backtest()
