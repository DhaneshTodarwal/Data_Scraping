"""
Performance Dashboard Generator
================================
Generates interactive HTML dashboards with charts for backtest results
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
import json
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import BACKTEST_OUTPUT


class DashboardGenerator:
    """Generate HTML dashboards from backtest results"""
    
    def __init__(self, results_df: pd.DataFrame = None):
        self.results = results_df
        self.output_dir = Path(__file__).parent / "output"
        self.output_dir.mkdir(exist_ok=True)
    
    def load_batch_results(self, batch_name: str = None):
        """Load results from batch backtest"""
        batch_dir = BACKTEST_OUTPUT / "batch"
        
        if batch_name:
            results_file = batch_dir / batch_name / "all_results.csv"
        else:
            # Find latest batch
            batches = sorted(batch_dir.glob("*/all_results.csv"), 
                           key=lambda x: x.stat().st_mtime, reverse=True)
            if not batches:
                raise FileNotFoundError("No batch results found")
            results_file = batches[0]
        
        self.results = pd.read_csv(results_file)
        print(f"Loaded {len(self.results)} results from {results_file}")
        return self.results
    
    def generate_dashboard(self, title: str = "Backtest Performance Dashboard"):
        """Generate complete HTML dashboard"""
        
        if self.results is None or self.results.empty:
            raise ValueError("No results loaded. Call load_batch_results() first.")
        
        html = self._generate_html(title)
        
        output_file = self.output_dir / f"dashboard_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
        with open(output_file, 'w') as f:
            f.write(html)
        
        print(f"\n✅ Dashboard saved to: {output_file}")
        return output_file
    
    def _generate_html(self, title: str) -> str:
        """Generate HTML content"""
        
        # Prepare data
        strategy_data = self.results.groupby('strategy').agg({
            'total_pnl': 'sum',
            'win_rate': 'mean',
            'total_trades': 'sum',
            'profit_factor': 'mean',
        }).round(2)
        
        symbol_data = self.results.groupby('symbol').agg({
            'total_pnl': 'sum',
            'win_rate': 'mean',
            'total_trades': 'sum',
        }).round(2)
        
        # Best combinations
        best = self.results.nlargest(10, 'total_pnl')
        
        html = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eaeaea;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        header {{
            text-align: center;
            padding: 30px 0;
            margin-bottom: 30px;
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        h1 {{
            font-size: 2.5em;
            background: linear-gradient(90deg, #00d9ff, #00ff88);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }}
        .subtitle {{
            color: #888;
            font-size: 1.1em;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .card {{
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 25px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .card h2 {{
            font-size: 1.2em;
            margin-bottom: 15px;
            color: #00d9ff;
        }}
        .stat-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .stat-value {{
            font-size: 2em;
            font-weight: bold;
            color: #00ff88;
        }}
        .stat-value.negative {{
            color: #ff6b6b;
        }}
        .stat-label {{
            color: #888;
            font-size: 0.9em;
            margin-top: 5px;
        }}
        .chart-container {{
            position: relative;
            height: 300px;
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
        }}
        tr:hover {{
            background: rgba(255,255,255,0.05);
        }}
        .positive {{
            color: #00ff88;
        }}
        .negative {{
            color: #ff6b6b;
        }}
        .badge {{
            display: inline-block;
            padding: 4px 10px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: bold;
        }}
        .badge.success {{
            background: rgba(0,255,136,0.2);
            color: #00ff88;
        }}
        .badge.danger {{
            background: rgba(255,107,107,0.2);
            color: #ff6b6b;
        }}
        footer {{
            text-align: center;
            padding: 20px;
            color: #666;
            margin-top: 30px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 {title}</h1>
            <p class="subtitle">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        </header>
        
        <!-- Key Metrics -->
        <div class="stat-grid">
            <div class="stat-card">
                <div class="stat-value {'negative' if self.results['total_pnl'].sum() < 0 else ''}">
                    ₹{self.results['total_pnl'].sum():,.0f}
                </div>
                <div class="stat-label">Total P&L</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">
                    {self.results['win_rate'].mean():.1f}%
                </div>
                <div class="stat-label">Avg Win Rate</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">
                    {self.results['total_trades'].sum()}
                </div>
                <div class="stat-label">Total Trades</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">
                    {len(self.results)}
                </div>
                <div class="stat-label">Combinations Tested</div>
            </div>
        </div>
        
        <!-- Charts Row -->
        <div class="grid">
            <div class="card">
                <h2>📈 P&L by Strategy</h2>
                <div class="chart-container">
                    <canvas id="strategyChart"></canvas>
                </div>
            </div>
            <div class="card">
                <h2>📍 P&L by Symbol</h2>
                <div class="chart-container">
                    <canvas id="symbolChart"></canvas>
                </div>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h2>🎯 Win Rate by Strategy</h2>
                <div class="chart-container">
                    <canvas id="winRateChart"></canvas>
                </div>
            </div>
            <div class="card">
                <h2>📊 Profit Factor</h2>
                <div class="chart-container">
                    <canvas id="profitFactorChart"></canvas>
                </div>
            </div>
        </div>
        
        <!-- Top Combinations Table -->
        <div class="card" style="margin-top: 20px;">
            <h2>🏆 Top 10 Strategy + Symbol Combinations</h2>
            <table>
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Strategy</th>
                        <th>Symbol</th>
                        <th>Trades</th>
                        <th>Win Rate</th>
                        <th>Total P&L</th>
                        <th>Profit Factor</th>
                    </tr>
                </thead>
                <tbody>
                    {self._generate_top_table_rows(best)}
                </tbody>
            </table>
        </div>
        
        <!-- Strategy Performance Table -->
        <div class="card" style="margin-top: 20px;">
            <h2>📋 All Strategies Performance</h2>
            <table>
                <thead>
                    <tr>
                        <th>Strategy</th>
                        <th>Total Trades</th>
                        <th>Avg Win Rate</th>
                        <th>Total P&L</th>
                        <th>Avg Profit Factor</th>
                    </tr>
                </thead>
                <tbody>
                    {self._generate_strategy_table_rows(strategy_data)}
                </tbody>
            </table>
        </div>
        
        <!-- Symbol Performance Table -->
        <div class="card" style="margin-top: 20px;">
            <h2>📍 Performance by Symbol</h2>
            <table>
                <thead>
                    <tr>
                        <th>Symbol</th>
                        <th>Total Trades</th>
                        <th>Avg Win Rate</th>
                        <th>Total P&L</th>
                    </tr>
                </thead>
                <tbody>
                    {self._generate_symbol_table_rows(symbol_data)}
                </tbody>
            </table>
        </div>
        
        <footer>
            <p>🚀 Professional Trading Analysis System</p>
        </footer>
    </div>
    
    <script>
        // Chart.js configuration
        Chart.defaults.color = '#888';
        Chart.defaults.borderColor = 'rgba(255,255,255,0.1)';
        
        // Strategy P&L Chart
        new Chart(document.getElementById('strategyChart'), {{
            type: 'bar',
            data: {{
                labels: {list(strategy_data.index)},
                datasets: [{{
                    label: 'Total P&L (₹)',
                    data: {list(strategy_data['total_pnl'])},
                    backgroundColor: {self._get_colors(strategy_data['total_pnl'])},
                    borderRadius: 5,
                }}]
            }},
            options: {{
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }}
            }}
        }});
        
        // Symbol P&L Chart
        new Chart(document.getElementById('symbolChart'), {{
            type: 'doughnut',
            data: {{
                labels: {list(symbol_data.index)},
                datasets: [{{
                    data: {list(abs(symbol_data['total_pnl']))},
                    backgroundColor: ['#00d9ff', '#00ff88', '#ff6b6b', '#ffd93d', '#6b5ce7'],
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
            }}
        }});
        
        // Win Rate Chart
        new Chart(document.getElementById('winRateChart'), {{
            type: 'bar',
            data: {{
                labels: {list(strategy_data.index)},
                datasets: [{{
                    label: 'Win Rate (%)',
                    data: {list(strategy_data['win_rate'])},
                    backgroundColor: '#00d9ff',
                    borderRadius: 5,
                }}]
            }},
            options: {{
                indexAxis: 'y',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {{
                    legend: {{ display: false }}
                }},
                scales: {{
                    x: {{ max: 100 }}
                }}
            }}
        }});
        
        // Profit Factor Chart
        new Chart(document.getElementById('profitFactorChart'), {{
            type: 'radar',
            data: {{
                labels: {list(strategy_data.index)},
                datasets: [{{
                    label: 'Profit Factor',
                    data: {list(strategy_data['profit_factor'].clip(upper=5))},
                    backgroundColor: 'rgba(0,217,255,0.2)',
                    borderColor: '#00d9ff',
                    pointBackgroundColor: '#00d9ff',
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    r: {{
                        beginAtZero: true,
                        max: 5
                    }}
                }}
            }}
        }});
    </script>
</body>
</html>
"""
        return html
    
    def _get_colors(self, values) -> str:
        """Get color array based on values"""
        colors = ["'#00ff88'" if v >= 0 else "'#ff6b6b'" for v in values]
        return f"[{', '.join(colors)}]"
    
    def _generate_top_table_rows(self, df: pd.DataFrame) -> str:
        """Generate HTML rows for top combinations table"""
        rows = []
        for i, (_, row) in enumerate(df.iterrows(), 1):
            pnl_class = 'positive' if row['total_pnl'] >= 0 else 'negative'
            rows.append(f"""
                <tr>
                    <td>{i}</td>
                    <td>{row['strategy']}</td>
                    <td>{row['symbol']}</td>
                    <td>{row['total_trades']}</td>
                    <td><span class="badge {'success' if row['win_rate'] >= 50 else 'danger'}">{row['win_rate']:.1f}%</span></td>
                    <td class="{pnl_class}">₹{row['total_pnl']:,.0f}</td>
                    <td>{row['profit_factor']:.2f}</td>
                </tr>
            """)
        return '\n'.join(rows)
    
    def _generate_strategy_table_rows(self, df: pd.DataFrame) -> str:
        """Generate HTML rows for strategy table"""
        rows = []
        for strategy, row in df.iterrows():
            pnl_class = 'positive' if row['total_pnl'] >= 0 else 'negative'
            rows.append(f"""
                <tr>
                    <td>{strategy}</td>
                    <td>{int(row['total_trades'])}</td>
                    <td><span class="badge {'success' if row['win_rate'] >= 50 else 'danger'}">{row['win_rate']:.1f}%</span></td>
                    <td class="{pnl_class}">₹{row['total_pnl']:,.0f}</td>
                    <td>{row['profit_factor']:.2f}</td>
                </tr>
            """)
        return '\n'.join(rows)
    
    def _generate_symbol_table_rows(self, df: pd.DataFrame) -> str:
        """Generate HTML rows for symbol table"""
        rows = []
        for symbol, row in df.iterrows():
            pnl_class = 'positive' if row['total_pnl'] >= 0 else 'negative'
            rows.append(f"""
                <tr>
                    <td>{symbol}</td>
                    <td>{int(row['total_trades'])}</td>
                    <td><span class="badge {'success' if row['win_rate'] >= 50 else 'danger'}">{row['win_rate']:.1f}%</span></td>
                    <td class="{pnl_class}">₹{row['total_pnl']:,.0f}</td>
                </tr>
            """)
        return '\n'.join(rows)


def generate_dashboard(batch_name: str = None):
    """Generate dashboard from batch results"""
    generator = DashboardGenerator()
    generator.load_batch_results(batch_name)
    return generator.generate_dashboard()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Generate Performance Dashboard')
    parser.add_argument('--batch', type=str, default=None, help='Batch name to load')
    
    args = parser.parse_args()
    generate_dashboard(args.batch)
