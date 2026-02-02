#!/usr/bin/env python3
"""
Gamma-EMA Confluence Strategy Runner
======================================
Dedicated runner for testing the Gamma-EMA strategy on expiry days.

Usage:
    python3 run_gamma_strategy.py --symbol NIFTY
    python3 run_gamma_strategy.py --symbol all
"""
import argparse
import json
from pathlib import Path
from datetime import datetime
import sys
import os

# Add strategy_lab directory to path BEFORE any local imports
STRATEGY_LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(STRATEGY_LAB_DIR))
os.chdir(STRATEGY_LAB_DIR)

# Now import local modules
from config import REPORTS_DIR, AVAILABLE_SYMBOLS
from runner.data_loader import DataLoader
from runner.gamma_backtest_engine import GammaBacktestEngine
from strategies.gamma_ema_confluence import GammaEMAConfluenceStrategy


def run_gamma_backtest(symbol: str, verbose: bool = True):
    """Run Gamma-EMA backtest on a symbol."""
    
    if symbol not in ['NIFTY', 'SENSEX']:
        print(f"⚠️ Gamma-EMA strategy only supports NIFTY and SENSEX, got {symbol}")
        return None
    
    # Initialize
    strategy = GammaEMAConfluenceStrategy()
    loader = DataLoader()
    
    print(f"\n{'='*60}")
    print(f"🎯 GAMMA-EMA CONFLUENCE STRATEGY BACKTEST")
    print(f"{'='*60}")
    print(f"   Symbol: {symbol}")
    print(f"   Strategy: Expiry Day Scalping (Post 1:30 PM)")
    print(f"{'='*60}\n")
    
    # Get available expiry dates
    expiry_dates = loader.get_available_expiry_dates(symbol)
    
    if not expiry_dates:
        print(f"⚠️ No options data available for {symbol}")
        return None
    
    print(f"📅 Found {len(expiry_dates)} expiry days with options data\n")
    
    all_results = []
    all_trades = []
    
    for year, month, day in expiry_dates:
        date_str = f"{year}-{month.split('_')[0]}-{day:02d}"
        print(f"Processing: {year}/{month}/{day}...", end=" ")
        
        # Load index data
        # Convert month format
        month_num = int(month.split('_')[0]) if '_' in month else 1
        index_date = f"{year}-{month_num:02d}-{day:02d}"
        
        index_df = loader.load_index_data(symbol, index_date)
        
        if index_df is None or index_df.empty:
            print("⚠️ No index data")
            continue
        
        # Load strikes data
        strikes_data = loader.load_strikes_data(symbol, year, month, day)
        
        if not strikes_data['CE'] and not strikes_data['PE']:
            print("⚠️ No strikes data")
            continue
        
        # Generate signals
        signals = strategy.generate_signals(index_df, strikes_data, symbol)
        
        if not signals:
            print("⚠️ No signals generated")
            continue
        
        print(f"✓ {len(signals)} signals")
        
        # Run backtest
        config = {
            'initial_capital': 100000,
            'stop_loss_pct': 25,
            'initial_rr': 4,
            'trail_start_rr': 3,
            'breakeven_trigger': 100,
            'sideways_exit_minutes': 5,
        }
        
        engine = GammaBacktestEngine(symbol, config)
        result = engine.run(signals, strikes_data)
        
        result['date'] = date_str
        all_results.append(result)
        all_trades.extend(result.get('trades', []))
        
        if verbose and result.get('total_trades', 0) > 0:
            engine.print_report(result)
    
    # Generate combined report
    if all_results:
        combined = generate_combined_report(all_results, all_trades, symbol)
        save_report(combined, all_trades, symbol)
        print_combined_report(combined)
        return combined
    else:
        print("⚠️ No trades executed")
        return None


def generate_combined_report(results: list, trades: list, symbol: str) -> dict:
    """Generate combined report across all days."""
    
    combined = {
        'strategy_name': 'Gamma_EMA_Confluence',
        'symbol': symbol,
        'days_tested': len(results),
        'dates': [r.get('date', '') for r in results],
        'initial_capital': 100000,
    }
    
    # Aggregate statistics
    total_trades = sum(r.get('total_trades', 0) for r in results)
    total_winners = sum(r.get('winning_trades', 0) for r in results)
    total_pnl = sum(r.get('total_pnl', 0) for r in results)
    
    combined['total_trades'] = total_trades
    combined['winning_trades'] = total_winners
    combined['losing_trades'] = total_trades - total_winners
    combined['win_rate'] = (total_winners / total_trades * 100) if total_trades > 0 else 0
    
    combined['total_pnl'] = total_pnl
    combined['final_capital'] = 100000 + total_pnl
    combined['return_pct'] = (total_pnl / 100000 * 100)
    combined['avg_pnl_per_trade'] = (total_pnl / total_trades) if total_trades > 0 else 0
    
    if trades:
        pnls = [t['pnl'] for t in trades]
        combined['max_win'] = max(pnls)
        combined['max_loss'] = min(pnls)
        
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        combined['profit_factor'] = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        combined['avg_duration'] = sum(t.get('duration_minutes', 0) for t in trades) / len(trades)
        combined['trades_hit_breakeven'] = sum(1 for t in trades if t.get('hit_breakeven'))
        combined['trades_with_trailing'] = sum(1 for t in trades if t.get('trailing_activated'))
        
        # Exit breakdown
        exit_reasons = {}
        for t in trades:
            reason = t.get('exit_reason', 'unknown')
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        combined['exit_breakdown'] = exit_reasons
    
    # Daily performance
    combined['daily_pnl'] = [r.get('total_pnl', 0) for r in results]
    combined['profitable_days'] = sum(1 for r in results if r.get('total_pnl', 0) > 0)
    
    return combined


def print_combined_report(combined: dict):
    """Print combined report."""
    print(f"""
{'='*70}
          GAMMA-EMA CONFLUENCE - COMBINED BACKTEST REPORT
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
   Initial Capital:  ₹{combined.get('initial_capital', 0):,.0f}
   Final Capital:    ₹{combined.get('final_capital', 0):,.0f}
   Total P&L:        ₹{combined.get('total_pnl', 0):,.0f}
   Return:           {combined.get('return_pct', 0):.1f}%
   Avg P&L/Trade:    ₹{combined.get('avg_pnl_per_trade', 0):,.0f}
   Max Win:          ₹{combined.get('max_win', 0):,.0f}
   Max Loss:         ₹{combined.get('max_loss', 0):,.0f}
   Profit Factor:    {combined.get('profit_factor', 0):.2f}

🎯 STRATEGY METRICS
   Avg Duration:     {combined.get('avg_duration', 0):.0f} minutes
   Hit Breakeven:    {combined.get('trades_hit_breakeven', 0)} trades
   Trailing Active:  {combined.get('trades_with_trailing', 0)} trades

📋 EXIT BREAKDOWN
""")
    for reason, count in combined.get('exit_breakdown', {}).items():
        pct = count / combined.get('total_trades', 1) * 100
        print(f"   {reason}: {count} ({pct:.1f}%)")
    
    print(f"""
📈 DAILY P&L
""")
    for i, (date, pnl) in enumerate(zip(combined.get('dates', []), combined.get('daily_pnl', []))):
        status = "✓" if pnl > 0 else "✗"
        print(f"   {date}: ₹{pnl:,.0f} {status}")
    
    print(f"\n{'='*70}")


def save_report(combined: dict, trades: list, symbol: str):
    """Save report to files."""
    import pandas as pd
    
    # Create output directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = REPORTS_DIR / f"Gamma_EMA_{symbol}_{timestamp}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save summary JSON
    with open(output_dir / 'summary.json', 'w') as f:
        # Convert non-serializable values
        save_combined = {k: v for k, v in combined.items()}
        if 'profit_factor' in save_combined and save_combined['profit_factor'] == float('inf'):
            save_combined['profit_factor'] = 999999
        json.dump(save_combined, f, indent=2, default=str)
    
    # Save trades CSV
    if trades:
        trades_df = pd.DataFrame(trades)
        trades_df.to_csv(output_dir / 'trades.csv', index=False)
    
    # Generate HTML report
    generate_html_report(combined, trades, output_dir / 'report.html')
    
    print(f"\n📁 Reports saved to: {output_dir}")


def generate_html_report(combined: dict, trades: list, output_path: Path):
    """Generate HTML report with styling."""
    
    pnl_color = "#27ae60" if combined.get('total_pnl', 0) > 0 else "#e74c3c"
    
    trades_html = ""
    for t in trades:
        pnl_class = "positive" if t['pnl'] > 0 else "negative"
        trades_html += f"""
        <tr>
            <td>{t['entry_time']}</td>
            <td>{t['signal_type']}</td>
            <td>{t['strike']}</td>
            <td>₹{t['entry_price']}</td>
            <td>₹{t['exit_price']}</td>
            <td class="{pnl_class}">₹{t['pnl']:,.0f}</td>
            <td>{t['exit_reason']}</td>
            <td>{t['duration_minutes']}m</td>
        </tr>
        """
    
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Gamma-EMA Confluence Strategy Report - {combined.get('symbol')}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 0; padding: 20px; background: #1a1a2e; color: #eee; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: #00d4ff; text-align: center; margin-bottom: 30px; }}
        h2 {{ color: #00d4ff; border-bottom: 2px solid #00d4ff; padding-bottom: 10px; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin: 20px 0; }}
        .stat-card {{ background: #16213e; padding: 20px; border-radius: 10px; text-align: center; }}
        .stat-value {{ font-size: 28px; font-weight: bold; color: #00d4ff; }}
        .stat-label {{ color: #888; font-size: 12px; margin-top: 5px; }}
        .positive {{ color: #27ae60; }}
        .negative {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; background: #16213e; border-radius: 10px; overflow: hidden; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #2a2a4a; }}
        th {{ background: #0f3460; color: #00d4ff; }}
        tr:hover {{ background: #1f4068; }}
        .exit-breakdown {{ display: flex; gap: 15px; flex-wrap: wrap; margin: 20px 0; }}
        .exit-chip {{ background: #0f3460; padding: 10px 20px; border-radius: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 Gamma-EMA Confluence Strategy</h1>
        <p style="text-align: center; color: #888;">Expiry Day Scalping | {combined.get('symbol')} | {combined.get('days_tested')} Days Tested</p>
        
        <div class="summary-grid">
            <div class="stat-card">
                <div class="stat-value">{combined.get('total_trades')}</div>
                <div class="stat-label">Total Trades</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{combined.get('win_rate', 0):.1f}%</div>
                <div class="stat-label">Win Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color: {pnl_color}">₹{combined.get('total_pnl', 0):,.0f}</div>
                <div class="stat-label">Total P&L</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{combined.get('profit_factor', 0):.2f}</div>
                <div class="stat-label">Profit Factor</div>
            </div>
        </div>
        
        <h2>📊 Performance Summary</h2>
        <div class="summary-grid">
            <div class="stat-card">
                <div class="stat-value">₹{combined.get('initial_capital', 0):,.0f}</div>
                <div class="stat-label">Initial Capital</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" style="color: {pnl_color}">₹{combined.get('final_capital', 0):,.0f}</div>
                <div class="stat-label">Final Capital</div>
            </div>
            <div class="stat-card">
                <div class="stat-value class="positive">₹{combined.get('max_win', 0):,.0f}</div>
                <div class="stat-label">Max Win</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" class="negative">₹{combined.get('max_loss', 0):,.0f}</div>
                <div class="stat-label">Max Loss</div>
            </div>
        </div>
        
        <h2>🎯 Strategy Metrics</h2>
        <div class="summary-grid">
            <div class="stat-card">
                <div class="stat-value">{combined.get('avg_duration', 0):.0f}m</div>
                <div class="stat-label">Avg Duration</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{combined.get('trades_hit_breakeven', 0)}</div>
                <div class="stat-label">Hit Breakeven</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{combined.get('trades_with_trailing', 0)}</div>
                <div class="stat-label">Trailing Active</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{combined.get('profitable_days', 0)}/{combined.get('days_tested', 0)}</div>
                <div class="stat-label">Profitable Days</div>
            </div>
        </div>
        
        <h2>📋 Exit Breakdown</h2>
        <div class="exit-breakdown">
            {''.join(f'<div class="exit-chip">{reason}: {count}</div>' for reason, count in combined.get('exit_breakdown', {}).items())}
        </div>
        
        <h2>📈 Trade Details</h2>
        <table>
            <tr>
                <th>Entry Time</th>
                <th>Type</th>
                <th>Strike</th>
                <th>Entry</th>
                <th>Exit</th>
                <th>P&L</th>
                <th>Exit Reason</th>
                <th>Duration</th>
            </tr>
            {trades_html}
        </table>
        
        <p style="text-align: center; color: #666; margin-top: 40px;">
            Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Strategy Lab
        </p>
    </div>
</body>
</html>
"""
    
    with open(output_path, 'w') as f:
        f.write(html)


def main():
    parser = argparse.ArgumentParser(description='Gamma-EMA Confluence Strategy Backtest')
    parser.add_argument('--symbol', type=str, default='NIFTY',
                        help='Symbol (NIFTY, SENSEX, or "all")')
    parser.add_argument('--verbose', '-v', action='store_true', default=True,
                        help='Verbose output')
    
    args = parser.parse_args()
    
    if args.symbol.lower() == 'all':
        symbols = ['NIFTY', 'SENSEX']
    else:
        symbols = [args.symbol.upper()]
    
    for symbol in symbols:
        run_gamma_backtest(symbol, args.verbose)


if __name__ == "__main__":
    main()
