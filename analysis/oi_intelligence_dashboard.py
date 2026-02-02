"""
OI Intelligence Dashboard
==========================
Enhanced dashboard for stock options intelligence system.

Features:
- OI Spurts visualization
- Gainers/Losers tracking
- Next-day predictions
- Movement analysis
- Historical accuracy tracking

Run: python oi_intelligence_dashboard.py --run
Open: http://localhost:8081
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from typing import Dict, List, Optional

BASE_DIR = Path(__file__).parent.parent
IST = timezone(timedelta(hours=5, minutes=30))


class OIIntelligenceData:
    """Load and format OI intelligence data."""
    
    def __init__(self):
        self.data_dir = BASE_DIR / 'data' / 'daily_analysis'
        self.predictions_dir = BASE_DIR / 'data' / 'predictions'
        self.correlations_dir = BASE_DIR / 'data' / 'correlations'
    
    def get_latest_date(self) -> str:
        """Get the latest date with data."""
        if self.data_dir.exists():
            dates = sorted([d.name for d in self.data_dir.iterdir() if d.is_dir()])
            return dates[-1] if dates else datetime.now().strftime('%Y-%m-%d')
        return datetime.now().strftime('%Y-%m-%d')
    
    def load_oi_spurts(self, date: str = None) -> Dict:
        """Load OI spurts data."""
        date = date or self.get_latest_date()
        filepath = self.data_dir / date / 'oi_spurts_analysis.json'
        
        if filepath.exists():
            with open(filepath, 'r') as f:
                return json.load(f)
        return {}
    
    def load_gainers_losers(self, date: str = None) -> Dict:
        """Load gainers/losers data."""
        date = date or self.get_latest_date()
        filepath = self.data_dir / date / 'gainers_losers.json'
        
        if filepath.exists():
            with open(filepath, 'r') as f:
                return json.load(f)
        return {}
    
    def load_predictions(self, date: str = None) -> Dict:
        """Load predictions data."""
        date = date or self.get_latest_date()
        filepath = self.predictions_dir / date / 'predictions.json'
        
        if filepath.exists():
            with open(filepath, 'r') as f:
                return json.load(f)
        return {}
    
    def load_movement_analysis(self, date: str = None) -> Dict:
        """Load movement analysis data."""
        date = date or self.get_latest_date()
        filepath = self.correlations_dir / date / 'movement_analysis.json'
        
        if filepath.exists():
            with open(filepath, 'r') as f:
                return json.load(f)
        return {}


def generate_dashboard_html() -> str:
    """Generate the OI Intelligence dashboard HTML."""
    
    data = OIIntelligenceData()
    latest_date = data.get_latest_date()
    
    oi_spurts = data.load_oi_spurts(latest_date)
    gainers_losers = data.load_gainers_losers(latest_date)
    predictions = data.load_predictions(latest_date)
    movement = data.load_movement_analysis(latest_date)
    
    now = datetime.now(IST)
    
    # Generate OI Spurts HTML
    spurts_html = ""
    if oi_spurts:
        long_buildups = oi_spurts.get('long_buildups', [])[:5]
        short_buildups = oi_spurts.get('short_buildups', [])[:5]
        
        for spurt in long_buildups:
            spurts_html += f"""
            <tr class="bullish-row">
                <td>{spurt.get('symbol', 'N/A')}</td>
                <td>{spurt.get('strike', 'N/A')}</td>
                <td>{spurt.get('option_type', 'N/A')}</td>
                <td class="profit">LONG BUILDUP</td>
                <td>+{spurt.get('oi_change_pct', 0):.1f}%</td>
                <td>{spurt.get('signal_strength', 'N/A')}</td>
            </tr>
            """
        
        for spurt in short_buildups:
            spurts_html += f"""
            <tr class="bearish-row">
                <td>{spurt.get('symbol', 'N/A')}</td>
                <td>{spurt.get('strike', 'N/A')}</td>
                <td>{spurt.get('option_type', 'N/A')}</td>
                <td class="loss">SHORT BUILDUP</td>
                <td>+{spurt.get('oi_change_pct', 0):.1f}%</td>
                <td>{spurt.get('signal_strength', 'N/A')}</td>
            </tr>
            """
    
    if not spurts_html:
        spurts_html = '<tr><td colspan="6" class="no-data">No OI spurts detected today</td></tr>'
    
    # Generate Gainers/Losers HTML
    gainers_html = ""
    top_gainers = gainers_losers.get('top_stock_gainers', [])[:5]
    
    for g in top_gainers:
        gainers_html += f"""
        <tr>
            <td>{g.get('symbol', 'N/A')}</td>
            <td class="profit">+{g.get('change_pct', 0):.2f}%</td>
            <td>₹{g.get('ltp', 0):,.2f}</td>
            <td>{g.get('volume', 0):,}</td>
        </tr>
        """
    
    if not gainers_html:
        gainers_html = '<tr><td colspan="4" class="no-data">No gainers data</td></tr>'
    
    losers_html = ""
    top_losers = gainers_losers.get('top_stock_losers', [])[:5]
    
    for l in top_losers:
        losers_html += f"""
        <tr>
            <td>{l.get('symbol', 'N/A')}</td>
            <td class="loss">{l.get('change_pct', 0):.2f}%</td>
            <td>₹{l.get('ltp', 0):,.2f}</td>
            <td>{l.get('volume', 0):,}</td>
        </tr>
        """
    
    if not losers_html:
        losers_html = '<tr><td colspan="4" class="no-data">No losers data</td></tr>'
    
    # Generate Predictions HTML
    predictions_html = ""
    all_predictions = predictions.get('predictions', [])[:8]
    
    for p in all_predictions:
        direction_class = "profit" if p.get('direction') == 'BULLISH' else "loss" if p.get('direction') == 'BEARISH' else ""
        direction_icon = "📈" if p.get('direction') == 'BULLISH' else "📉" if p.get('direction') == 'BEARISH' else "➡️"
        
        predictions_html += f"""
        <tr>
            <td>{p.get('symbol', 'N/A')}</td>
            <td class="{direction_class}">{direction_icon} {p.get('direction', 'N/A')}</td>
            <td>{p.get('confidence', 0)*100:.0f}%</td>
            <td>+{p.get('target_move_pct', 0):.1f}%</td>
            <td>{p.get('stop_loss_pct', 0):.1f}%</td>
            <td>{p.get('risk_level', 'N/A')}</td>
            <td style="font-size: 0.8em">{p.get('suggested_strategy', 'N/A')}</td>
        </tr>
        """
    
    if not predictions_html:
        predictions_html = '<tr><td colspan="7" class="no-data">No predictions available</td></tr>'
    
    # Market sentiment
    sentiment = oi_spurts.get('market_sentiment', 'N/A')
    sentiment_score = oi_spurts.get('sentiment_score', 0)
    sentiment_class = "profit" if sentiment == 'BULLISH' else "loss" if sentiment == 'BEARISH' else ""
    
    # Prediction accuracy
    pred_accuracy = predictions.get('model_accuracy', 0.5) * 100
    
    # Movement analysis
    total_analyzed = movement.get('total_analyzed', 0)
    correct_preds = movement.get('correct_predictions', 0)
    move_accuracy = movement.get('prediction_accuracy', 0) * 100
    
    html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="120">
    <title>OI Intelligence Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, sans-serif;
            background: linear-gradient(135deg, #0f0f23 0%, #1a1a3e 50%, #0d1b2a 100%);
            color: #eee;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{ max-width: 1600px; margin: 0 auto; }}
        
        h1 {{
            text-align: center;
            font-size: 2.5em;
            margin-bottom: 10px;
            background: linear-gradient(90deg, #f39c12, #e74c3c, #9b59b6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        .subtitle {{
            text-align: center;
            color: #888;
            margin-bottom: 30px;
        }}
        
        /* Tabs */
        .tabs {{
            display: flex;
            justify-content: center;
            gap: 10px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }}
        .tab {{
            padding: 12px 25px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.1);
            border-radius: 10px;
            cursor: pointer;
            transition: all 0.3s;
            font-weight: 500;
        }}
        .tab:hover {{ background: rgba(255,255,255,0.1); }}
        .tab.active {{
            background: linear-gradient(135deg, #f39c12, #e74c3c);
            border-color: transparent;
        }}
        
        .tab-content {{ display: none; }}
        .tab-content.active {{ display: block; }}
        
        /* Stats Grid */
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s;
        }}
        .stat-card:hover {{ transform: translateY(-5px); }}
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            margin: 10px 0;
        }}
        .stat-label {{ color: #888; font-size: 0.9em; }}
        
        .profit {{ color: #2ecc71; }}
        .loss {{ color: #e74c3c; }}
        .neutral {{ color: #f39c12; }}
        
        /* Sections */
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
            color: #f39c12;
            display: flex;
            align-items: center;
            gap: 10px;
        }}
        
        /* Tables */
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
            background: rgba(243,156,18,0.1);
            color: #f39c12;
            font-weight: 600;
        }}
        tr:hover {{ background: rgba(255,255,255,0.03); }}
        .bullish-row {{ border-left: 3px solid #2ecc71; }}
        .bearish-row {{ border-left: 3px solid #e74c3c; }}
        .no-data {{
            text-align: center;
            color: #666;
            padding: 30px;
        }}
        
        /* Two column layout */
        .two-col {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: 20px;
        }}
        
        /* Sentiment Badge */
        .sentiment-badge {{
            display: inline-block;
            padding: 8px 20px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 1.1em;
        }}
        .sentiment-bullish {{ background: rgba(46,204,113,0.2); color: #2ecc71; }}
        .sentiment-bearish {{ background: rgba(231,76,60,0.2); color: #e74c3c; }}
        .sentiment-neutral {{ background: rgba(243,156,18,0.2); color: #f39c12; }}
        
        /* Legend */
        .legend {{
            display: flex;
            gap: 20px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.9em;
            color: #888;
        }}
        .legend-dot {{
            width: 12px;
            height: 12px;
            border-radius: 50%;
        }}
        .legend-dot.bullish {{ background: #2ecc71; }}
        .legend-dot.bearish {{ background: #e74c3c; }}
        
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
        <h1>🔮 OI Intelligence Dashboard</h1>
        <div class="subtitle">
            Data for: {latest_date} | Updated: {now.strftime('%H:%M:%S')} IST | Auto-refresh: 2 min
        </div>
        
        <!-- Tabs -->
        <div class="tabs">
            <div class="tab active" onclick="showTab('overview')">📊 Overview</div>
            <div class="tab" onclick="showTab('spurts')">🔥 OI Spurts</div>
            <div class="tab" onclick="showTab('movers')">📈 Gainers/Losers</div>
            <div class="tab" onclick="showTab('predictions')">🎯 Predictions</div>
        </div>
        
        <!-- Overview Tab -->
        <div id="overview" class="tab-content active">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Market Sentiment</div>
                    <div class="stat-value {sentiment_class}">{sentiment}</div>
                    <div style="color:#888">Score: {sentiment_score}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Total OI Spurts</div>
                    <div class="stat-value">{oi_spurts.get('total_spurts', 0)}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Long Buildups</div>
                    <div class="stat-value profit">{len(oi_spurts.get('long_buildups', []))}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Short Buildups</div>
                    <div class="stat-value loss">{len(oi_spurts.get('short_buildups', []))}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Predictions Made</div>
                    <div class="stat-value">{len(all_predictions)}</div>
                </div>
                <div class="stat-card">
                    <div class="stat-label">Model Accuracy</div>
                    <div class="stat-value">{pred_accuracy:.0f}%</div>
                </div>
            </div>
            
            <div class="section">
                <h2>📌 Quick Summary</h2>
                <div class="legend">
                    <div class="legend-item">
                        <div class="legend-dot bullish"></div>
                        <span>Bullish Signal</span>
                    </div>
                    <div class="legend-item">
                        <div class="legend-dot bearish"></div>
                        <span>Bearish Signal</span>
                    </div>
                </div>
                <p style="color:#aaa; line-height: 1.6;">
                    Today's market sentiment is 
                    <span class="sentiment-badge sentiment-{sentiment.lower()}">{sentiment}</span>
                    based on OI analysis. 
                    There were <strong>{oi_spurts.get('total_spurts', 0)}</strong> significant OI spurts detected,
                    with <strong class="profit">{len(oi_spurts.get('long_buildups', []))}</strong> bullish 
                    and <strong class="loss">{len(oi_spurts.get('short_buildups', []))}</strong> bearish signals.
                </p>
            </div>
            
            <div class="two-col">
                <div class="section">
                    <h2>📈 Top Bullish Signals</h2>
                    <table>
                        <tr><th>Symbol</th><th>Direction</th><th>Confidence</th></tr>
                        {''.join([f"<tr><td>{p.get('symbol')}</td><td class='profit'>BULLISH</td><td>{p.get('confidence',0)*100:.0f}%</td></tr>" for p in predictions.get('top_bullish', [])[:3]]) or '<tr><td colspan="3" class="no-data">No bullish signals</td></tr>'}
                    </table>
                </div>
                <div class="section">
                    <h2>📉 Top Bearish Signals</h2>
                    <table>
                        <tr><th>Symbol</th><th>Direction</th><th>Confidence</th></tr>
                        {''.join([f"<tr><td>{p.get('symbol')}</td><td class='loss'>BEARISH</td><td>{p.get('confidence',0)*100:.0f}%</td></tr>" for p in predictions.get('top_bearish', [])[:3]]) or '<tr><td colspan="3" class="no-data">No bearish signals</td></tr>'}
                    </table>
                </div>
            </div>
        </div>
        
        <!-- OI Spurts Tab -->
        <div id="spurts" class="tab-content">
            <div class="section">
                <h2>🔥 OI Spurts Detected</h2>
                <p style="color:#888; margin-bottom:15px;">
                    Significant Open Interest changes (>15%) indicating institutional activity
                </p>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Strike</th>
                        <th>Type</th>
                        <th>Classification</th>
                        <th>OI Change</th>
                        <th>Strength</th>
                    </tr>
                    {spurts_html}
                </table>
            </div>
        </div>
        
        <!-- Gainers/Losers Tab -->
        <div id="movers" class="tab-content">
            <div class="two-col">
                <div class="section">
                    <h2>📈 Top Gainers</h2>
                    <table>
                        <tr>
                            <th>Symbol</th>
                            <th>Change</th>
                            <th>LTP</th>
                            <th>Volume</th>
                        </tr>
                        {gainers_html}
                    </table>
                </div>
                <div class="section">
                    <h2>📉 Top Losers</h2>
                    <table>
                        <tr>
                            <th>Symbol</th>
                            <th>Change</th>
                            <th>LTP</th>
                            <th>Volume</th>
                        </tr>
                        {losers_html}
                    </table>
                </div>
            </div>
            
            <div class="section">
                <h2>🔥 Trending Stocks</h2>
                <p style="color:#888;">Stocks appearing in movers list for multiple days</p>
                <div style="margin-top:15px; display:flex; gap:10px; flex-wrap:wrap;">
                    {''.join([f'<span style="background:rgba(243,156,18,0.2); padding:8px 15px; border-radius:20px; color:#f39c12;">{s}</span>' for s in gainers_losers.get('trending_stocks', [])[:10]]) or '<span style="color:#666;">No trending stocks detected</span>'}
                </div>
            </div>
        </div>
        
        <!-- Predictions Tab -->
        <div id="predictions" class="tab-content">
            <div class="section">
                <h2>🎯 Next Day Predictions</h2>
                <p style="color:#888; margin-bottom:15px;">
                    Predictions generated based on OI spurts, momentum, and sector analysis
                </p>
                <table>
                    <tr>
                        <th>Symbol</th>
                        <th>Direction</th>
                        <th>Confidence</th>
                        <th>Target</th>
                        <th>Stop Loss</th>
                        <th>Risk</th>
                        <th>Strategy</th>
                    </tr>
                    {predictions_html}
                </table>
            </div>
            
            <div class="section" style="background: rgba(231,76,60,0.1); border-color: rgba(231,76,60,0.3);">
                <h2 style="color:#e74c3c;">⚠️ Disclaimer</h2>
                <p style="color:#aaa; line-height:1.6;">
                    These predictions are generated by analyzing OI patterns and market data. 
                    They are for <strong>educational purposes only</strong> and should not be 
                    considered as financial advice. Always do your own research (DYOR) and 
                    trade with proper risk management.
                </p>
            </div>
        </div>
        
        <div class="footer">
            OI Intelligence Dashboard | Data refreshes every 2 minutes | 
            <a href="/" style="color:#f39c12;">Trading Dashboard</a>
        </div>
    </div>
    
    <script>
        function showTab(tabId) {{
            // Hide all tabs
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            
            // Show selected tab
            document.getElementById(tabId).classList.add('active');
            event.target.classList.add('active');
        }}
    </script>
</body>
</html>
"""
    return html


class OIDashboardHandler(SimpleHTTPRequestHandler):
    """Handler for OI Intelligence Dashboard."""
    
    def do_GET(self):
        if self.path == '/' or self.path == '/oi':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            html = generate_dashboard_html()
            self.wfile.write(html.encode())
        elif self.path == '/api/oi-data':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            data = OIIntelligenceData()
            response = {
                'oi_spurts': data.load_oi_spurts(),
                'gainers_losers': data.load_gainers_losers(),
                'predictions': data.load_predictions()
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            super().do_GET()
    
    def log_message(self, format, *args):
        pass  # Suppress logs


def run_dashboard(port: int = 8081):
    """Run the OI Intelligence dashboard server."""
    server = HTTPServer(('0.0.0.0', port), OIDashboardHandler)
    print(f"🔮 OI Intelligence Dashboard running at http://localhost:{port}")
    print("Press Ctrl+C to stop")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n⏹ Dashboard stopped")
        server.shutdown()


def main():
    """Main execution."""
    import argparse
    
    parser = argparse.ArgumentParser(description='OI Intelligence Dashboard')
    parser.add_argument('--run', action='store_true', help='Run dashboard server')
    parser.add_argument('--port', type=int, default=8081, help='Port number (default: 8081)')
    
    args = parser.parse_args()
    
    if args.run:
        run_dashboard(args.port)
    else:
        print("OI Intelligence Dashboard")
        print("  --run           Start dashboard server")
        print("  --port PORT     Port number (default: 8081)")


if __name__ == "__main__":
    main()
