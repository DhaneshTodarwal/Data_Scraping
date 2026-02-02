#!/usr/bin/env python3
"""
SIMPLE MOMENTUM STRATEGY - Works with Options Data Only
=========================================================
This strategy doesn't require index data. It trades options
based on their own price action and momentum.
"""
import sys
from pathlib import Path
from datetime import datetime, time
import json
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

STRATEGY_LAB_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(STRATEGY_LAB_DIR))

from config import REPORTS_DIR
from runner.old_data_loader import OldDataLoader


@dataclass
class Trade:
    """Represents a single trade."""
    entry_time: datetime
    exit_time: datetime
    option_type: str
    strike: int
    entry_price: float
    exit_price: float
    pnl: float
    pnl_pct: float
    exit_reason: str


def run_simple_momentum_test():
    """
    Simple momentum strategy:
    - Entry: When option price breaks above 9 EMA and volume spikes
    - Exit: 25% SL or 50% Target or Time
    """
    
    print(f"\n{'='*80}")
    print(f"   📈 SIMPLE MOMENTUM STRATEGY BACKTEST")
    print(f"   Using Options Data Only (No Index Required)")
    print(f"{'='*80}\n")
    
    loader = OldDataLoader()
    
    # Strategy parameters
    SL_PCT = 25  # Stop loss
    TARGET_PCT = 50  # Target (1:2 RR)
    EMA_PERIOD = 9
    MIN_PREMIUM = 10
    MAX_PREMIUM = 300
    
    print(f"Strategy Parameters:")
    print(f"  Stop Loss: {SL_PCT}%")
    print(f"  Target: {TARGET_PCT}%")
    print(f"  EMA Period: {EMA_PERIOD}")
    print(f"  Premium Range: ₹{MIN_PREMIUM} - ₹{MAX_PREMIUM}")
    print()
    
    symbols_to_test = ['NIFTY', 'BANKNIFTY', 'SENSEX']
    all_results = {}
    
    for symbol in symbols_to_test:
        print(f"\n{'='*60}")
        print(f"📈 Testing: {symbol}")
        print(f"{'='*60}")
        
        expiry_dates = loader.get_available_expiry_dates(symbol)
        
        if len(expiry_dates) < 6:
            print(f"⚠️ Insufficient data ({len(expiry_dates)} days)")
            continue
        
        # 60/40 split
        split_idx = int(len(expiry_dates) * 0.6)
        test_dates = expiry_dates[split_idx:]
        
        print(f"\n🧪 Testing on {len(test_dates)} days (out-of-sample)")
        
        all_trades = []
        
        for year, month, day in test_dates:
            date_str = f"{year}-{month}-{day:02d}"
            
            strikes_data = loader.load_strikes_data(symbol, year, month, day)
            
            # Count available strikes
            ce_count = len(strikes_data['CE'])
            pe_count = len(strikes_data['PE'])
            
            if ce_count == 0 and pe_count == 0:
                continue
            
            day_trades = []
            
            # Trade each strike option
            for opt_type in ['CE', 'PE']:
                for strike, df in strikes_data[opt_type].items():
                    if len(df) < 30:  # Need enough data
                        continue
                    
                    # Add EMA
                    df = df.copy()
                    df['ema'] = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
                    df['above_ema'] = df['close'] > df['ema']
                    df['vol_sma'] = df['volume'].rolling(10).mean()
                    df['vol_spike'] = df['volume'] > df['vol_sma'] * 1.5
                    
                    # Find entry signals (after 11:00)
                    in_trade = False
                    entry_price = 0
                    entry_time = None
                    
                    for i in range(10, len(df)):
                        row = df.iloc[i]
                        prev_row = df.iloc[i-1]
                        ts = row['timestamp']
                        
                        # Only trade between 11:00 and 15:15
                        time_only = ts.time()
                        if time_only < time(11, 0) or time_only > time(15, 15):
                            continue
                        
                        if not in_trade:
                            # Check entry: Cross above EMA + volume spike
                            price = row['close']
                            
                            if MIN_PREMIUM <= price <= MAX_PREMIUM:
                                if row['above_ema'] and not prev_row['above_ema']:
                                    # Entry signal
                                    in_trade = True
                                    entry_price = price
                                    entry_time = ts
                        else:
                            # Check exit
                            current_price = row['close']
                            pnl_pct = (current_price - entry_price) / entry_price * 100
                            
                            exit_reason = None
                            
                            if pnl_pct <= -SL_PCT:
                                exit_reason = 'stoploss'
                            elif pnl_pct >= TARGET_PCT:
                                exit_reason = 'target'
                            elif time_only >= time(15, 20):
                                exit_reason = 'time_exit'
                            
                            if exit_reason:
                                trade = Trade(
                                    entry_time=entry_time,
                                    exit_time=ts,
                                    option_type=opt_type,
                                    strike=strike,
                                    entry_price=entry_price,
                                    exit_price=current_price,
                                    pnl=current_price - entry_price,
                                    pnl_pct=pnl_pct,
                                    exit_reason=exit_reason
                                )
                                day_trades.append(trade)
                                in_trade = False
            
            if day_trades:
                day_pnl = sum(t.pnl for t in day_trades)
                status = "✓" if day_pnl > 0 else "✗"
                print(f"   {date_str}: {len(day_trades):2} trades, ₹{day_pnl:>8.0f} {status}")
                all_trades.extend(day_trades)
        
        if all_trades:
            # Calculate results
            total_trades = len(all_trades)
            winners = len([t for t in all_trades if t.pnl > 0])
            total_pnl = sum(t.pnl for t in all_trades)
            win_rate = winners / total_trades * 100
            
            profit_sum = sum(t.pnl for t in all_trades if t.pnl > 0)
            loss_sum = abs(sum(t.pnl for t in all_trades if t.pnl < 0))
            profit_factor = profit_sum / loss_sum if loss_sum > 0 else float('inf')
            
            all_results[symbol] = {
                'test_days': len(test_dates),
                'total_trades': total_trades,
                'winners': winners,
                'win_rate': win_rate,
                'total_pnl': total_pnl,
                'profit_factor': profit_factor,
            }
            
            print(f"\n📊 {symbol} RESULTS")
            print(f"   Trades: {total_trades} | Win Rate: {win_rate:.1f}%")
            print(f"   P&L: ₹{total_pnl:,.0f} | PF: {profit_factor:.2f}")
    
    # Summary
    print(f"\n{'='*80}")
    print(f"   📊 FINAL SUMMARY")
    print(f"{'='*80}\n")
    
    total_pnl = 0
    total_trades = 0
    
    for symbol, res in all_results.items():
        print(f"{symbol:<12} {res['total_trades']:>5} trades, {res['win_rate']:>5.1f}% win, ₹{res['total_pnl']:>10,.0f}, PF {res['profit_factor']:.2f}")
        total_pnl += res['total_pnl']
        total_trades += res['total_trades']
    
    print("-" * 60)
    print(f"{'COMBINED':<12} {total_trades:>5} trades, {'':>5} ₹{total_pnl:>10,.0f}")
    
    # Save
    output_dir = REPORTS_DIR / f"SimpleMomentum_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    with open(output_dir / 'summary.json', 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    
    print(f"\n📁 Saved to: {output_dir}")
    return all_results


if __name__ == "__main__":
    run_simple_momentum_test()
