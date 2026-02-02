#!/usr/bin/env python3
"""
Strategy Optimization Analysis
================================
Analyze trades to find optimal parameters.
"""
import pandas as pd
import numpy as np
from pathlib import Path

# Load trade data
nifty_trades = pd.read_csv("/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping/strategy_lab/reports/Gamma_EMA_NIFTY_20260131_121931/trades.csv")
sensex_trades = pd.read_csv("/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping/strategy_lab/reports/Gamma_EMA_SENSEX_20260131_121950/trades.csv")

print("="*70)
print("         GAMMA-EMA STRATEGY OPTIMIZATION ANALYSIS")
print("="*70)

# Combine all trades
all_trades = pd.concat([nifty_trades, sensex_trades], ignore_index=True)

print(f"\n📊 TOTAL TRADES ANALYZED: {len(all_trades)}")

# 1. Analysis by Exit Reason
print("\n" + "="*50)
print("📋 EXIT REASON ANALYSIS")
print("="*50)

exit_analysis = all_trades.groupby('exit_reason').agg({
    'pnl': ['count', 'sum', 'mean'],
    'pnl_pct': 'mean',
    'max_profit_pct': 'mean'
}).round(2)

exit_analysis.columns = ['Count', 'Total P&L', 'Avg P&L', 'Avg P&L%', 'Avg Max Profit%']
exit_analysis = exit_analysis.sort_values('Total P&L', ascending=False)
print(exit_analysis.to_string())

# 2. What if we used different RR targets?
print("\n" + "="*50)
print("🎯 RISK-REWARD RATIO ANALYSIS")
print("="*50)
print("\nSimulating different Target RR ratios (keeping 25% SL):")

# Current strategy uses 25% SL, so risk = 25% of entry
# For different RRs, target = entry * (1 + 0.25 * RR)

rr_results = []
for rr in [2, 2.5, 3, 3.5, 4, 5, 6]:
    # Calculate what target percentage would be hit given max_profit_pct
    target_pct = 25 * rr  # e.g., RR=3 means 75% target
    
    hits_target = all_trades[all_trades['max_profit_pct'] >= target_pct]
    hits_sl = all_trades[all_trades['max_loss_pct'] <= -25]
    
    # Calculate simulated results
    wins = len(hits_target)
    losses = len(all_trades) - wins
    
    # Estimate P&L (simplified)
    # Winners get target_pct * avg_entry_price * lot_size
    avg_entry = all_trades['entry_price'].mean()
    win_pnl = wins * (target_pct/100 * avg_entry * 25)  # 25 lot size
    loss_pnl = losses * (0.25 * avg_entry * 25)  # 25% loss
    
    total_pnl = win_pnl - loss_pnl
    win_rate = wins / len(all_trades) * 100
    
    rr_results.append({
        'RR': rr,
        'Target%': f"{target_pct:.0f}%",
        'Wins': wins,
        'Losses': losses,
        'Win Rate': f"{win_rate:.1f}%",
        'Est. P&L': f"₹{total_pnl:,.0f}",
        'Would Be': "✓" if total_pnl > 0 else "✗"
    })

rr_df = pd.DataFrame(rr_results)
print(rr_df.to_string(index=False))

# 3. Analyze max_profit_pct to understand potential
print("\n" + "="*50)
print("📈 MAXIMUM PROFIT POTENTIAL ANALYSIS")
print("="*50)

print(f"\nTrades by Max Profit % reached:")
ranges = [(0, 25), (25, 50), (50, 75), (75, 100), (100, float('inf'))]
for low, high in ranges:
    count = len(all_trades[(all_trades['max_profit_pct'] >= low) & (all_trades['max_profit_pct'] < high)])
    pct = count / len(all_trades) * 100
    label = f"{low}-{high}%" if high != float('inf') else f"{low}%+"
    print(f"  {label:>10}: {count:3} trades ({pct:.1f}%)")

# 4. Time analysis - When do best trades happen?
print("\n" + "="*50)
print("⏰ ENTRY TIME ANALYSIS")
print("="*50)

all_trades['entry_hour'] = pd.to_datetime(all_trades['entry_time']).dt.hour
time_analysis = all_trades.groupby('entry_hour').agg({
    'pnl': ['count', 'sum', 'mean']
}).round(2)
time_analysis.columns = ['Trades', 'Total P&L', 'Avg P&L']
print(time_analysis.to_string())

# 5. Duration analysis
print("\n" + "="*50)
print("⏱️ TRADE DURATION ANALYSIS")
print("="*50)

winners = all_trades[all_trades['pnl'] > 0]
losers = all_trades[all_trades['pnl'] < 0]

print(f"Winners avg duration: {winners['duration_minutes'].mean():.0f} mins")
print(f"Losers avg duration:  {losers['duration_minutes'].mean():.0f} mins")

# 6. RECOMMENDATIONS
print("\n" + "="*70)
print("💡 OPTIMIZATION RECOMMENDATIONS")
print("="*70)

print("""
1. REDUCE TARGET (Use 1:3 or 1:2.5 RR instead of 1:4):
   - Only 1.9% of trades hit the 1:4 target
   - Many trades showed 50-75% max profit but exited at time_exit
   - With 1:3 RR (75% target), win rate could improve significantly

2. EXPAND ENTRY WINDOW:
   - Current: 13:30 - 15:15 (105 mins)
   - Consider: 12:00 - 15:15 (195 mins) for more signals
   - Morning scalps (09:30-10:30) could add more trades

3. REDUCE SIDEWAYS EXIT THRESHOLD:
   - 18% of trades exited due to sideways movement
   - Keeping positions longer could allow them to hit target

4. MULTIPLE LOT SCALING:
   - Book partial profits at 1:2 RR
   - Let remaining position run for 1:4 target

5. FILTER BY MAX PROFIT POTENTIAL:
   - 42% of trades reached 50%+ max profit
   - Add momentum filter to select higher-potential setups

6. EARLIER ENTRY TIMING:
   - 14:00 hour has highest avg P&L
   - Focus signals between 13:45 - 14:30
""")

# 7. Best scenario calculation
print("\n" + "="*50)
print("🏆 OPTIMAL CONFIGURATION ESTIMATE")
print("="*50)

# Simulate 1:3 RR
target_pct = 75  # 1:3 RR
hits_target = len(all_trades[all_trades['max_profit_pct'] >= target_pct])
win_rate_3rr = hits_target / len(all_trades) * 100
avg_entry = all_trades['entry_price'].mean()
est_pnl = hits_target * (target_pct/100 * avg_entry * 25) - (len(all_trades) - hits_target) * (0.25 * avg_entry * 25)

print(f"""
With 1:3 RR (75% target, 25% SL):
  - Estimated Win Rate: {win_rate_3rr:.1f}%
  - Estimated Trades Hitting Target: {hits_target}
  - Estimated P&L: ₹{est_pnl:,.0f}
  
vs Current 1:4 RR:
  - Actual Win Rate: 39.9%
  - Actual P&L: ₹42,638 (combined)
""")
