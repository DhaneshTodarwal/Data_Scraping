"""
Trading Web Dashboard
======================
Simple web dashboard to view:
- Open positions
- Trade history
- P&L stats
- System status

Run: python web_dashboard.py
Open: http://localhost:8080
"""
import sys
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
import urllib.parse

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from paper_trading_platform import get_platform
    PAPER_OK = True
except ImportError:
    PAPER_OK = False


def get_dashboard_html() -> str:
    """Generate dashboard HTML"""
    
    # Get data
    if PAPER_OK:
        platform = get_platform()
        platform.update_positions()
        stats = platform.stats
        open_trades = list(platform.open_trades.values())
        closed_trades = platform.get_trade_history(20)
    else:
        stats = None
        open_trades = []
        closed_trades = []
    
    # Generate HTML
    now = datetime.now(IST)
    
    # Open positions table
    positions_html = ""
    if open_trades:
        for trade in open_trades:
            pnl_class = "profit" if trade.pnl_amount >= 0 else "loss"
            legs_str = ", ".join([f"{l.get('action','')[0]}-{l.get('type','')}{l.get('strike','')}" 
                                  for l in trade.legs])
            positions_html += f"""
            <tr>
                <td>{trade.trade_id}</td>
                <td>{trade.symbol}</td>
                <td>{trade.strategy}</td>
                <td>{legs_str}</td>
                <td>₹{trade.entry_premium:.2f}</td>
                <td class="{pnl_class}">₹{trade.pnl_amount:+,.0f}</td>
                <td>{trade.entry_time}</td>
            </tr>
            """
    else:
        positions_html = '<tr><td colspan="7" class="no-data">No open positions</td></tr>'
    
    # History table
    history_html = ""
    if closed_trades:
        for trade in reversed(closed_trades):
            pnl_class = "profit" if trade.pnl_amount >= 0 else "loss"
            history_html += f"""
            <tr>
                <td>{trade.trade_id}</td>
                <td>{trade.symbol}</td>
                <td>{trade.strategy}</td>
                <td class="{pnl_class}">₹{trade.pnl_amount:+,.0f}</td>
                <td>{trade.exit_reason}</td>
                <td>{trade.exit_time or '-'}</td>
            </tr>
            """
    else:
        history_html = '<tr><td colspan="6" class="no-data">No trade history</td></tr>'
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="60">
    <title>Trading Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{
            text-align: center;
            font-size: 2.5em;
            margin-bottom: 10px;
            background: linear-gradient(90deg, #00d9ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .time {{ text-align: center; color: #888; margin-bottom: 30px; }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            margin: 10px 0;
        }}
        .stat-label {{ color: #888; font-size: 0.9em; }}
        .profit {{ color: #00ff88; }}
        .loss {{ color: #ff4757; }}
        
        .section {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 30px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .section h2 {{
            font-size: 1.3em;
            margin-bottom: 15px;
            color: #00d9ff;
        }}
        
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        th {{
            background: rgba(0,217,255,0.1);
            color: #00d9ff;
            font-weight: 600;
        }}
        tr:hover {{ background: rgba(255,255,255,0.03); }}
        .no-data {{
            text-align: center;
            color: #666;
            padding: 30px;
        }}
        
        .footer {{
            text-align: center;
            color: #666;
            margin-top: 30px;
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 Trading Dashboard</h1>
        <div class="time">{now.strftime('%Y-%m-%d %H:%M:%S')} IST | Auto-refresh every 60s</div>
        
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Capital</div>
                <div class="stat-value">₹{stats.total_capital:,.0f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Available</div>
                <div class="stat-value">₹{stats.available_capital:,.0f}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total P&L</div>
                <div class="stat-value {'profit' if stats.total_pnl >= 0 else 'loss'}">
                    ₹{stats.total_pnl:+,.0f}
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Win Rate</div>
                <div class="stat-value">{stats.win_rate:.1f}%</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Total Trades</div>
                <div class="stat-value">{stats.total_trades}</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Open Positions</div>
                <div class="stat-value">{len(open_trades)}</div>
            </div>
        </div>
        
        <div class="section">
            <h2>📈 Open Positions</h2>
            <table>
                <tr>
                    <th>Trade ID</th>
                    <th>Symbol</th>
                    <th>Strategy</th>
                    <th>Legs</th>
                    <th>Entry</th>
                    <th>P&L</th>
                    <th>Time</th>
                </tr>
                {positions_html}
            </table>
        </div>
        
        <div class="section">
            <h2>📜 Trade History</h2>
            <table>
                <tr>
                    <th>Trade ID</th>
                    <th>Symbol</th>
                    <th>Strategy</th>
                    <th>P&L</th>
                    <th>Exit Reason</th>
                    <th>Exit Time</th>
                </tr>
                {history_html}
            </table>
        </div>
        
        <div class="footer">
            Paper Trading Dashboard | Auto-refreshes every 60 seconds
        </div>
    </div>
</body>
</html>
"""
    return html


class DashboardHandler(SimpleHTTPRequestHandler):
    """Custom handler for dashboard"""
    
    def do_GET(self):
        if self.path == '/' or self.path == '/dashboard':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = get_dashboard_html()
            self.wfile.write(html.encode())
        elif self.path == '/api/stats':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            if PAPER_OK:
                platform = get_platform()
                data = {
                    'total_pnl': platform.stats.total_pnl,
                    'open_positions': len(platform.open_trades),
                    'win_rate': platform.stats.win_rate,
                }
            else:
                data = {'error': 'Paper trading not available'}
            self.wfile.write(json.dumps(data).encode())
        else:
            super().do_GET()
    
    def log_message(self, format, *args):
        pass  # Suppress logs


def run_dashboard(port: int = 8080):
    """Run the dashboard server"""
    server = HTTPServer(('0.0.0.0', port), DashboardHandler)
    print(f"📊 Dashboard running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹ Dashboard stopped")
        server.shutdown()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true', help='Run dashboard')
    parser.add_argument('--port', type=int, default=8080, help='Port number')
    
    args = parser.parse_args()
    
    if args.run:
        run_dashboard(args.port)
    else:
        print("Web Dashboard")
        print("  --run         Start dashboard server")
        print("  --port PORT   Port number (default: 8080)")
