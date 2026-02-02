#!/usr/bin/env python3
"""
Run Gamma-EMA V2 (Optimized) Strategy Backtest
================================================
Compares V1 vs V2 performance.
"""
import sys
from pathlib import Path
from datetime import datetime
import json

# Add strategy_lab directory to path
STRATEGY_LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(STRATEGY_LAB_DIR))

from config import REPORTS_DIR
from runner.data_loader import DataLoader
from runner.gamma_backtest_engine import GammaBacktestEngine
from strategies.gamma_ema_v2 import GammaEMAConfluenceV2


def run_v2_backtest(symbol: str, verbose: bool = True):
    """Run V2 optimized strategy backtest."""
    
    strategy = GammaEMAConfluenceV2()
    loader = DataLoader()
    
    print(f"\n{'='*70}")
    print(f"🚀 GAMMA-EMA V2 (OPTIMIZED) BACKTEST")
    print(f"{'='*70}")
    print(f"   Symbol: {symbol}")
    print(f"   Optimizations:")
    print(f"     • Entry Window: 11:00 - 15:15 (was 13:30 - 15:15)")
    print(f"     • Stop Loss: 35% (was 25%)")
    print(f"     • Target: 1:2 RR / 70% (was 1:4 / 100%)")
    print(f"     • Sideways Exit: 10 mins (was 5 mins)")
    print(f"{'='*70}\n")
    
    expiry_dates = loader.get_available_expiry_dates(symbol)
    
    if not expiry_dates:
        print(f"⚠️ No data for {symbol}")
        return None
    
    print(f"📅 Found {len(expiry_dates)} expiry days\n")
    
    all_results = []
    all_trades = []
    
    for year, month, day in expiry_dates:
        date_str = f"{year}-{month.split('_')[0]}-{day:02d}"
        print(f"Processing: {year}/{month}/{day}...", end=" ")
        
        month_num = int(month.split('_')[0]) if '_' in month else 1
        index_date = f"{year}-{month_num:02d}-{day:02d}"
        
        index_df = loader.load_index_data(symbol, index_date)
        if index_df is None or index_df.empty:
            print("⚠️ No index data")
            continue
        
        strikes_data = loader.load_strikes_data(symbol, year, month, day)
        if not strikes_data['CE'] and not strikes_data['PE']:
            print("⚠️ No strikes data")
            continue
        
        signals = strategy.generate_signals(index_df, strikes_data, symbol)
        
        if not signals:
            print("⚠️ No signals")
            continue
        
        print(f"✓ {len(signals)} signals")
        
        # V2 config
        config = {
            'initial_capital': 100000,
            'stop_loss_pct': 35,
            'initial_rr': 2,
            'trail_start_rr': 1.5,
            'breakeven_trigger': 50,
            'sideways_exit_minutes': 10,
        }
        
        engine = GammaBacktestEngine(symbol, config)
        result = engine.run(signals, strikes_data)
        result['date'] = date_str
        all_results.append(result)
        all_trades.extend(result.get('trades', []))
    
    if all_results:
        combined = generate_combined(all_results, all_trades, symbol)
        print_combined(combined)
        save_report(combined, all_trades, symbol)
        return combined
    
    return None


def generate_combined(results, trades, symbol):
    """Generate combined report."""
    total_trades = sum(r.get('total_trades', 0) for r in results)
    total_winners = sum(r.get('winning_trades', 0) for r in results)
    total_pnl = sum(r.get('total_pnl', 0) for r in results)
    
    return {
        'strategy_name': 'Gamma_EMA_V2',
        'symbol': symbol,
        'days_tested': len(results),
        'total_trades': total_trades,
        'winning_trades': total_winners,
        'losing_trades': total_trades - total_winners,
        'win_rate': (total_winners / total_trades * 100) if total_trades > 0 else 0,
        'total_pnl': total_pnl,
        'final_capital': 100000 + total_pnl,
        'return_pct': total_pnl / 100000 * 100,
        'avg_pnl_per_trade': total_pnl / total_trades if total_trades > 0 else 0,
        'max_win': max(t['pnl'] for t in trades) if trades else 0,
        'max_loss': min(t['pnl'] for t in trades) if trades else 0,
        'dates': [r.get('date', '') for r in results],
        'daily_pnl': [r.get('total_pnl', 0) for r in results],
        'profitable_days': sum(1 for r in results if r.get('total_pnl', 0) > 0),
    }


def print_combined(combined):
    """Print combined report."""
    print(f"""
{'='*70}
          GAMMA-EMA V2 - COMBINED BACKTEST REPORT
{'='*70}

📅 BACKTEST PERIOD
   Symbol:           {combined.get('symbol')}
   Days Tested:      {combined.get('days_tested')}
   Profitable Days:  {combined.get('profitable_days')}

📊 TRADE STATISTICS
   Total Trades:     {combined.get('total_trades')}
   Winners:          {combined.get('winning_trades')}
   Losers:           {combined.get('losing_trades')}
   Win Rate:         {combined.get('win_rate', 0):.1f}%

💰 PROFIT & LOSS
   Initial Capital:  ₹{combined.get('initial_capital', 100000):,.0f}
   Final Capital:    ₹{combined.get('final_capital', 0):,.0f}
   Total P&L:        ₹{combined.get('total_pnl', 0):,.0f}
   Return:           {combined.get('return_pct', 0):.1f}%
   Avg P&L/Trade:    ₹{combined.get('avg_pnl_per_trade', 0):,.0f}
   Max Win:          ₹{combined.get('max_win', 0):,.0f}
   Max Loss:         ₹{combined.get('max_loss', 0):,.0f}

📈 DAILY P&L
""")
    for date, pnl in zip(combined.get('dates', []), combined.get('daily_pnl', [])):
        status = "✓" if pnl > 0 else "✗"
        print(f"   {date}: ₹{pnl:,.0f} {status}")
    
    print(f"\n{'='*70}")


def save_report(combined, trades, symbol):
    """Save reports."""
    import pandas as pd
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = REPORTS_DIR / f"Gamma_EMA_V2_{symbol}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / 'summary.json', 'w') as f:
        json.dump(combined, f, indent=2, default=str)
    
    if trades:
        pd.DataFrame(trades).to_csv(output_dir / 'trades.csv', index=False)
    
    print(f"\n📁 Reports saved to: {output_dir}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--symbol', default='NIFTY')
    args = parser.parse_args()
    
    if args.symbol.lower() == 'all':
        symbols = ['NIFTY', 'SENSEX']
    else:
        symbols = [args.symbol.upper()]
    
    for symbol in symbols:
        run_v2_backtest(symbol)


if __name__ == "__main__":
    main()
