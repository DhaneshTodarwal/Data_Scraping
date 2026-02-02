"""
Batch Runner for Multi-Symbol, Multi-Strategy Backtesting
===========================================================
Runs all strategies across all symbols and generates comprehensive results
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import json
import sys
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent))

from historical_data_loader import HistoricalDataLoader, get_expiry_dates_for_backtest
from config import BACKTEST_OUTPUT, NIFTY_LOT_SIZE, BANKNIFTY_LOT_SIZE
from backtest.strategies import ALL_STRATEGIES, get_strategy, list_strategies


# Lot sizes for each symbol
LOT_SIZES = {
    'NIFTY': 75,
    'BANKNIFTY': 30,
    'FINNIFTY': 65,
    'MIDCAPNIFTY': 100,
    'SENSEX': 20,
}


class BatchBacktester:
    """Run backtests across multiple strategies and symbols"""
    
    def __init__(self, initial_capital: float = 1000000):
        self.initial_capital = initial_capital
        self.loader = HistoricalDataLoader()
        self.results = []
    
    def run_all(self, symbols: List[str] = None, strategies: List[str] = None,
                year: int = None, max_days_per_symbol: int = None) -> pd.DataFrame:
        """
        Run all combinations of strategies and symbols
        """
        symbols = symbols or list(LOT_SIZES.keys())
        strategies = strategies or list(ALL_STRATEGIES.keys())
        
        print("="*70)
        print("           BATCH BACKTESTING - ALL STRATEGIES & SYMBOLS")
        print("="*70)
        print(f"\nSymbols:    {symbols}")
        print(f"Strategies: {strategies}")
        print(f"Year:       {year or 'All'}")
        print("="*70)
        
        all_results = []
        
        for symbol in symbols:
            # Check if symbol has data
            available = self.loader.get_available_symbols(2024)
            if symbol not in available:
                print(f"\n⚠ {symbol}: No data available, skipping...")
                continue
            
            for strategy_name in strategies:
                print(f"\n▶ Testing {strategy_name.upper()} on {symbol}...", end=" ")
                
                try:
                    strategy = get_strategy(strategy_name)
                    result = self._run_single_backtest(
                        symbol, strategy, year, max_days_per_symbol
                    )
                    
                    if result:
                        all_results.append(result)
                        status = "✓" if result['total_pnl'] >= 0 else "✗"
                        print(f"{status} Days={result['total_days']}, "
                              f"WinRate={result['win_rate']:.0f}%, "
                              f"PnL=₹{result['total_pnl']:,.0f}")
                    else:
                        print("⚠ No trades")
                        
                except Exception as e:
                    print(f"❌ Error: {str(e)[:40]}")
        
        # Convert to DataFrame
        results_df = pd.DataFrame(all_results)
        self.results = results_df
        
        return results_df
    
    def _run_single_backtest(self, symbol: str, strategy, year: int = None,
                             max_days: int = None) -> Optional[Dict]:
        """Run backtest for a single symbol/strategy combination"""
        
        lot_size = LOT_SIZES.get(symbol, 50)
        
        # Get available expiry dates
        all_dates = get_expiry_dates_for_backtest(symbol, year)
        if max_days:
            all_dates = all_dates[:max_days]
        
        if not all_dates:
            return None
        
        day_results = []
        all_trades = []
        
        for year_val, month, day in all_dates:
            try:
                result = self._backtest_single_day(
                    symbol, strategy, year_val, month, day, lot_size
                )
                if result:
                    day_results.append(result)
                    all_trades.extend(result.get('trades', []))
            except Exception:
                pass
        
        if not day_results:
            return None
        
        # Calculate summary
        total_trades = len(all_trades)
        winners = sum(1 for t in all_trades if t['pnl'] > 0)
        total_pnl = sum(t['pnl'] for t in all_trades)
        
        return {
            'symbol': symbol,
            'strategy': strategy.name,
            'strategy_key': [k for k, v in ALL_STRATEGIES.items() if v.name == strategy.name][0],
            'total_days': len(day_results),
            'total_trades': total_trades,
            'winners': winners,
            'losers': total_trades - winners,
            'win_rate': (winners / total_trades * 100) if total_trades > 0 else 0,
            'total_pnl': total_pnl,
            'avg_pnl_per_trade': total_pnl / total_trades if total_trades > 0 else 0,
            'max_win': max((t['pnl'] for t in all_trades), default=0),
            'max_loss': min((t['pnl'] for t in all_trades), default=0),
            'profit_factor': self._calc_profit_factor(all_trades),
        }
    
    def _backtest_single_day(self, symbol: str, strategy, year: int, 
                             month: str, day: int, lot_size: int) -> Optional[Dict]:
        """Backtest a single day"""
        
        strikes_data = self.loader.load_expiry_day_data(year, symbol, month, day)
        
        if not strikes_data['CE'] and not strikes_data['PE']:
            return None
        
        # Get sample dataframe for timestamps
        sample_df = None
        for ot in ['CE', 'PE']:
            if strikes_data[ot]:
                sample_df = list(strikes_data[ot].values())[0]
                break
        
        if sample_df is None or sample_df.empty:
            return None
        
        # Filter to expiry day only
        expiry_date = sample_df['timestamp'].dt.date.max()
        for ot in ['CE', 'PE']:
            for strike in list(strikes_data[ot].keys()):
                df = strikes_data[ot][strike]
                strikes_data[ot][strike] = df[df['timestamp'].dt.date == expiry_date].copy()
        
        # Get filtered sample
        sample_df = None
        for ot in ['CE', 'PE']:
            if strikes_data[ot]:
                first_key = list(strikes_data[ot].keys())[0]
                sample_df = strikes_data[ot][first_key]
                break
        
        if sample_df is None or sample_df.empty:
            return None
        
        trades = []
        active_trade = None
        entry_premium = 0
        
        # Get spot estimate
        all_strikes = set()
        for ot in ['CE', 'PE']:
            all_strikes.update(strikes_data[ot].keys())
        
        if not all_strikes:
            return None
        
        spot_estimate = sorted(all_strikes)[len(all_strikes) // 2]
        
        for _, row in sample_df.iterrows():
            timestamp = row['timestamp']
            
            if active_trade is None:
                # Look for entry
                signal = strategy.get_entry_signal(spot_estimate, strikes_data, timestamp)
                
                if signal:
                    active_trade = signal.copy()
                    active_trade['entry_time'] = timestamp
                    
                    # Calculate entry premium based on strategy type
                    entry_premium = self._get_entry_premium(
                        strikes_data, signal, timestamp
                    )
                    
                    if entry_premium is None or entry_premium <= 0:
                        active_trade = None
            else:
                # Check for exit
                current_premium = self._get_current_premium(
                    strikes_data, active_trade, timestamp
                )
                
                if current_premium is None:
                    continue
                
                # Calculate PnL %
                if active_trade['direction'] == 'SELL':
                    pnl_pct = ((entry_premium - current_premium) / entry_premium) * 100
                else:
                    pnl_pct = ((current_premium - entry_premium) / entry_premium) * 100
                
                exit_reason = strategy.get_exit_signal(active_trade, pnl_pct, timestamp)
                
                if exit_reason:
                    pnl_points = entry_premium - current_premium if active_trade['direction'] == 'SELL' else current_premium - entry_premium
                    pnl_amount = pnl_points * lot_size
                    
                    trades.append({
                        'entry_time': str(active_trade['entry_time']),
                        'exit_time': str(timestamp),
                        'pnl': pnl_amount,
                        'exit_reason': exit_reason,
                    })
                    
                    active_trade = None
        
        return {'trades': trades} if trades else None
    
    def _get_entry_premium(self, strikes_data: Dict, signal: Dict, 
                           timestamp: pd.Timestamp) -> Optional[float]:
        """Calculate entry premium for a signal"""
        strategy_type = signal.get('type', '')
        
        if strategy_type == 'STRADDLE':
            strike = signal['strike']
            ce = self._get_price(strikes_data, 'CE', strike, timestamp)
            pe = self._get_price(strikes_data, 'PE', strike, timestamp)
            return (ce + pe) if ce and pe else None
        
        elif strategy_type == 'STRANGLE':
            ce = self._get_price(strikes_data, 'CE', signal['ce_strike'], timestamp)
            pe = self._get_price(strikes_data, 'PE', signal['pe_strike'], timestamp)
            return (ce + pe) if ce and pe else None
        
        elif strategy_type == 'IRON_CONDOR':
            short_ce = self._get_price(strikes_data, 'CE', signal['short_ce'], timestamp)
            long_ce = self._get_price(strikes_data, 'CE', signal['long_ce'], timestamp)
            short_pe = self._get_price(strikes_data, 'PE', signal['short_pe'], timestamp)
            long_pe = self._get_price(strikes_data, 'PE', signal['long_pe'], timestamp)
            if all([short_ce, long_ce, short_pe, long_pe]):
                return (short_ce - long_ce) + (short_pe - long_pe)
            return None
        
        elif strategy_type == 'IRON_BUTTERFLY':
            atm = signal['atm_strike']
            ce = self._get_price(strikes_data, 'CE', atm, timestamp)
            pe = self._get_price(strikes_data, 'PE', atm, timestamp)
            wing_ce = self._get_price(strikes_data, 'CE', signal['wing_ce'], timestamp)
            wing_pe = self._get_price(strikes_data, 'PE', signal['wing_pe'], timestamp)
            if all([ce, pe, wing_ce, wing_pe]):
                return (ce + pe) - (wing_ce + wing_pe)
            return None
        
        elif strategy_type == 'BULL_PUT_SPREAD':
            short = self._get_price(strikes_data, 'PE', signal['short_pe'], timestamp)
            long = self._get_price(strikes_data, 'PE', signal['long_pe'], timestamp)
            return (short - long) if short and long else None
        
        elif strategy_type == 'BEAR_CALL_SPREAD':
            short = self._get_price(strikes_data, 'CE', signal['short_ce'], timestamp)
            long = self._get_price(strikes_data, 'CE', signal['long_ce'], timestamp)
            return (short - long) if short and long else None
        
        return None
    
    def _get_current_premium(self, strikes_data: Dict, trade: Dict,
                             timestamp: pd.Timestamp) -> Optional[float]:
        """Get current premium for active trade"""
        return self._get_entry_premium(strikes_data, trade, timestamp)
    
    def _get_price(self, strikes_data: Dict, option_type: str, strike: int,
                   timestamp: pd.Timestamp) -> Optional[float]:
        """Get option price at timestamp"""
        if strike not in strikes_data.get(option_type, {}):
            return None
        
        df = strikes_data[option_type][strike]
        row = df[df['timestamp'] == timestamp]
        
        if row.empty:
            df_sorted = df.iloc[(df['timestamp'] - timestamp).abs().argsort()[:1]]
            return df_sorted['close'].iloc[0] if not df_sorted.empty else None
        
        return row['close'].iloc[0]
    
    def _calc_profit_factor(self, trades: List[Dict]) -> float:
        """Calculate profit factor"""
        gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
        return gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    def save_results(self, name: str = None):
        """Save batch results"""
        if self.results.empty:
            print("No results to save")
            return
        
        name = name or f"batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        output_dir = BACKTEST_OUTPUT / "batch" / name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save full results
        self.results.to_csv(output_dir / 'all_results.csv', index=False)
        
        # Create summary by strategy
        strategy_summary = self.results.groupby('strategy').agg({
            'total_days': 'sum',
            'total_trades': 'sum',
            'winners': 'sum',
            'total_pnl': 'sum',
            'win_rate': 'mean',
            'profit_factor': 'mean',
        }).round(2)
        strategy_summary.to_csv(output_dir / 'strategy_summary.csv')
        
        # Create summary by symbol
        symbol_summary = self.results.groupby('symbol').agg({
            'total_days': 'sum',
            'total_trades': 'sum',
            'winners': 'sum',
            'total_pnl': 'sum',
            'win_rate': 'mean',
            'profit_factor': 'mean',
        }).round(2)
        symbol_summary.to_csv(output_dir / 'symbol_summary.csv')
        
        print(f"\nResults saved to: {output_dir}")
        
        return output_dir
    
    def print_summary(self):
        """Print summary of batch results"""
        if self.results.empty:
            print("No results available")
            return
        
        print("\n" + "="*70)
        print("                    BATCH BACKTEST SUMMARY")
        print("="*70)
        
        # Best strategies
        print("\n📊 TOP STRATEGIES BY TOTAL P&L:")
        top = self.results.nlargest(5, 'total_pnl')[['strategy', 'symbol', 'win_rate', 'total_pnl', 'profit_factor']]
        print(top.to_string(index=False))
        
        # By symbol
        print("\n📍 PERFORMANCE BY SYMBOL:")
        by_symbol = self.results.groupby('symbol').agg({
            'total_pnl': 'sum',
            'win_rate': 'mean',
        }).round(1)
        print(by_symbol.to_string())
        
        # By strategy
        print("\n🎯 PERFORMANCE BY STRATEGY:")
        by_strategy = self.results.groupby('strategy').agg({
            'total_pnl': 'sum',
            'win_rate': 'mean',
        }).round(1).sort_values('total_pnl', ascending=False)
        print(by_strategy.to_string())
        
        print("\n" + "="*70)


def run_batch_backtest(symbols: List[str] = None, strategies: List[str] = None,
                       year: int = None, max_days: int = None):
    """Convenience function to run batch backtest"""
    
    batch = BatchBacktester()
    results = batch.run_all(
        symbols=symbols,
        strategies=strategies,
        year=year,
        max_days_per_symbol=max_days
    )
    
    batch.print_summary()
    output_dir = batch.save_results()
    
    return results, output_dir


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Batch Backtester')
    parser.add_argument('--symbols', type=str, nargs='+', default=None,
                        help='Symbols to test (default: all)')
    parser.add_argument('--strategies', type=str, nargs='+', default=None,
                        help='Strategies to test (default: all)')
    parser.add_argument('--year', type=int, default=2024, help='Year to backtest')
    parser.add_argument('--max-days', type=int, default=None, help='Max days per symbol')
    parser.add_argument('--list-strategies', action='store_true', help='List available strategies')
    
    args = parser.parse_args()
    
    if args.list_strategies:
        print("\nAvailable Strategies:")
        for key, name in list_strategies():
            print(f"  {key:20s} -> {name}")
        exit()
    
    run_batch_backtest(
        symbols=args.symbols,
        strategies=args.strategies,
        year=args.year,
        max_days=args.max_days
    )
