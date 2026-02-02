"""
Multi-Day Backtester
======================
Tests strategies across multiple expiry days using historical data
Generates comprehensive performance reports
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime
import json
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from historical_data_loader import HistoricalDataLoader, get_expiry_dates_for_backtest
from config import BACKTEST_OUTPUT, NIFTY_LOT_SIZE, BANKNIFTY_LOT_SIZE


@dataclass
class TradeResult:
    """Result of a single trade"""
    entry_time: str
    exit_time: str
    symbol: str
    expiry_date: str
    option_type: str
    strike: int
    direction: str  # BUY or SELL
    entry_price: float
    exit_price: float
    quantity: int
    pnl: float
    pnl_percent: float
    exit_reason: str  # target, stoploss, expiry


@dataclass
class DayResult:
    """Result for a single expiry day"""
    date: str
    symbol: str
    trades: List[TradeResult] = field(default_factory=list)
    total_pnl: float = 0.0
    num_trades: int = 0
    winners: int = 0
    losers: int = 0


@dataclass
class BacktestSummary:
    """Overall backtest summary"""
    strategy_name: str
    symbol: str
    start_date: str
    end_date: str
    total_days: int
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    avg_pnl_per_trade: float
    avg_pnl_per_day: float
    max_win: float
    max_loss: float
    profit_factor: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    day_results: List[DayResult] = field(default_factory=list)


class OptionBacktestStrategy:
    """Base class for option backtest strategies"""
    
    def __init__(self, name: str, config: Dict = None):
        self.name = name
        self.config = config or {}
    
    def get_entry_signal(self, spot_price: float, strikes_data: Dict, 
                         timestamp: pd.Timestamp) -> Optional[Dict]:
        """
        Override this method to define entry logic
        Returns: {'option_type': 'CE'/'PE', 'strike': int, 'direction': 'BUY'/'SELL'}
        """
        raise NotImplementedError
    
    def get_exit_signal(self, trade: Dict, current_price: float, 
                        entry_price: float, timestamp: pd.Timestamp) -> Optional[str]:
        """
        Override this method to define exit logic
        Returns: 'target', 'stoploss', 'time', or None (hold)
        """
        raise NotImplementedError


class ATMStraddleSellStrategy(OptionBacktestStrategy):
    """
    Strategy: Sell ATM Straddle at a fixed time
    Exit: SL at 30% loss or target at 50% profit or expiry
    """
    
    def __init__(self):
        super().__init__("ATM Straddle Sell", {
            'entry_time': '09:45',
            'stoploss_pct': 30,
            'target_pct': 50,
            'exit_time': '15:20',
        })
    
    def get_entry_signal(self, spot_price: float, strikes_data: Dict,
                         timestamp: pd.Timestamp) -> Optional[Dict]:
        time_str = timestamp.strftime('%H:%M')
        
        # Only enter at specified time
        if time_str != self.config['entry_time']:
            return None
        
        # Find ATM strike
        strike_gap = 50 if spot_price < 30000 else 100
        atm_strike = round(spot_price / strike_gap) * strike_gap
        
        # Check if both CE and PE available
        if atm_strike in strikes_data.get('CE', {}) and atm_strike in strikes_data.get('PE', {}):
            return {
                'option_type': 'STRADDLE',
                'strike': int(atm_strike),
                'direction': 'SELL',
            }
        return None
    
    def get_exit_signal(self, trade: Dict, current_pnl_pct: float,
                        timestamp: pd.Timestamp) -> Optional[str]:
        time_str = timestamp.strftime('%H:%M')
        
        # Time-based exit
        if time_str >= self.config['exit_time']:
            return 'time'
        
        # Stop loss
        if current_pnl_pct <= -self.config['stoploss_pct']:
            return 'stoploss'
        
        # Target
        if current_pnl_pct >= self.config['target_pct']:
            return 'target'
        
        return None


class OTMStrangleSellStrategy(OptionBacktestStrategy):
    """
    Strategy: Sell OTM Strangle (2 strikes away from ATM)
    """
    
    def __init__(self):
        super().__init__("OTM Strangle Sell", {
            'entry_time': '09:45',
            'otm_distance': 2,  # 2 strikes OTM
            'stoploss_pct': 40,
            'target_pct': 40,
            'exit_time': '15:20',
        })
    
    def get_entry_signal(self, spot_price: float, strikes_data: Dict,
                         timestamp: pd.Timestamp) -> Optional[Dict]:
        time_str = timestamp.strftime('%H:%M')
        
        if time_str != self.config['entry_time']:
            return None
        
        strike_gap = 50 if spot_price < 30000 else 100
        atm_strike = round(spot_price / strike_gap) * strike_gap
        
        ce_strike = int(atm_strike + strike_gap * self.config['otm_distance'])
        pe_strike = int(atm_strike - strike_gap * self.config['otm_distance'])
        
        if ce_strike in strikes_data.get('CE', {}) and pe_strike in strikes_data.get('PE', {}):
            return {
                'option_type': 'STRANGLE',
                'ce_strike': ce_strike,
                'pe_strike': pe_strike,
                'direction': 'SELL',
            }
        return None
    
    def get_exit_signal(self, trade: Dict, current_pnl_pct: float,
                        timestamp: pd.Timestamp) -> Optional[str]:
        time_str = timestamp.strftime('%H:%M')
        
        if time_str >= self.config['exit_time']:
            return 'time'
        
        if current_pnl_pct <= -self.config['stoploss_pct']:
            return 'stoploss'
        
        if current_pnl_pct >= self.config['target_pct']:
            return 'target'
        
        return None


class MultiDayBacktester:
    """Run backtest across multiple expiry days"""
    
    def __init__(self, strategy: OptionBacktestStrategy, symbol: str = 'NIFTY',
                 initial_capital: float = 1000000):
        self.strategy = strategy
        self.symbol = symbol
        self.initial_capital = initial_capital
        self.loader = HistoricalDataLoader()
        
        self.lot_size = NIFTY_LOT_SIZE if 'NIFTY' in symbol else BANKNIFTY_LOT_SIZE
    
    def run(self, year: int = None, months: List[str] = None, 
            max_days: int = None) -> BacktestSummary:
        """Run backtest across available expiry days"""
        
        # Get all expiry dates
        all_dates = get_expiry_dates_for_backtest(self.symbol, year)
        
        # Filter by months if specified
        if months:
            all_dates = [(y, m, d) for y, m, d in all_dates if m in months]
        
        # Limit days if specified
        if max_days:
            all_dates = all_dates[:max_days]
        
        print(f"\n{'='*60}")
        print(f"MULTI-DAY BACKTEST: {self.strategy.name}")
        print(f"Symbol: {self.symbol}")
        print(f"Total Expiry Days: {len(all_dates)}")
        print(f"{'='*60}\n")
        
        day_results = []
        all_pnls = []
        
        for i, (year, month, day) in enumerate(all_dates):
            date_str = f"{year}-{month}-{day}"
            print(f"[{i+1}/{len(all_dates)}] Processing {date_str}...", end=" ")
            
            try:
                day_result = self._backtest_single_day(year, month, day)
                day_results.append(day_result)
                all_pnls.append(day_result.total_pnl)
                
                status = "✓" if day_result.total_pnl >= 0 else "✗"
                print(f"{status} PnL: ₹{day_result.total_pnl:,.0f}")
            except Exception as e:
                print(f"⚠ Error: {str(e)[:50]}")
        
        # Calculate summary
        summary = self._calculate_summary(day_results, all_pnls)
        
        return summary
    
    def _backtest_single_day(self, year: int, month: str, day: int) -> DayResult:
        """Backtest a single expiry day"""
        
        # Load data
        strikes_data = self.loader.load_expiry_day_data(year, self.symbol, month, day)
        
        if not strikes_data['CE'] and not strikes_data['PE']:
            raise ValueError("No strike data available")
        
        # Get timestamps from first available strike
        sample_df = None
        for ot in ['CE', 'PE']:
            if strikes_data[ot]:
                sample_df = list(strikes_data[ot].values())[0]
                break
        
        if sample_df is None:
            raise ValueError("No data available")
        
        date_str = f"{year}-{month}-{day}"
        result = DayResult(date=date_str, symbol=self.symbol)
        
        # Get only expiry day data
        expiry_date = sample_df['timestamp'].dt.date.max()
        
        # Filter to just expiry day
        for ot in ['CE', 'PE']:
            for strike in list(strikes_data[ot].keys()):
                df = strikes_data[ot][strike]
                strikes_data[ot][strike] = df[df['timestamp'].dt.date == expiry_date].copy()
        
        # Get filtered timestamps
        sample_df = list(strikes_data['CE'].values())[0] if strikes_data['CE'] else list(strikes_data['PE'].values())[0]
        
        if sample_df.empty:
            raise ValueError("No expiry day data")
        
        # Initialize trade tracking
        active_trade = None
        entry_premium = 0
        
        # Iterate through timestamps
        for _, row in sample_df.iterrows():
            timestamp = row['timestamp']
            
            # Get current spot estimate (average of ATM CE and PE)
            spot_estimate = self._estimate_spot(strikes_data, timestamp)
            if spot_estimate is None:
                continue
            
            # If no active trade, look for entry
            if active_trade is None:
                signal = self.strategy.get_entry_signal(spot_estimate, strikes_data, timestamp)
                
                if signal:
                    active_trade = signal.copy()
                    active_trade['entry_time'] = timestamp
                    
                    # Calculate entry premium
                    if signal['option_type'] == 'STRADDLE':
                        ce_price = self._get_price(strikes_data, 'CE', signal['strike'], timestamp)
                        pe_price = self._get_price(strikes_data, 'PE', signal['strike'], timestamp)
                        if ce_price and pe_price:
                            entry_premium = ce_price + pe_price
                            active_trade['ce_price'] = ce_price
                            active_trade['pe_price'] = pe_price
                        else:
                            active_trade = None
                    
                    elif signal['option_type'] == 'STRANGLE':
                        ce_price = self._get_price(strikes_data, 'CE', signal['ce_strike'], timestamp)
                        pe_price = self._get_price(strikes_data, 'PE', signal['pe_strike'], timestamp)
                        if ce_price and pe_price:
                            entry_premium = ce_price + pe_price
                            active_trade['ce_price'] = ce_price
                            active_trade['pe_price'] = pe_price
                        else:
                            active_trade = None
            
            # If active trade, check for exit
            else:
                # Calculate current PnL %
                if active_trade['option_type'] == 'STRADDLE':
                    ce_current = self._get_price(strikes_data, 'CE', active_trade['strike'], timestamp)
                    pe_current = self._get_price(strikes_data, 'PE', active_trade['strike'], timestamp)
                elif active_trade['option_type'] == 'STRANGLE':
                    ce_current = self._get_price(strikes_data, 'CE', active_trade['ce_strike'], timestamp)
                    pe_current = self._get_price(strikes_data, 'PE', active_trade['pe_strike'], timestamp)
                
                if ce_current is None or pe_current is None:
                    continue
                
                current_premium = ce_current + pe_current
                
                # For selling, profit when premium decreases
                if active_trade['direction'] == 'SELL':
                    pnl_pct = ((entry_premium - current_premium) / entry_premium) * 100
                else:
                    pnl_pct = ((current_premium - entry_premium) / entry_premium) * 100
                
                # Check exit
                exit_reason = self.strategy.get_exit_signal(active_trade, pnl_pct, timestamp)
                
                if exit_reason:
                    # Calculate final PnL
                    pnl_points = entry_premium - current_premium if active_trade['direction'] == 'SELL' else current_premium - entry_premium
                    pnl_amount = pnl_points * self.lot_size
                    
                    trade_result = TradeResult(
                        entry_time=str(active_trade['entry_time']),
                        exit_time=str(timestamp),
                        symbol=self.symbol,
                        expiry_date=date_str,
                        option_type=active_trade['option_type'],
                        strike=active_trade.get('strike', 0),
                        direction=active_trade['direction'],
                        entry_price=entry_premium,
                        exit_price=current_premium,
                        quantity=self.lot_size,
                        pnl=pnl_amount,
                        pnl_percent=pnl_pct,
                        exit_reason=exit_reason
                    )
                    
                    result.trades.append(trade_result)
                    result.total_pnl += pnl_amount
                    result.num_trades += 1
                    
                    if pnl_amount > 0:
                        result.winners += 1
                    else:
                        result.losers += 1
                    
                    active_trade = None
        
        return result
    
    def _estimate_spot(self, strikes_data: Dict, timestamp: pd.Timestamp) -> Optional[float]:
        """Estimate spot price from options data"""
        # Use middle strike as estimate
        all_strikes = set()
        for ot in ['CE', 'PE']:
            all_strikes.update(strikes_data[ot].keys())
        
        if not all_strikes:
            return None
        
        return sorted(all_strikes)[len(all_strikes) // 2]
    
    def _get_price(self, strikes_data: Dict, option_type: str, strike: int, 
                   timestamp: pd.Timestamp) -> Optional[float]:
        """Get option price at a specific time"""
        if strike not in strikes_data.get(option_type, {}):
            return None
        
        df = strikes_data[option_type][strike]
        row = df[df['timestamp'] == timestamp]
        
        if row.empty:
            # Find closest timestamp
            df_sorted = df.iloc[(df['timestamp'] - timestamp).abs().argsort()[:1]]
            if not df_sorted.empty:
                return df_sorted['close'].iloc[0]
            return None
        
        return row['close'].iloc[0]
    
    def _calculate_summary(self, day_results: List[DayResult], 
                          all_pnls: List[float]) -> BacktestSummary:
        """Calculate overall summary statistics"""
        
        total_trades = sum(d.num_trades for d in day_results)
        winning_trades = sum(d.winners for d in day_results)
        losing_trades = sum(d.losers for d in day_results)
        total_pnl = sum(all_pnls)
        
        all_trade_pnls = []
        for dr in day_results:
            for t in dr.trades:
                all_trade_pnls.append(t.pnl)
        
        # Draw down calculation
        cumulative = np.cumsum([self.initial_capital] + all_pnls)
        peak = np.maximum.accumulate(cumulative)
        drawdown = peak - cumulative
        max_dd = drawdown.max()
        max_dd_pct = (max_dd / peak.max()) * 100 if peak.max() > 0 else 0
        
        # Profit factor
        gross_profit = sum(p for p in all_trade_pnls if p > 0)
        gross_loss = abs(sum(p for p in all_trade_pnls if p < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Sharpe ratio (daily)
        if len(all_pnls) > 1 and np.std(all_pnls) > 0:
            sharpe = np.sqrt(252) * np.mean(all_pnls) / np.std(all_pnls)
        else:
            sharpe = 0
        
        return BacktestSummary(
            strategy_name=self.strategy.name,
            symbol=self.symbol,
            start_date=day_results[0].date if day_results else "",
            end_date=day_results[-1].date if day_results else "",
            total_days=len(day_results),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=(winning_trades / total_trades * 100) if total_trades > 0 else 0,
            total_pnl=total_pnl,
            avg_pnl_per_trade=(total_pnl / total_trades) if total_trades > 0 else 0,
            avg_pnl_per_day=(total_pnl / len(day_results)) if day_results else 0,
            max_win=max(all_trade_pnls) if all_trade_pnls else 0,
            max_loss=min(all_trade_pnls) if all_trade_pnls else 0,
            profit_factor=profit_factor,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            sharpe_ratio=sharpe,
            day_results=day_results
        )
    
    def print_report(self, summary: BacktestSummary):
        """Print formatted backtest report"""
        print(f"""
{'='*70}
                    BACKTEST REPORT: {summary.strategy_name}
{'='*70}

📅 PERIOD
   Symbol:      {summary.symbol}
   Start:       {summary.start_date}
   End:         {summary.end_date}
   Total Days:  {summary.total_days}

📊 TRADE STATISTICS
   Total Trades:     {summary.total_trades}
   Winners:          {summary.winning_trades}
   Losers:           {summary.losing_trades}
   Win Rate:         {summary.win_rate:.1f}%

💰 PROFIT & LOSS
   Total P&L:        ₹{summary.total_pnl:,.0f}
   Avg P&L/Trade:    ₹{summary.avg_pnl_per_trade:,.0f}
   Avg P&L/Day:      ₹{summary.avg_pnl_per_day:,.0f}
   Max Win:          ₹{summary.max_win:,.0f}
   Max Loss:         ₹{summary.max_loss:,.0f}
   Profit Factor:    {summary.profit_factor:.2f}

⚠️ RISK METRICS
   Max Drawdown:     ₹{summary.max_drawdown:,.0f} ({summary.max_drawdown_pct:.1f}%)
   Sharpe Ratio:     {summary.sharpe_ratio:.2f}

{'='*70}
""")
    
    def save_results(self, summary: BacktestSummary, name: str = None):
        """Save results to files"""
        name = name or f"{self.symbol}_{self.strategy.name.replace(' ', '_')}"
        output_dir = BACKTEST_OUTPUT / "multi_day" / name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save summary
        summary_dict = {
            'strategy_name': summary.strategy_name,
            'symbol': summary.symbol,
            'start_date': summary.start_date,
            'end_date': summary.end_date,
            'total_days': summary.total_days,
            'total_trades': summary.total_trades,
            'winning_trades': summary.winning_trades,
            'losing_trades': summary.losing_trades,
            'win_rate': summary.win_rate,
            'total_pnl': summary.total_pnl,
            'profit_factor': summary.profit_factor,
            'max_drawdown': summary.max_drawdown,
            'sharpe_ratio': summary.sharpe_ratio,
        }
        
        with open(output_dir / 'summary.json', 'w') as f:
            json.dump(summary_dict, f, indent=2)
        
        # Save daily results
        daily_data = []
        for dr in summary.day_results:
            daily_data.append({
                'date': dr.date,
                'symbol': dr.symbol,
                'num_trades': dr.num_trades,
                'winners': dr.winners,
                'losers': dr.losers,
                'pnl': dr.total_pnl,
            })
        
        pd.DataFrame(daily_data).to_csv(output_dir / 'daily_results.csv', index=False)
        
        # Save all trades
        all_trades = []
        for dr in summary.day_results:
            for t in dr.trades:
                all_trades.append({
                    'entry_time': t.entry_time,
                    'exit_time': t.exit_time,
                    'symbol': t.symbol,
                    'expiry_date': t.expiry_date,
                    'option_type': t.option_type,
                    'strike': t.strike,
                    'direction': t.direction,
                    'entry_price': t.entry_price,
                    'exit_price': t.exit_price,
                    'quantity': t.quantity,
                    'pnl': t.pnl,
                    'pnl_percent': t.pnl_percent,
                    'exit_reason': t.exit_reason,
                })
        
        pd.DataFrame(all_trades).to_csv(output_dir / 'all_trades.csv', index=False)
        
        print(f"Results saved to: {output_dir}")


def run_multi_day_backtest(symbol: str = 'NIFTY', strategy: str = 'straddle',
                           year: int = None, max_days: int = None):
    """Convenience function to run backtest"""
    
    strategies = {
        'straddle': ATMStraddleSellStrategy(),
        'strangle': OTMStrangleSellStrategy(),
    }
    
    if strategy not in strategies:
        print(f"Available strategies: {list(strategies.keys())}")
        return
    
    bt = MultiDayBacktester(strategies[strategy], symbol)
    summary = bt.run(year=year, max_days=max_days)
    bt.print_report(summary)
    bt.save_results(summary)
    
    return summary


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Multi-Day Backtester')
    parser.add_argument('--symbol', type=str, default='NIFTY', help='Symbol to backtest')
    parser.add_argument('--strategy', type=str, default='straddle', 
                        choices=['straddle', 'strangle'], help='Strategy to test')
    parser.add_argument('--year', type=int, default=None, help='Year to backtest')
    parser.add_argument('--max-days', type=int, default=None, help='Max expiry days to test')
    
    args = parser.parse_args()
    
    run_multi_day_backtest(
        symbol=args.symbol,
        strategy=args.strategy,
        year=args.year,
        max_days=args.max_days
    )
