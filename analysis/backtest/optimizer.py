"""
Strategy Optimizer
===================
Finds optimal parameters for each strategy using grid search
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from itertools import product
import json
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from historical_data_loader import HistoricalDataLoader, get_expiry_dates_for_backtest
from config import BACKTEST_OUTPUT, NIFTY_LOT_SIZE, BANKNIFTY_LOT_SIZE
from backtest.strategies import (
    ShortStraddleStrategy, ShortStrangleStrategy, 
    IronCondorStrategy, IronButterflyStrategy,
    BullPutSpreadStrategy, BearCallSpreadStrategy,
    BaseStrategy
)


class StrategyOptimizer:
    """Find optimal parameters for trading strategies"""
    
    def __init__(self, symbol: str = 'NIFTY', year: int = 2024):
        self.symbol = symbol
        self.year = year
        self.loader = HistoricalDataLoader()
        self.lot_size = NIFTY_LOT_SIZE if 'NIFTY' in symbol else BANKNIFTY_LOT_SIZE
        self.results = []
    
    def optimize_straddle(self, max_days: int = None) -> pd.DataFrame:
        """
        Optimize Short Straddle parameters
        Grid search over: entry_time, sl_pct, target_pct
        """
        print("\n" + "="*60)
        print("OPTIMIZING SHORT STRADDLE")
        print("="*60)
        
        # Parameter grid
        entry_times = ['09:30', '09:45', '10:00', '10:15', '10:30', '11:00']
        sl_pcts = [20, 25, 30, 35, 40]
        target_pcts = [30, 40, 50, 60, 70]
        
        results = []
        total = len(entry_times) * len(sl_pcts) * len(target_pcts)
        
        for i, (entry, sl, target) in enumerate(product(entry_times, sl_pcts, target_pcts)):
            print(f"\r[{i+1}/{total}] Testing Entry={entry}, SL={sl}%, Target={target}%...", end="")
            
            strategy = ShortStraddleStrategy(
                entry_time=entry, sl_pct=sl, target_pct=target
            )
            
            stats = self._run_backtest(strategy, max_days)
            if stats:
                results.append({
                    'entry_time': entry,
                    'sl_pct': sl,
                    'target_pct': target,
                    **stats
                })
        
        print()
        
        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values('total_pnl', ascending=False)
        
        self._save_results(df, 'straddle')
        return df
    
    def optimize_strangle(self, max_days: int = None) -> pd.DataFrame:
        """
        Optimize Short Strangle parameters
        Grid search over: entry_time, otm_distance, sl_pct, target_pct
        """
        print("\n" + "="*60)
        print("OPTIMIZING SHORT STRANGLE")
        print("="*60)
        
        entry_times = ['09:30', '09:45', '10:15']
        otm_distances = [1, 2, 3, 4]
        sl_pcts = [30, 40, 50]
        target_pcts = [30, 40, 50]
        
        results = []
        total = len(entry_times) * len(otm_distances) * len(sl_pcts) * len(target_pcts)
        
        for i, (entry, otm, sl, target) in enumerate(product(entry_times, otm_distances, sl_pcts, target_pcts)):
            print(f"\r[{i+1}/{total}] Testing Entry={entry}, OTM={otm}, SL={sl}%, Target={target}%...", end="")
            
            strategy = ShortStrangleStrategy(
                entry_time=entry, otm_distance=otm, sl_pct=sl, target_pct=target
            )
            
            stats = self._run_backtest(strategy, max_days)
            if stats:
                results.append({
                    'entry_time': entry,
                    'otm_distance': otm,
                    'sl_pct': sl,
                    'target_pct': target,
                    **stats
                })
        
        print()
        
        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values('total_pnl', ascending=False)
        
        self._save_results(df, 'strangle')
        return df
    
    def optimize_iron_condor(self, max_days: int = None) -> pd.DataFrame:
        """
        Optimize Iron Condor parameters
        """
        print("\n" + "="*60)
        print("OPTIMIZING IRON CONDOR")
        print("="*60)
        
        entry_times = ['09:30', '09:45', '10:15']
        short_distances = [1, 2, 3]
        long_distances_diff = [1, 2, 3]  # Added to short distance
        sl_pcts = [40, 50, 60]
        target_pcts = [40, 50, 60]
        
        results = []
        
        for entry, short, diff, sl, target in product(entry_times, short_distances, long_distances_diff, sl_pcts, target_pcts):
            long = short + diff
            
            strategy = IronCondorStrategy(
                entry_time=entry, short_distance=short, long_distance=long,
                sl_pct=sl, target_pct=target
            )
            
            stats = self._run_backtest(strategy, max_days)
            if stats:
                results.append({
                    'entry_time': entry,
                    'short_distance': short,
                    'long_distance': long,
                    'sl_pct': sl,
                    'target_pct': target,
                    **stats
                })
        
        df = pd.DataFrame(results)
        if not df.empty:
            df = df.sort_values('total_pnl', ascending=False)
        
        self._save_results(df, 'iron_condor')
        return df
    
    def _run_backtest(self, strategy: BaseStrategy, max_days: int = None) -> Optional[Dict]:
        """Run backtest and return statistics"""
        
        all_dates = get_expiry_dates_for_backtest(self.symbol, self.year)
        if max_days:
            all_dates = all_dates[:max_days]
        
        if not all_dates:
            return None
        
        total_pnl = 0
        trades = []
        
        for year, month, day in all_dates:
            try:
                day_trades = self._backtest_day(strategy, year, month, day)
                trades.extend(day_trades)
            except Exception:
                pass
        
        if not trades:
            return None
        
        total_pnl = sum(t['pnl'] for t in trades)
        winners = sum(1 for t in trades if t['pnl'] > 0)
        
        return {
            'total_trades': len(trades),
            'winners': winners,
            'win_rate': (winners / len(trades) * 100) if trades else 0,
            'total_pnl': total_pnl,
            'avg_pnl': total_pnl / len(trades) if trades else 0,
            'profit_factor': self._calc_profit_factor(trades),
        }
    
    def _backtest_day(self, strategy: BaseStrategy, year: int, 
                      month: str, day: int) -> List[Dict]:
        """Backtest a single day"""
        
        strikes_data = self.loader.load_expiry_day_data(year, self.symbol, month, day)
        
        if not strikes_data['CE'] and not strikes_data['PE']:
            return []
        
        sample_df = None
        for ot in ['CE', 'PE']:
            if strikes_data[ot]:
                sample_df = list(strikes_data[ot].values())[0]
                break
        
        if sample_df is None or sample_df.empty:
            return []
        
        # Filter to expiry day
        expiry_date = sample_df['timestamp'].dt.date.max()
        for ot in ['CE', 'PE']:
            for strike in list(strikes_data[ot].keys()):
                df = strikes_data[ot][strike]
                strikes_data[ot][strike] = df[df['timestamp'].dt.date == expiry_date].copy()
        
        sample_df = None
        for ot in ['CE', 'PE']:
            if strikes_data[ot]:
                sample_df = list(strikes_data[ot].values())[0]
                break
        
        if sample_df is None or sample_df.empty:
            return []
        
        trades = []
        active_trade = None
        entry_premium = 0
        
        all_strikes = set()
        for ot in ['CE', 'PE']:
            all_strikes.update(strikes_data[ot].keys())
        
        if not all_strikes:
            return []
        
        spot_estimate = sorted(all_strikes)[len(all_strikes) // 2]
        
        for _, row in sample_df.iterrows():
            timestamp = row['timestamp']
            
            if active_trade is None:
                signal = strategy.get_entry_signal(spot_estimate, strikes_data, timestamp)
                
                if signal:
                    active_trade = signal.copy()
                    active_trade['entry_time'] = timestamp
                    entry_premium = self._get_entry_premium(strikes_data, signal, timestamp)
                    
                    if entry_premium is None or entry_premium <= 0:
                        active_trade = None
            else:
                current_premium = self._get_entry_premium(strikes_data, active_trade, timestamp)
                
                if current_premium is None:
                    continue
                
                if active_trade.get('direction') == 'SELL':
                    pnl_pct = ((entry_premium - current_premium) / entry_premium) * 100
                else:
                    pnl_pct = ((current_premium - entry_premium) / entry_premium) * 100
                
                exit_reason = strategy.get_exit_signal(active_trade, pnl_pct, timestamp)
                
                if exit_reason:
                    pnl_points = entry_premium - current_premium if active_trade.get('direction') == 'SELL' else current_premium - entry_premium
                    pnl_amount = pnl_points * self.lot_size
                    trades.append({'pnl': pnl_amount, 'exit_reason': exit_reason})
                    active_trade = None
        
        return trades
    
    def _get_entry_premium(self, strikes_data: Dict, signal: Dict, 
                           timestamp: pd.Timestamp) -> Optional[float]:
        """Calculate entry premium"""
        strategy_type = signal.get('type', '')
        
        def get_price(ot, strike):
            if strike not in strikes_data.get(ot, {}):
                return None
            df = strikes_data[ot][strike]
            row = df[df['timestamp'] == timestamp]
            if row.empty:
                df_sorted = df.iloc[(df['timestamp'] - timestamp).abs().argsort()[:1]]
                return df_sorted['close'].iloc[0] if not df_sorted.empty else None
            return row['close'].iloc[0]
        
        if strategy_type == 'STRADDLE':
            ce = get_price('CE', signal['strike'])
            pe = get_price('PE', signal['strike'])
            return (ce + pe) if ce and pe else None
        
        elif strategy_type == 'STRANGLE':
            ce = get_price('CE', signal['ce_strike'])
            pe = get_price('PE', signal['pe_strike'])
            return (ce + pe) if ce and pe else None
        
        elif strategy_type == 'IRON_CONDOR':
            short_ce = get_price('CE', signal['short_ce'])
            long_ce = get_price('CE', signal['long_ce'])
            short_pe = get_price('PE', signal['short_pe'])
            long_pe = get_price('PE', signal['long_pe'])
            if all([short_ce, long_ce, short_pe, long_pe]):
                return (short_ce - long_ce) + (short_pe - long_pe)
            return None
        
        elif strategy_type == 'IRON_BUTTERFLY':
            ce = get_price('CE', signal['atm_strike'])
            pe = get_price('PE', signal['atm_strike'])
            wing_ce = get_price('CE', signal['wing_ce'])
            wing_pe = get_price('PE', signal['wing_pe'])
            if all([ce, pe, wing_ce, wing_pe]):
                return (ce + pe) - (wing_ce + wing_pe)
            return None
        
        return None
    
    def _calc_profit_factor(self, trades: List[Dict]) -> float:
        """Calculate profit factor"""
        gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
        return gross_profit / gross_loss if gross_loss > 0 else float('inf')
    
    def _save_results(self, df: pd.DataFrame, strategy_name: str):
        """Save optimization results"""
        if df.empty:
            return
        
        output_dir = BACKTEST_OUTPUT / "optimization" / self.symbol
        output_dir.mkdir(parents=True, exist_ok=True)
        
        filename = f"{strategy_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        df.to_csv(output_dir / filename, index=False)
        print(f"\n📁 Saved to: {output_dir / filename}")
    
    def print_best_params(self, df: pd.DataFrame, top_n: int = 5):
        """Print best parameter combinations"""
        if df.empty:
            print("No results to show")
            return
        
        print("\n" + "="*70)
        print(f"TOP {top_n} PARAMETER COMBINATIONS")
        print("="*70)
        
        top = df.head(top_n)
        for i, row in top.iterrows():
            win_rate = row.get('win_rate', 0)
            pnl = row.get('total_pnl', 0)
            pf = row.get('profit_factor', 0)
            
            params = {k: v for k, v in row.items() 
                     if k not in ['total_trades', 'winners', 'win_rate', 'total_pnl', 'avg_pnl', 'profit_factor']}
            
            print(f"\n#{i+1}: P&L=₹{pnl:,.0f} | WinRate={win_rate:.0f}% | PF={pf:.2f}")
            print(f"   Params: {params}")


def run_optimization(symbol: str = 'NIFTY', strategy: str = 'straddle',
                     year: int = 2024, max_days: int = None):
    """Run optimization for a specific strategy"""
    
    optimizer = StrategyOptimizer(symbol, year)
    
    if strategy == 'straddle':
        df = optimizer.optimize_straddle(max_days)
    elif strategy == 'strangle':
        df = optimizer.optimize_strangle(max_days)
    elif strategy == 'iron_condor':
        df = optimizer.optimize_iron_condor(max_days)
    else:
        print(f"Unknown strategy: {strategy}")
        return None
    
    optimizer.print_best_params(df)
    return df


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Strategy Optimizer')
    parser.add_argument('--symbol', type=str, default='NIFTY', help='Symbol to optimize')
    parser.add_argument('--strategy', type=str, default='straddle',
                        choices=['straddle', 'strangle', 'iron_condor'],
                        help='Strategy to optimize')
    parser.add_argument('--year', type=int, default=2024, help='Year to use')
    parser.add_argument('--max-days', type=int, default=None, help='Max days to test')
    
    args = parser.parse_args()
    
    run_optimization(
        symbol=args.symbol,
        strategy=args.strategy,
        year=args.year,
        max_days=args.max_days
    )
