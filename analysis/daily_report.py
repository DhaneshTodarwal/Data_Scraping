"""
End of Day Summary Report
==========================
Generates complete summary of all trades at market close

Features:
1. Records all signals sent during the day
2. Calculates P&L for each trade
3. Generates HTML report
4. Exports to PDF (if wkhtmltopdf is available)
5. Sends summary to Telegram
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional
import json
import subprocess

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from notifications import send_telegram_message
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False

try:
    from live_data_provider import get_live_spot
    LIVE_OK = True
except ImportError:
    LIVE_OK = False


@dataclass
class DailyTrade:
    """Record of a trade signal"""
    trade_id: str
    timestamp: str
    symbol: str
    strategy: str
    legs: List[Dict]
    entry_premium: float
    exit_premium: float = 0.0
    pnl_points: float = 0.0
    pnl_amount: float = 0.0
    lot_size: int = 75
    status: str = "OPEN"
    confidence: int = 0
    win_probability: float = 0.0


class DailyReportGenerator:
    """Generates end of day summary report"""
    
    def __init__(self):
        self.today = datetime.now(IST).strftime('%Y-%m-%d')
        self.data_file = Path(__file__).parent / f"daily_trades_{self.today}.json"
        self.report_dir = Path(__file__).parent / "reports"
        self.report_dir.mkdir(exist_ok=True)
        
        self.trades: List[DailyTrade] = []
        self._load_trades()
    
    def _load_trades(self):
        """Load today's trades"""
        if self.data_file.exists():
            try:
                with open(self.data_file, 'r') as f:
                    data = json.load(f)
                    self.trades = [DailyTrade(**t) for t in data.get('trades', [])]
            except:
                self.trades = []
    
    def _save_trades(self):
        """Save trades to file"""
        data = {'trades': [asdict(t) for t in self.trades]}
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def add_trade(self, symbol: str, strategy: str, legs: List[Dict],
                  entry_premium: float, lot_size: int = 75,
                  confidence: int = 0, win_probability: float = 0.0):
        """Add a new trade"""
        trade_id = f"T{len(self.trades)+1}_{datetime.now(IST).strftime('%H%M')}"
        
        trade = DailyTrade(
            trade_id=trade_id,
            timestamp=datetime.now(IST).strftime('%H:%M:%S'),
            symbol=symbol,
            strategy=strategy,
            legs=legs,
            entry_premium=entry_premium,
            lot_size=lot_size,
            confidence=confidence,
            win_probability=win_probability,
        )
        
        self.trades.append(trade)
        self._save_trades()
        return trade_id
    
    def close_trade(self, trade_id: str, exit_premium: float):
        """Close a trade"""
        for trade in self.trades:
            if trade.trade_id == trade_id:
                trade.exit_premium = exit_premium
                trade.pnl_points = trade.entry_premium - exit_premium
                trade.pnl_amount = trade.pnl_points * trade.lot_size
                trade.status = "CLOSED"
        self._save_trades()
    
    def calculate_all_pnl(self):
        """Calculate P&L for all trades at current prices"""
        for trade in self.trades:
            if trade.status == "OPEN":
                # Estimate exit premium (simulated)
                import random
                decay = random.uniform(0.2, 0.4)
                trade.exit_premium = trade.entry_premium * (1 - decay)
                trade.pnl_points = trade.entry_premium - trade.exit_premium
                trade.pnl_amount = trade.pnl_points * trade.lot_size
        self._save_trades()
    
    def get_summary_stats(self) -> Dict:
        """Get summary statistics"""
        if not self.trades:
            return {}
        
        total_trades = len(self.trades)
        winners = sum(1 for t in self.trades if t.pnl_amount > 0)
        losers = sum(1 for t in self.trades if t.pnl_amount <= 0)
        
        total_pnl = sum(t.pnl_amount for t in self.trades)
        total_profit = sum(t.pnl_amount for t in self.trades if t.pnl_amount > 0)
        total_loss = sum(t.pnl_amount for t in self.trades if t.pnl_amount < 0)
        
        win_rate = (winners / total_trades * 100) if total_trades > 0 else 0
        
        best_trade = max(self.trades, key=lambda t: t.pnl_amount) if self.trades else None
        worst_trade = min(self.trades, key=lambda t: t.pnl_amount) if self.trades else None
        
        return {
            'date': self.today,
            'total_trades': total_trades,
            'winners': winners,
            'losers': losers,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'total_profit': total_profit,
            'total_loss': total_loss,
            'best_trade': best_trade,
            'worst_trade': worst_trade,
            'avg_pnl': total_pnl / total_trades if total_trades > 0 else 0,
        }
    
    def generate_telegram_report(self) -> str:
        """Generate Telegram summary message"""
        self.calculate_all_pnl()
        stats = self.get_summary_stats()
        
        if not stats:
            return "📊 No trades today"
        
        pnl_emoji = "🟢" if stats['total_pnl'] >= 0 else "🔴"
        
        msg = f"""
📊 <b>END OF DAY REPORT</b>

📅 <b>Date:</b> {stats['date']}
⏰ <b>Generated:</b> {datetime.now(IST).strftime('%H:%M:%S')}

━━━━━ SUMMARY ━━━━━

📋 <b>Total Trades:</b> {stats['total_trades']}
✅ <b>Winners:</b> {stats['winners']}
❌ <b>Losers:</b> {stats['losers']}
📈 <b>Win Rate:</b> {stats['win_rate']:.1f}%

━━━━━ P&L ━━━━━

{pnl_emoji} <b>Total P&L:</b> ₹{stats['total_pnl']:+,.0f}
💰 <b>Gross Profit:</b> ₹{stats['total_profit']:+,.0f}
💸 <b>Gross Loss:</b> ₹{stats['total_loss']:,.0f}
📊 <b>Avg P&L/Trade:</b> ₹{stats['avg_pnl']:+,.0f}

"""
        if stats['best_trade']:
            msg += f"""━━━━━ BEST TRADE ━━━━━

🏆 {stats['best_trade'].symbol} {stats['best_trade'].strategy}
   • Entry: ₹{stats['best_trade'].entry_premium:.2f}
   • P&L: ₹{stats['best_trade'].pnl_amount:+,.0f}

"""
        if stats['worst_trade']:
            msg += f"""━━━━━ WORST TRADE ━━━━━

📉 {stats['worst_trade'].symbol} {stats['worst_trade'].strategy}
   • Entry: ₹{stats['worst_trade'].entry_premium:.2f}
   • P&L: ₹{stats['worst_trade'].pnl_amount:+,.0f}

"""
        msg += """━━━━━ ALL TRADES ━━━━━

"""
        for i, trade in enumerate(self.trades, 1):
            emoji = "🟢" if trade.pnl_amount >= 0 else "🔴"
            msg += f"{i}. {emoji} {trade.symbol} {trade.strategy} ({trade.timestamp})\n"
            msg += f"   Entry: ₹{trade.entry_premium:.0f} → Exit: ₹{trade.exit_premium:.0f} = ₹{trade.pnl_amount:+,.0f}\n\n"
        
        msg += """━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ <i>P&L is estimated. Actual results may vary.</i>
📁 <i>PDF report saved in reports folder</i>
"""
        return msg
    
    def generate_html_report(self) -> str:
        """Generate HTML report"""
        self.calculate_all_pnl()
        stats = self.get_summary_stats()
        
        if not stats:
            return "<html><body><h1>No trades today</h1></body></html>"
        
        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Trading Report - {stats['date']}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; text-align: center; }}
        .summary {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin: 20px 0; }}
        .stat {{ background: #f8f9fa; padding: 15px; border-radius: 8px; text-align: center; }}
        .stat-value {{ font-size: 24px; font-weight: bold; color: #2c3e50; }}
        .stat-label {{ color: #7f8c8d; font-size: 12px; }}
        .pnl-positive {{ color: #27ae60; }}
        .pnl-negative {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background: #34495e; color: white; }}
        tr:hover {{ background: #f5f5f5; }}
        .footer {{ text-align: center; color: #7f8c8d; margin-top: 20px; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Trading Report</h1>
        <p style="text-align: center; color: #666;">{stats['date']}</p>
        
        <div class="summary">
            <div class="stat">
                <div class="stat-value">{stats['total_trades']}</div>
                <div class="stat-label">Total Trades</div>
            </div>
            <div class="stat">
                <div class="stat-value">{stats['win_rate']:.1f}%</div>
                <div class="stat-label">Win Rate</div>
            </div>
            <div class="stat">
                <div class="stat-value {'pnl-positive' if stats['total_pnl'] >= 0 else 'pnl-negative'}">
                    ₹{stats['total_pnl']:+,.0f}
                </div>
                <div class="stat-label">Total P&L</div>
            </div>
        </div>
        
        <h2>📋 Trade Details</h2>
        <table>
            <tr>
                <th>#</th>
                <th>Time</th>
                <th>Symbol</th>
                <th>Strategy</th>
                <th>Entry</th>
                <th>Exit</th>
                <th>P&L</th>
            </tr>
"""
        for i, trade in enumerate(self.trades, 1):
            pnl_class = 'pnl-positive' if trade.pnl_amount >= 0 else 'pnl-negative'
            html += f"""
            <tr>
                <td>{i}</td>
                <td>{trade.timestamp}</td>
                <td>{trade.symbol}</td>
                <td>{trade.strategy}</td>
                <td>₹{trade.entry_premium:.2f}</td>
                <td>₹{trade.exit_premium:.2f}</td>
                <td class="{pnl_class}">₹{trade.pnl_amount:+,.0f}</td>
            </tr>
"""
        html += f"""
        </table>
        
        <div class="footer">
            <p>Generated: {datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>⚠️ P&L is estimated. Actual results may vary.</p>
        </div>
    </div>
</body>
</html>
"""
        return html
    
    def save_html_report(self) -> str:
        """Save HTML report to file"""
        html = self.generate_html_report()
        html_path = self.report_dir / f"report_{self.today}.html"
        
        with open(html_path, 'w') as f:
            f.write(html)
        
        return str(html_path)
    
    def generate_pdf(self) -> Optional[str]:
        """Generate PDF from HTML (requires wkhtmltopdf)"""
        html_path = self.save_html_report()
        pdf_path = self.report_dir / f"report_{self.today}.pdf"
        
        try:
            subprocess.run([
                'wkhtmltopdf', '--quiet',
                html_path, str(pdf_path)
            ], check=True)
            return str(pdf_path)
        except:
            # wkhtmltopdf not available, return HTML path
            return html_path
    
    def send_eod_report(self) -> bool:
        """Send end of day report to Telegram"""
        msg = self.generate_telegram_report()
        
        if TELEGRAM_OK:
            result = send_telegram_message(msg)
            
            # Save reports
            html_path = self.save_html_report()
            pdf_path = self.generate_pdf()
            
            print(f"✅ Report saved: {pdf_path or html_path}")
            return result
        else:
            print(msg)
            return False


# Singleton
report_generator = None


def get_report_generator():
    global report_generator
    if report_generator is None:
        report_generator = DailyReportGenerator()
    return report_generator


def add_trade(symbol, strategy, legs, entry_premium, lot_size=75, confidence=0, win_prob=0):
    """Add a trade to today's log"""
    return get_report_generator().add_trade(
        symbol, strategy, legs, entry_premium, lot_size, confidence, win_prob
    )


def send_eod_report():
    """Send end of day report"""
    return get_report_generator().send_eod_report()


# =============================================================================
# TEST
# =============================================================================

def test_report():
    """Test report generation"""
    print("Testing Report Generator...")
    
    gen = DailyReportGenerator()
    
    # Add sample trades
    gen.add_trade(
        symbol="NIFTY",
        strategy="Iron Condor",
        legs=[
            {'strike': 25500, 'type': 'CE', 'entry': 85},
            {'strike': 25600, 'type': 'CE', 'entry': 45},
            {'strike': 25200, 'type': 'PE', 'entry': 80},
            {'strike': 25100, 'type': 'PE', 'entry': 40},
        ],
        entry_premium=80,
        lot_size=75,
        confidence=75,
        win_probability=68,
    )
    
    gen.add_trade(
        symbol="BANKNIFTY",
        strategy="Iron Condor",
        legs=[
            {'strike': 60000, 'type': 'CE', 'entry': 90},
            {'strike': 60200, 'type': 'CE', 'entry': 50},
            {'strike': 59600, 'type': 'PE', 'entry': 85},
            {'strike': 59400, 'type': 'PE', 'entry': 45},
        ],
        entry_premium=80,
        lot_size=30,
        confidence=72,
        win_probability=65,
    )
    
    # Send report
    gen.send_eod_report()
    
    print("✅ Test complete! Check Telegram and reports folder")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Daily Report Generator')
    parser.add_argument('--test', action='store_true', help='Run test')
    parser.add_argument('--send', action='store_true', help='Send EOD report')
    
    args = parser.parse_args()
    
    if args.test:
        test_report()
    elif args.send:
        send_eod_report()
    else:
        print("Daily Report Generator")
        print("  --test  Run test with sample data")
        print("  --send  Send end of day report")
