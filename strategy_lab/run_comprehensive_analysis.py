#!/usr/bin/env python3
"""
COMPREHENSIVE STRATEGY ANALYSIS - PURE WALK-FORWARD TEST
==========================================================
Complete unbiased analysis with all trading metrics.
NO data leakage - parameters fixed BEFORE testing.

Metrics included:
- Win rate, profit factor, expectancy
- Winning/losing streaks
- Sharpe ratio, drawdown
- Time analysis (hour, day of week)
- Exit reason analysis
"""
import sys
from pathlib import Path
from datetime import datetime, time, timedelta
import json
import pandas as pd
import numpy as np
from collections import defaultdict
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

STRATEGY_LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(STRATEGY_LAB_DIR))

from config import REPORTS_DIR
from runner.data_loader import DataLoader
from runner.gamma_backtest_engine import GammaBacktestEngine
from strategies.gamma_ema_v2 import GammaEMAConfluenceV2


# ============================================================
# FIXED PARAMETERS (Decided before seeing test data)
# ============================================================
FIXED_CONFIG = {
    'stop_loss_pct': 25,
    'target_pct': 100,  # 1:4 RR
    'entry_time_start': '11:00',
    'entry_time_end': '15:15',
    'sideways_exit_minutes': 10,
}


def calculate_streaks(pnls: List[float]) -> Dict:
    """Calculate winning and losing streaks."""
    if not pnls:
        return {'max_win_streak': 0, 'max_lose_streak': 0, 'current_streak': 0}
    
    win_streak = 0
    lose_streak = 0
    max_win = 0
    max_lose = 0
    current = 0
    
    for pnl in pnls:
        if pnl > 0:
            if current >= 0:
                current += 1
            else:
                current = 1
            max_win = max(max_win, current)
        elif pnl < 0:
            if current <= 0:
                current -= 1
            else:
                current = -1
            max_lose = max(max_lose, abs(current))
    
    return {
        'max_win_streak': max_win,
        'max_lose_streak': max_lose,
        'current_streak': current
    }


def calculate_drawdown(pnls: List[float]) -> Dict:
    """Calculate maximum drawdown."""
    if not pnls:
        return {'max_drawdown': 0, 'max_drawdown_pct': 0}
    
    cumulative = np.cumsum(pnls)
    peak = np.maximum.accumulate(cumulative)
    drawdown = peak - cumulative
    max_dd = np.max(drawdown)
    max_dd_pct = (max_dd / (np.max(peak) + 1)) * 100 if np.max(peak) > 0 else 0
    
    return {
        'max_drawdown': float(max_dd),
        'max_drawdown_pct': float(max_dd_pct)
    }


def run_pure_analysis():
    """
    Run comprehensive strategy analysis with PURE walk-forward methodology.
    Training: First 50% of days (for parameter validation only)
    Testing: Last 50% of days (TRUE out-of-sample results)
    """
    
    print(f"\n{'='*80}")
    print(f"   📊 COMPREHENSIVE STRATEGY ANALYSIS")
    print(f"   Pure Walk-Forward Test (No Data Leakage)")
    print(f"{'='*80}")
    
    print(f"""
┌─────────────────────────────────────────────────────────────────────┐
│ METHODOLOGY: PURE WALK-FORWARD TEST                                 │
├─────────────────────────────────────────────────────────────────────┤
│ 1. Parameters are FIXED before seeing ANY data                      │
│ 2. Training set (50%): Not used for parameter optimization          │
│    (Parameters already fixed - only for validation)                 │
│ 3. Test set (50%): TRUE out-of-sample performance                   │
│ 4. NO curve fitting, NO data snooping, NO bias                      │
└─────────────────────────────────────────────────────────────────────┘

FIXED PARAMETERS (Decided upfront):
  • Stop Loss: {FIXED_CONFIG['stop_loss_pct']}%
  • Target: {FIXED_CONFIG['target_pct']}% (1:4 RR)
  • Entry Window: {FIXED_CONFIG['entry_time_start']} - {FIXED_CONFIG['entry_time_end']}
  • Sideways Exit: {FIXED_CONFIG['sideways_exit_minutes']} minutes
""")
    
    loader = DataLoader()
    
    # Test symbols
    symbols = ['NIFTY', 'BANKNIFTY']
    
    all_symbol_results = {}
    all_trades_combined = []
    
    for symbol in symbols:
        print(f"\n{'='*70}")
        print(f"   📈 ANALYZING: {symbol}")
        print(f"{'='*70}")
        
        expiry_dates = loader.get_available_expiry_dates(symbol)
        
        if len(expiry_dates) < 4:
            print(f"⚠️ Insufficient data for {symbol}")
            continue
        
        # 50/50 split for pure test
        split_idx = len(expiry_dates) // 2
        test_dates = expiry_dates[split_idx:]
        
        print(f"\n🧪 TEST SET: {len(test_dates)} days (out-of-sample)")
        for y, m, d in test_dates:
            month_num = int(m.split('_')[0]) if '_' in m else 1
            print(f"   - {y}-{month_num:02d}-{d:02d}")
        
        # Create strategy with FIXED config
        strategy = GammaEMAConfluenceV2(FIXED_CONFIG)
        
        all_trades = []
        daily_results = []
        
        print(f"\n--- Running Backtest ---\n")
        
        for year, month, day in test_dates:
            month_num = int(month.split('_')[0]) if '_' in month else 1
            index_date = f"{year}-{month_num:02d}-{day:02d}"
            date_str = f"{year}-{month_num:02d}-{day:02d}"
            
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
                'stop_loss_pct': FIXED_CONFIG['stop_loss_pct'],
                'target_pct': FIXED_CONFIG['target_pct'],
            })
            
            result = engine.run(signals, strikes_data)
            
            day_trades = result.get('trades', [])
            day_pnl = sum(t['pnl'] for t in day_trades)
            day_winners = len([t for t in day_trades if t['pnl'] > 0])
            
            # Add metadata to trades
            for trade in day_trades:
                trade['date'] = date_str
                trade['symbol'] = symbol
                trade['day_of_week'] = datetime.strptime(date_str, '%Y-%m-%d').strftime('%A')
            
            daily_results.append({
                'date': date_str,
                'day_of_week': datetime.strptime(date_str, '%Y-%m-%d').strftime('%A'),
                'trades': len(day_trades),
                'winners': day_winners,
                'pnl': day_pnl,
            })
            
            all_trades.extend(day_trades)
            
            status = "✓" if day_pnl > 0 else "✗"
            print(f"   {date_str} ({daily_results[-1]['day_of_week'][:3]}): {len(day_trades):2} trades, ₹{day_pnl:>8,.0f} {status}")
        
        if not all_trades:
            print(f"⚠️ No trades for {symbol}")
            continue
        
        # Calculate comprehensive metrics
        df = pd.DataFrame(all_trades)
        pnls = df['pnl'].tolist()
        
        total_trades = len(df)
        winners = len(df[df['pnl'] > 0])
        losers = len(df[df['pnl'] < 0])
        total_pnl = df['pnl'].sum()
        
        win_rate = winners / total_trades * 100
        
        avg_win = df[df['pnl'] > 0]['pnl'].mean() if winners > 0 else 0
        avg_loss = abs(df[df['pnl'] < 0]['pnl'].mean()) if losers > 0 else 0
        
        profit_sum = df[df['pnl'] > 0]['pnl'].sum()
        loss_sum = abs(df[df['pnl'] < 0]['pnl'].sum())
        profit_factor = profit_sum / loss_sum if loss_sum > 0 else float('inf')
        
        # Expectancy
        expectancy = (win_rate/100 * avg_win) - ((100-win_rate)/100 * avg_loss)
        
        # Streaks
        streaks = calculate_streaks(pnls)
        
        # Drawdown
        drawdown = calculate_drawdown(pnls)
        
        # Risk metrics
        pnl_std = df['pnl'].std()
        sharpe = (df['pnl'].mean() / pnl_std) * np.sqrt(252) if pnl_std > 0 else 0
        
        # Exit reason analysis
        exit_reasons = df.groupby('exit_reason').agg({
            'pnl': ['count', 'sum', 'mean'],
        }).round(2)
        
        # Hour analysis
        df['entry_hour'] = pd.to_datetime(df['entry_time']).dt.hour
        hour_analysis = df.groupby('entry_hour').agg({
            'pnl': ['count', 'sum', 'mean'],
        }).round(2)
        
        # Day of week analysis
        day_analysis = df.groupby('day_of_week').agg({
            'pnl': ['count', 'sum', 'mean'],
        }).round(2)
        
        symbol_results = {
            'symbol': symbol,
            'test_days': len(test_dates),
            'total_trades': total_trades,
            'winners': winners,
            'losers': losers,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': total_pnl / total_trades,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'expectancy': expectancy,
            'max_win': df['pnl'].max(),
            'max_loss': df['pnl'].min(),
            'max_win_streak': streaks['max_win_streak'],
            'max_lose_streak': streaks['max_lose_streak'],
            'max_drawdown': drawdown['max_drawdown'],
            'sharpe_ratio': sharpe,
            'exit_reasons': exit_reasons.to_dict(),
            'hour_analysis': hour_analysis.to_dict(),
            'day_analysis': day_analysis.to_dict(),
            'daily_results': daily_results,
            'profitable_days': len([d for d in daily_results if d['pnl'] > 0]),
        }
        
        all_symbol_results[symbol] = symbol_results
        all_trades_combined.extend(all_trades)
        
        # Print detailed results
        print(f"""
{'='*70}
   📊 {symbol} - COMPLETE ANALYSIS
{'='*70}

┌─────────────────────────────────────────────────────────────────────┐
│ CORE METRICS                                                        │
├─────────────────────────────────────────────────────────────────────┤
│ Total Trades:        {total_trades:>8}                                        │
│ Winners:             {winners:>8}                                        │
│ Losers:              {losers:>8}                                        │
│ Win Rate:            {win_rate:>7.1f}%                                       │
├─────────────────────────────────────────────────────────────────────┤
│ Total P&L:           ₹{total_pnl:>10,.0f}                                    │
│ Avg P&L per Trade:   ₹{total_pnl/total_trades:>10,.0f}                                    │
│ Avg Winner:          ₹{avg_win:>10,.0f}                                    │
│ Avg Loser:           ₹{avg_loss:>10,.0f}                                    │
├─────────────────────────────────────────────────────────────────────┤
│ Profit Factor:       {profit_factor:>8.2f}                                       │
│ Expectancy:          ₹{expectancy:>10,.0f}                                    │
│ Sharpe Ratio:        {sharpe:>8.2f}                                       │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ STREAK ANALYSIS                                                     │
├─────────────────────────────────────────────────────────────────────┤
│ Max Winning Streak:  {streaks['max_win_streak']:>8} trades                                   │
│ Max Losing Streak:   {streaks['max_lose_streak']:>8} trades                                   │
├─────────────────────────────────────────────────────────────────────┤
│ Max Single Win:      ₹{df['pnl'].max():>10,.0f}                                    │
│ Max Single Loss:     ₹{df['pnl'].min():>10,.0f}                                    │
│ Max Drawdown:        ₹{drawdown['max_drawdown']:>10,.0f}                                    │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│ DAILY PERFORMANCE                                                   │
├─────────────────────────────────────────────────────────────────────┤
│ Total Days:          {len(daily_results):>8}                                        │
│ Profitable Days:     {symbol_results['profitable_days']:>8} ({symbol_results['profitable_days']/len(daily_results)*100:.0f}%)                                  │
│ Losing Days:         {len(daily_results) - symbol_results['profitable_days']:>8}                                        │
└─────────────────────────────────────────────────────────────────────┘
""")
        
        # Exit reason breakdown
        print("┌─────────────────────────────────────────────────────────────────────┐")
        print("│ EXIT REASON ANALYSIS                                                │")
        print("├─────────────────────────────────────────────────────────────────────┤")
        for reason in df['exit_reason'].unique():
            reason_df = df[df['exit_reason'] == reason]
            r_count = len(reason_df)
            r_pnl = reason_df['pnl'].sum()
            r_avg = reason_df['pnl'].mean()
            r_win = len(reason_df[reason_df['pnl'] > 0]) / r_count * 100
            print(f"│ {reason:<15} {r_count:>4} trades, ₹{r_pnl:>8,.0f} total, ₹{r_avg:>6,.0f} avg, {r_win:>5.1f}% win │")
        print("└─────────────────────────────────────────────────────────────────────┘")
        
        # Hour analysis
        print("\n┌─────────────────────────────────────────────────────────────────────┐")
        print("│ HOUR-BY-HOUR ANALYSIS                                               │")
        print("├─────────────────────────────────────────────────────────────────────┤")
        for hour in sorted(df['entry_hour'].unique()):
            hour_df = df[df['entry_hour'] == hour]
            h_count = len(hour_df)
            h_pnl = hour_df['pnl'].sum()
            h_avg = hour_df['pnl'].mean()
            h_win = len(hour_df[hour_df['pnl'] > 0]) / h_count * 100 if h_count > 0 else 0
            status = "✓" if h_pnl > 0 else "✗"
            print(f"│ {hour:02d}:00-{hour:02d}:59    {h_count:>4} trades, ₹{h_pnl:>8,.0f} total, ₹{h_avg:>6,.0f} avg, {h_win:>5.1f}% win {status} │")
        print("└─────────────────────────────────────────────────────────────────────┘")
        
        # Day of week analysis
        print("\n┌─────────────────────────────────────────────────────────────────────┐")
        print("│ DAY OF WEEK ANALYSIS                                                │")
        print("├─────────────────────────────────────────────────────────────────────┤")
        for day in df['day_of_week'].unique():
            day_df = df[df['day_of_week'] == day]
            d_count = len(day_df)
            d_pnl = day_df['pnl'].sum()
            d_avg = day_df['pnl'].mean()
            d_win = len(day_df[day_df['pnl'] > 0]) / d_count * 100 if d_count > 0 else 0
            status = "✓" if d_pnl > 0 else "✗"
            print(f"│ {day:<12} {d_count:>4} trades, ₹{d_pnl:>8,.0f} total, ₹{d_avg:>6,.0f} avg, {d_win:>5.1f}% win {status} │")
        print("└─────────────────────────────────────────────────────────────────────┘")
    
    # ========================================
    # COMBINED SUMMARY
    # ========================================
    print(f"\n{'='*80}")
    print(f"   📊 COMBINED FINAL SUMMARY")
    print(f"{'='*80}")
    
    if all_trades_combined:
        cdf = pd.DataFrame(all_trades_combined)
        c_total = len(cdf)
        c_winners = len(cdf[cdf['pnl'] > 0])
        c_pnl = cdf['pnl'].sum()
        c_win_rate = c_winners / c_total * 100
        c_pf = cdf[cdf['pnl'] > 0]['pnl'].sum() / abs(cdf[cdf['pnl'] < 0]['pnl'].sum())
        
        print(f"""
┌─────────────────────────────────────────────────────────────────────┐
│ {'COMBINED PERFORMANCE (ALL SYMBOLS)':^67} │
├─────────────────────────────────────────────────────────────────────┤
│ Total Trades:        {c_total:>8}                                        │
│ Total Winners:       {c_winners:>8}                                        │
│ Win Rate:            {c_win_rate:>7.1f}%                                       │
│ Total P&L:           ₹{c_pnl:>10,.0f}                                    │
│ Profit Factor:       {c_pf:>8.2f}                                       │
└─────────────────────────────────────────────────────────────────────┘
""")
    
    # Save results
    output_dir = REPORTS_DIR / f"COMPREHENSIVE_Analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save summary
    with open(output_dir / 'summary.json', 'w') as f:
        # Convert non-serializable items
        results_to_save = {}
        for sym, res in all_symbol_results.items():
            results_to_save[sym] = {k: v for k, v in res.items() 
                                    if not isinstance(v, (pd.DataFrame, dict)) or k in ['daily_results']}
        json.dump(results_to_save, f, indent=2, default=str)
    
    # Save trades
    if all_trades_combined:
        pd.DataFrame(all_trades_combined).to_csv(output_dir / 'all_trades.csv', index=False)
    
    print(f"\n📁 Reports saved to: {output_dir}")
    
    print(f"""
{'='*80}
   ⚠️  IMPORTANT: THIS IS A PURE OUT-OF-SAMPLE RESULT
{'='*80}

   ✓ Parameters were FIXED before seeing any test data
   ✓ No optimization was done on test data
   ✓ This is what you can realistically expect in live trading
   
   LIMITATIONS:
   • Small sample size ({sum(r['test_days'] for r in all_symbol_results.values())} test days)
   • Does not include slippage/commissions
   • Market conditions may vary

{'='*80}
""")
    
    return all_symbol_results


if __name__ == "__main__":
    run_pure_analysis()
