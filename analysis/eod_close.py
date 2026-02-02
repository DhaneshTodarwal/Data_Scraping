"""
End of Day Trade Closer
========================
Closes ALL open positions at 3:25 PM daily
and clears position tracker for fresh start next day

Rules:
1. All intraday trades MUST be closed by EOD
2. No carry-forward to next day
3. Sends summary of closed positions
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from notifications import send_telegram_message
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False

try:
    from paper_trading_platform import get_platform
    PAPER_OK = True
except ImportError:
    PAPER_OK = False


def close_all_positions():
    """Close all open positions at end of day with detailed summary"""
    
    if not PAPER_OK:
        print("❌ Paper trading module not available")
        return
    
    platform = get_platform()
    
    # Update positions with real prices first
    platform.update_positions()
    
    open_trades = list(platform.open_trades.keys())
    
    # Collect stats
    closed_summary = []
    total_pnl = 0
    target_hits = 0
    sl_hits = 0
    time_exits = 0
    
    # Close all open positions
    for trade_id in open_trades:
        trade = platform.close_trade(trade_id, "EOD Auto-Close")
        if trade:
            total_pnl += trade.pnl_amount
            closed_summary.append({
                'symbol': trade.symbol,
                'strategy': trade.strategy,
                'pnl': trade.pnl_amount,
                'exit_reason': trade.exit_reason,
            })
            time_exits += 1
            print(f"  ✅ {trade_id}: ₹{trade.pnl_amount:+,.0f}")
    
    # Calculate stats
    total_trades = len(closed_summary)
    winners = [t for t in closed_summary if t['pnl'] > 0]
    losers = [t for t in closed_summary if t['pnl'] < 0]
    best_trade = max(closed_summary, key=lambda x: x['pnl']) if closed_summary else None
    worst_trade = min(closed_summary, key=lambda x: x['pnl']) if closed_summary else None
    win_rate = (len(winners) / total_trades * 100) if total_trades > 0 else 0
    
    # Premium formatted message
    emoji = "🟢" if total_pnl >= 0 else "🔴"
    now = datetime.now(IST)
    
    msg = f"""
╔══════════════════════════════╗
     📊 <b>END OF DAY SUMMARY</b>
╚══════════════════════════════╝

📅 {now.strftime('%Y-%m-%d')}  │  ⏰ {now.strftime('%H:%M')}

┌──────── TRADE STATS ────────┐

  📋 Total Trades:  <code>{total_trades}</code>
  ✅ Winners:       <code>{len(winners)}</code>
  ❌ Losers:        <code>{len(losers)}</code>
  📊 Win Rate:      <code>{win_rate:.0f}%</code>

└────────────────────────────┘

┌──────── ALL TRADES ────────┐
"""
    
    for item in closed_summary:
        e = "🟢" if item['pnl'] >= 0 else "🔴"
        msg += f"\n  {e} {item['symbol']}: <code>₹{item['pnl']:+,.0f}</code>"
    
    if not closed_summary:
        msg += "\n  📭 No trades today"
    
    msg += f"""

└────────────────────────────┘

┌───────── P&L ──────────────┐
"""
    
    if best_trade:
        msg += f"\n  🏆 Best:  <code>₹{best_trade['pnl']:+,.0f}</code>"
    if worst_trade and worst_trade['pnl'] < 0:
        msg += f"\n  📉 Worst: <code>₹{worst_trade['pnl']:+,.0f}</code>"
    
    msg += f"""

  ━━━━━━━━━━━━━━━━━━━━━━
  {emoji} <b>TOTAL: </b><code>₹{total_pnl:+,.0f}</code>

└────────────────────────────┘

<i>💡 Fresh start tomorrow!</i>
"""
    
    if TELEGRAM_OK:
        send_telegram_message(msg)
    else:
        print(msg)
    
    print(f"\n✅ EOD complete! Total P&L: ₹{total_pnl:+,.0f}")


def clear_position_tracker():
    """Clear position tracker file for fresh start"""
    
    tracker_file = Path(__file__).parent / "positions_today.json"
    daily_trades = Path(__file__).parent / f"daily_trades_{datetime.now(IST).strftime('%Y-%m-%d')}.json"
    
    # Archive today's trades
    if daily_trades.exists():
        archive_dir = Path(__file__).parent / "archive"
        archive_dir.mkdir(exist_ok=True)
        archive_file = archive_dir / f"trades_{datetime.now(IST).strftime('%Y-%m-%d')}.json"
        daily_trades.rename(archive_file)
        print(f"📦 Archived trades to {archive_file.name}")
    
    # Clear tracker
    if tracker_file.exists():
        tracker_file.unlink()
        print("🧹 Cleared position tracker")


def run_eod_close():
    """Run full EOD close process"""
    
    print("\n" + "="*50)
    print("       END OF DAY CLOSE")
    print("="*50)
    print(f"Time: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')}")
    print("-"*50)
    
    # Close all positions
    close_all_positions()
    
    # Clear tracker
    clear_position_tracker()
    
    print("\n✅ EOD process complete!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true', help='Run EOD close')
    parser.add_argument('--clear', action='store_true', help='Just clear tracker')
    
    args = parser.parse_args()
    
    if args.run:
        run_eod_close()
    elif args.clear:
        clear_position_tracker()
        print("✅ Tracker cleared")
    else:
        print("EOD Trade Closer")
        print("  --run    Run full EOD close")
        print("  --clear  Just clear tracker")
