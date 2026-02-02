"""
Professional Backtesting Engine
Tests strategies on historical data with realistic assumptions
"""
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import sys
sys.path.append(str(Path(__file__).parent.parent))
from config import BACKTEST_OUTPUT, NIFTY_LOT_SIZE, BANKNIFTY_LOT_SIZE


class TradeStatus(Enum):
    OPEN = "open"
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"
    TIME_EXIT = "time_exit"


@dataclass
class Trade:
    """Represents a single trade"""
    entry_time: pd.Timestamp
    direction: int  # 1 for long, -1 for short
    entry_price: float
    stop_loss: float
    target: float
    quantity: int
    
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    status: TradeStatus = TradeStatus.OPEN
    pnl: float = 0.0
    pnl_points: float = 0.0
    r_multiple: float = 0.0
    max_favorable: float = 0.0
    max_adverse: float = 0.0


@dataclass
class BacktestResult:
    """Results of a backtest run"""
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    
    # Summary metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    total_pnl: float = 0.0
    gross_profit: float = 0.0
    gross_loss: float = 0.0
    profit_factor: float = 0.0
    
    avg_win: float = 0.0
    avg_loss: float = 0.0
    avg_rr: float = 0.0
    expectancy: float = 0.0
    
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    recovery_factor: float = 0.0
    
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0


class RiskManager:
    """Position sizing and risk control"""
    
    def __init__(self, capital: float, risk_per_trade: float = 1.0,
                 max_daily_loss: float = 2.0, max_drawdown: float = 15.0):
        """
        capital: Starting capital
        risk_per_trade: % of capital to risk per trade
        max_daily_loss: Max % loss allowed per day
        max_drawdown: Max % drawdown before stopping
        """
        self.initial_capital = capital
        self.capital = capital
        self.peak_capital = capital
        self.risk_per_trade = risk_per_trade
        self.max_daily_loss = max_daily_loss
        self.max_drawdown = max_drawdown
        
        self.daily_pnl = 0.0
        self.current_date = None
    
    def calculate_position_size(self, entry: float, stop_loss: float, 
                                symbol: str = 'NIFTY') -> int:
        """Calculate position size based on risk budget"""
        lot_size = NIFTY_LOT_SIZE if symbol == 'NIFTY' else BANKNIFTY_LOT_SIZE
        
        # Risk amount
        risk_amount = self.capital * (self.risk_per_trade / 100)
        
        # Points at risk
        points_at_risk = abs(entry - stop_loss)
        if points_at_risk == 0:
            return 0
        
        # Max quantity based on risk
        max_quantity = risk_amount / points_at_risk
        
        # Round to lot size
        num_lots = int(max_quantity / lot_size)
        return max(0, num_lots * lot_size)
    
    def can_trade(self, trade_date: pd.Timestamp) -> tuple:
        """Check if trading is allowed based on risk limits"""
        # Reset daily PnL on new day
        if self.current_date != trade_date.date():
            self.daily_pnl = 0.0
            self.current_date = trade_date.date()
        
        # Check daily loss limit
        daily_loss_pct = abs(self.daily_pnl) / self.capital * 100 if self.daily_pnl < 0 else 0
        if daily_loss_pct >= self.max_daily_loss:
            return False, "Daily loss limit hit"
        
        # Check max drawdown
        current_dd = (self.peak_capital - self.capital) / self.peak_capital * 100
        if current_dd >= self.max_drawdown:
            return False, "Max drawdown limit hit"
        
        return True, "OK"
    
    def update(self, pnl: float):
        """Update capital and metrics after a trade"""
        self.capital += pnl
        self.daily_pnl += pnl
        self.peak_capital = max(self.peak_capital, self.capital)
    
    def get_drawdown(self) -> float:
        """Current drawdown percentage"""
        if self.peak_capital == 0:
            return 0.0
        return (self.peak_capital - self.capital) / self.peak_capital * 100


class Backtester:
    """Main backtesting engine"""
    
    def __init__(self, signals_df: pd.DataFrame, price_df: pd.DataFrame,
                 initial_capital: float = 1000000, symbol: str = 'NIFTY'):
        """
        signals_df: DataFrame with signals (must have: timestamp, direction, entry, stop_loss, target)
        price_df: OHLCV DataFrame (must have: timestamp, open, high, low, close)
        """
        self.signals = signals_df.copy()
        self.prices = price_df.copy()
        self.symbol = symbol
        self.initial_capital = initial_capital
        
        self._prepare_data()
        self.risk_manager = RiskManager(initial_capital)
        self.trades: List[Trade] = []
        self.equity_curve = [initial_capital]
    
    def _prepare_data(self):
        """Prepare data for backtesting"""
        # Ensure timestamp index
        if 'timestamp' in self.signals.columns:
            self.signals['timestamp'] = pd.to_datetime(self.signals['timestamp'])
            self.signals.set_index('timestamp', inplace=True)
        
        if 'timestamp' in self.prices.columns:
            self.prices['timestamp'] = pd.to_datetime(self.prices['timestamp'])
            self.prices.set_index('timestamp', inplace=True)
    
    def run(self, slippage_pct: float = 0.01, commission_per_lot: float = 20) -> BacktestResult:
        """
        Run backtest with realistic execution
        slippage_pct: Slippage as % of price
        commission_per_lot: Commission per lot traded
        """
        lot_size = NIFTY_LOT_SIZE if self.symbol == 'NIFTY' else BANKNIFTY_LOT_SIZE
        
        for signal_time, signal in self.signals.iterrows():
            # Check if trading allowed
            can_trade, reason = self.risk_manager.can_trade(signal_time)
            if not can_trade:
                continue
            
            # Parse direction
            direction = 1 if signal.get('direction', 'LONG') == 'LONG' else -1
            
            # Entry with slippage
            entry_price = signal['entry'] * (1 + slippage_pct/100 * direction)
            stop_loss = signal['stop_loss']
            target = signal['target']
            
            # Calculate position size
            quantity = self.risk_manager.calculate_position_size(
                entry_price, stop_loss, self.symbol
            )
            
            if quantity == 0:
                continue
            
            # Create trade
            trade = Trade(
                entry_time=signal_time,
                direction=direction,
                entry_price=entry_price,
                stop_loss=stop_loss,
                target=target,
                quantity=quantity
            )
            
            # Simulate trade outcome
            self._simulate_trade(trade, slippage_pct)
            
            # Calculate PnL
            if trade.exit_price:
                trade.pnl_points = (trade.exit_price - trade.entry_price) * trade.direction
                trade.pnl = trade.pnl_points * trade.quantity
                
                # Subtract commission
                num_lots = trade.quantity // lot_size
                commission = commission_per_lot * num_lots * 2  # Entry + Exit
                trade.pnl -= commission
                
                # Calculate R-multiple
                risk_per_unit = abs(trade.entry_price - trade.stop_loss)
                trade.r_multiple = trade.pnl_points / risk_per_unit if risk_per_unit > 0 else 0
                
                # Update risk manager
                self.risk_manager.update(trade.pnl)
                self.equity_curve.append(self.risk_manager.capital)
            
            self.trades.append(trade)
        
        return self._calculate_results()
    
    def _simulate_trade(self, trade: Trade, slippage_pct: float):
        """Simulate trade execution bar by bar"""
        # Find bars after entry
        future_bars = self.prices[self.prices.index > trade.entry_time]
        
        for bar_time, bar in future_bars.iterrows():
            # Track max adverse/favorable excursion
            if trade.direction == 1:
                trade.max_favorable = max(trade.max_favorable, bar['high'] - trade.entry_price)
                trade.max_adverse = max(trade.max_adverse, trade.entry_price - bar['low'])
            else:
                trade.max_favorable = max(trade.max_favorable, trade.entry_price - bar['low'])
                trade.max_adverse = max(trade.max_adverse, bar['high'] - trade.entry_price)
            
            # Check stop loss
            stop_hit = (trade.direction == 1 and bar['low'] <= trade.stop_loss) or \
                       (trade.direction == -1 and bar['high'] >= trade.stop_loss)
            
            # Check target
            target_hit = (trade.direction == 1 and bar['high'] >= trade.target) or \
                         (trade.direction == -1 and bar['low'] <= trade.target)
            
            if stop_hit and target_hit:
                # Need to determine which hit first
                # Pessimistic assumption: stop hit first
                trade.exit_price = trade.stop_loss * (1 - slippage_pct/100 * trade.direction)
                trade.exit_time = bar_time
                trade.status = TradeStatus.LOSS
                return
            
            if stop_hit:
                trade.exit_price = trade.stop_loss * (1 - slippage_pct/100 * trade.direction)
                trade.exit_time = bar_time
                trade.status = TradeStatus.LOSS
                return
            
            if target_hit:
                trade.exit_price = trade.target * (1 - slippage_pct/100 * trade.direction)
                trade.exit_time = bar_time
                trade.status = TradeStatus.WIN
                return
        
        # End of data - close at last price
        if not future_bars.empty:
            trade.exit_time = future_bars.index[-1]
            trade.exit_price = future_bars.iloc[-1]['close']
            trade.status = TradeStatus.TIME_EXIT
    
    def _calculate_results(self) -> BacktestResult:
        """Calculate performance metrics"""
        result = BacktestResult()
        result.trades = self.trades
        result.equity_curve = self.equity_curve
        
        if not self.trades:
            return result
        
        closed_trades = [t for t in self.trades if t.status != TradeStatus.OPEN]
        
        result.total_trades = len(closed_trades)
        result.winning_trades = len([t for t in closed_trades if t.pnl > 0])
        result.losing_trades = len([t for t in closed_trades if t.pnl < 0])
        
        if result.total_trades > 0:
            result.win_rate = result.winning_trades / result.total_trades * 100
        
        # PnL metrics
        result.total_pnl = sum(t.pnl for t in closed_trades)
        result.gross_profit = sum(t.pnl for t in closed_trades if t.pnl > 0)
        result.gross_loss = abs(sum(t.pnl for t in closed_trades if t.pnl < 0))
        
        if result.gross_loss > 0:
            result.profit_factor = result.gross_profit / result.gross_loss
        
        # Average trade metrics
        if result.winning_trades > 0:
            result.avg_win = result.gross_profit / result.winning_trades
        if result.losing_trades > 0:
            result.avg_loss = result.gross_loss / result.losing_trades
        
        r_multiples = [t.r_multiple for t in closed_trades]
        result.avg_rr = np.mean(r_multiples) if r_multiples else 0
        
        # Expectancy
        if result.total_trades > 0:
            result.expectancy = result.total_pnl / result.total_trades
        
        # Drawdown
        equity = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / peak * 100
        result.max_drawdown_pct = drawdown.max()
        result.max_drawdown = (peak - equity).max()
        
        if result.max_drawdown > 0:
            result.recovery_factor = result.total_pnl / result.max_drawdown
        
        # Risk-adjusted returns
        returns = np.diff(equity) / equity[:-1]
        if len(returns) > 0 and returns.std() > 0:
            result.sharpe_ratio = np.sqrt(252) * returns.mean() / returns.std()
            
            downside_returns = returns[returns < 0]
            if len(downside_returns) > 0 and downside_returns.std() > 0:
                result.sortino_ratio = np.sqrt(252) * returns.mean() / downside_returns.std()
        
        return result
    
    def generate_report(self, result: BacktestResult) -> str:
        """Generate text report of backtest results"""
        report = f"""
═══════════════════════════════════════════════════════════
                   BACKTEST RESULTS
═══════════════════════════════════════════════════════════

📊 TRADE STATISTICS
───────────────────────────────────────────────────────────
Total Trades:       {result.total_trades}
Winning Trades:     {result.winning_trades}
Losing Trades:      {result.losing_trades}
Win Rate:           {result.win_rate:.1f}%

💰 PROFIT & LOSS
───────────────────────────────────────────────────────────
Total P&L:          ₹{result.total_pnl:,.2f}
Gross Profit:       ₹{result.gross_profit:,.2f}
Gross Loss:         ₹{result.gross_loss:,.2f}
Profit Factor:      {result.profit_factor:.2f}

📈 TRADE METRICS
───────────────────────────────────────────────────────────
Avg Win:            ₹{result.avg_win:,.2f}
Avg Loss:           ₹{result.avg_loss:,.2f}
Avg R:R:            {result.avg_rr:.2f}R
Expectancy:         ₹{result.expectancy:,.2f}

⚠️ RISK METRICS
───────────────────────────────────────────────────────────
Max Drawdown:       ₹{result.max_drawdown:,.2f} ({result.max_drawdown_pct:.1f}%)
Recovery Factor:    {result.recovery_factor:.2f}
Sharpe Ratio:       {result.sharpe_ratio:.2f}
Sortino Ratio:      {result.sortino_ratio:.2f}

═══════════════════════════════════════════════════════════
"""
        return report
    
    def save_results(self, result: BacktestResult, name: str):
        """Save backtest results to files"""
        output_dir = BACKTEST_OUTPUT / name
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Save trades
        trades_df = pd.DataFrame([
            {
                'entry_time': t.entry_time,
                'exit_time': t.exit_time,
                'direction': 'LONG' if t.direction == 1 else 'SHORT',
                'entry_price': t.entry_price,
                'exit_price': t.exit_price,
                'stop_loss': t.stop_loss,
                'target': t.target,
                'quantity': t.quantity,
                'pnl': t.pnl,
                'pnl_points': t.pnl_points,
                'r_multiple': t.r_multiple,
                'status': t.status.value,
            }
            for t in result.trades
        ])
        trades_df.to_csv(output_dir / 'trades.csv', index=False)
        
        # Save equity curve
        pd.DataFrame({'equity': result.equity_curve}).to_csv(
            output_dir / 'equity_curve.csv', index=False
        )
        
        # Save report
        with open(output_dir / 'report.txt', 'w') as f:
            f.write(self.generate_report(result))


if __name__ == "__main__":
    print("Backtesting engine ready.")
    print("Usage:")
    print("  from backtest.engine import Backtester")
    print("  bt = Backtester(signals_df, prices_df)")
    print("  result = bt.run()")
    print("  print(bt.generate_report(result))")
