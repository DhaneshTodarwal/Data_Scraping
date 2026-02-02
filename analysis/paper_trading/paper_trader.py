"""
Paper Trading Engine
======================
Real-time paper trading simulation with live market data
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Callable
from datetime import datetime, timezone, timedelta, time
import time as time_module
import threading
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

from paper_trading.portfolio import Portfolio, Position
from backtest.strategies import (
    ALL_STRATEGIES, get_strategy, 
    ShortStraddleStrategy, ShortStrangleStrategy
)

# Try importing alerts
try:
    from alerts import alert_signal, alert_entry, alert_exit, send_daily_summary
    ALERTS_AVAILABLE = True
except ImportError:
    ALERTS_AVAILABLE = False

# Try importing AngelOne API for live data
try:
    from angelone_api import AngelOneAPI
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False

IST = timezone(timedelta(hours=5, minutes=30))


class PaperTrader:
    """
    Paper trading engine that simulates real trading
    without using real money
    """
    
    def __init__(self, initial_capital: float = 1000000):
        self.portfolio = Portfolio(initial_capital)
        self.strategies = {}  # Active strategies
        self.is_running = False
        self.market_data = {}  # Current market prices
        
        # Market timing
        self.market_open = time(9, 15)
        self.market_close = time(15, 30)
        
        # Config
        self.check_interval = 60  # seconds
        self.enable_alerts = ALERTS_AVAILABLE
    
    def add_strategy(self, strategy_key: str, symbol: str = 'NIFTY',
                     lots: int = 1, config: Dict = None):
        """
        Add a strategy to paper trade
        
        Args:
            strategy_key: Key from ALL_STRATEGIES (e.g., 'short_straddle')
            symbol: Trading symbol (NIFTY, BANKNIFTY, etc.)
            lots: Number of lots to trade
            config: Override strategy configuration
        """
        strategy = get_strategy(strategy_key)
        
        if config:
            strategy.config.update(config)
        
        key = f"{symbol}_{strategy_key}"
        self.strategies[key] = {
            'strategy': strategy,
            'symbol': symbol,
            'lots': lots,
            'active': True,
        }
        
        print(f"✅ Added: {strategy.name} on {symbol} ({lots} lot(s))")
    
    def remove_strategy(self, symbol: str, strategy_key: str):
        """Remove a strategy"""
        key = f"{symbol}_{strategy_key}"
        if key in self.strategies:
            del self.strategies[key]
            print(f"✅ Removed: {strategy_key} on {symbol}")
    
    def is_market_open(self) -> bool:
        """Check if market is open"""
        now = datetime.now(IST)
        current_time = now.time()
        
        # Weekend check
        if now.weekday() >= 5:
            return False
        
        return self.market_open <= current_time <= self.market_close
    
    def get_spot_price(self, symbol: str) -> Optional[float]:
        """Get current spot price (simulated or live)"""
        # If API available, use live data
        if API_AVAILABLE:
            try:
                # This would be the actual API call
                pass
            except Exception:
                pass
        
        # Return from cached data
        return self.market_data.get(f"{symbol}_spot")
    
    def get_option_premium(self, symbol: str, strike: int, 
                           option_type: str) -> Optional[float]:
        """Get current option premium"""
        key = f"{symbol}_{option_type}_{strike}"
        return self.market_data.get(key)
    
    def update_market_data(self, data: Dict):
        """Update market data from external source"""
        self.market_data.update(data)
    
    def simulate_market_data(self, symbol: str):
        """Simulate market data for testing"""
        import random
        
        # Simulate spot price
        base_prices = {
            'NIFTY': 24500,
            'BANKNIFTY': 52000,
            'FINNIFTY': 23500,
            'SENSEX': 81000,
        }
        
        base = base_prices.get(symbol, 24500)
        spot = base + random.uniform(-50, 50)
        self.market_data[f"{symbol}_spot"] = spot
        
        # Simulate option premiums
        gap = 50 if base < 30000 else 100
        atm = round(spot / gap) * gap
        
        for i in range(-3, 4):
            strike = int(atm + i * gap)
            ce_premium = max(10, (spot - strike) + random.uniform(50, 150))
            pe_premium = max(10, (strike - spot) + random.uniform(50, 150))
            
            self.market_data[f"{symbol}_CE_{strike}"] = ce_premium
            self.market_data[f"{symbol}_PE_{strike}"] = pe_premium
        
        return spot, atm
    
    def check_entry_signals(self):
        """Check all strategies for entry signals"""
        for key, config in self.strategies.items():
            if not config['active']:
                continue
            
            strategy = config['strategy']
            symbol = config['symbol']
            lots = config['lots']
            
            # Skip if already have position for this strategy
            for pos in self.portfolio.get_open_positions():
                if pos.symbol == symbol and pos.strategy == strategy.name:
                    continue
            
            # Get market data
            spot = self.get_spot_price(symbol)
            if not spot:
                continue
            
            # Build strikes_data structure
            gap = 50 if spot < 30000 else 100
            atm = round(spot / gap) * gap
            
            strikes_data = {'CE': {}, 'PE': {}}
            for i in range(-5, 6):
                strike = int(atm + i * gap)
                ce_price = self.get_option_premium(symbol, strike, 'CE')
                pe_price = self.get_option_premium(symbol, strike, 'PE')
                if ce_price:
                    strikes_data['CE'][strike] = pd.DataFrame({'close': [ce_price]})
                if pe_price:
                    strikes_data['PE'][strike] = pd.DataFrame({'close': [pe_price]})
            
            # Check for entry signal
            timestamp = pd.Timestamp(datetime.now(IST))
            signal = strategy.get_entry_signal(spot, strikes_data, timestamp)
            
            if signal:
                self._execute_entry(symbol, strategy, signal, lots)
    
    def _execute_entry(self, symbol: str, strategy, signal: Dict, lots: int):
        """Execute a paper trade entry"""
        
        # Calculate entry premium
        entry_premium = 0
        legs = {}
        
        if signal.get('type') == 'STRADDLE':
            strike = signal['strike']
            ce_price = self.get_option_premium(symbol, strike, 'CE')
            pe_price = self.get_option_premium(symbol, strike, 'PE')
            if ce_price and pe_price:
                entry_premium = ce_price + pe_price
                legs = {'CE': strike, 'PE': strike}
        
        elif signal.get('type') == 'STRANGLE':
            ce_strike = signal['ce_strike']
            pe_strike = signal['pe_strike']
            ce_price = self.get_option_premium(symbol, ce_strike, 'CE')
            pe_price = self.get_option_premium(symbol, pe_strike, 'PE')
            if ce_price and pe_price:
                entry_premium = ce_price + pe_price
                legs = {'CE': ce_strike, 'PE': pe_strike}
        
        if entry_premium <= 0:
            return
        
        # Open position
        position = self.portfolio.open_position(
            symbol=symbol,
            strategy=strategy.name,
            strategy_type=signal.get('type'),
            direction=signal.get('direction', 'SELL'),
            entry_premium=entry_premium,
            sl_pct=strategy.config.get('stoploss_pct', 30),
            target_pct=strategy.config.get('target_pct', 50),
            legs=legs,
            lots=lots,
        )
        
        print(f"\n🔔 ENTRY: {strategy.name} on {symbol}")
        print(f"   Premium: ₹{entry_premium:.2f}")
        print(f"   SL: ₹{position.stop_loss:.2f} | Target: ₹{position.target:.2f}")
        
        # Send alert
        if self.enable_alerts:
            alert_entry({
                'symbol': symbol,
                'strategy': strategy.name,
                'action': signal.get('direction', 'SELL'),
                'strike': legs,
                'premium': entry_premium,
                'quantity': position.quantity,
                'target': position.target,
                'stop_loss': position.stop_loss,
            })
    
    def check_exits(self):
        """Check all positions for exit conditions"""
        for position in self.portfolio.get_open_positions():
            # Get current premium
            current_premium = self._get_current_premium(position)
            
            if current_premium is None:
                continue
            
            self.portfolio.update_position(position.id, current_premium)
            
            # Check exit conditions
            exit_reason = self.portfolio.check_exit_conditions(position.id)
            
            if exit_reason:
                self._execute_exit(position, exit_reason)
    
    def _get_current_premium(self, position: Position) -> Optional[float]:
        """Get current premium for a position"""
        symbol = position.symbol
        legs = position.legs
        
        if position.strategy_type in ['STRADDLE', 'STRANGLE']:
            ce_strike = legs.get('CE')
            pe_strike = legs.get('PE')
            
            ce_price = self.get_option_premium(symbol, ce_strike, 'CE')
            pe_price = self.get_option_premium(symbol, pe_strike, 'PE')
            
            if ce_price and pe_price:
                return ce_price + pe_price
        
        return None
    
    def _execute_exit(self, position: Position, exit_reason: str):
        """Execute a paper trade exit"""
        trade = self.portfolio.close_position(position.id, exit_reason=exit_reason)
        
        if trade:
            pnl_emoji = "🟢" if trade.pnl >= 0 else "🔴"
            print(f"\n{pnl_emoji} EXIT: {position.strategy} on {position.symbol}")
            print(f"   Reason: {exit_reason}")
            print(f"   P&L: ₹{trade.pnl:,.2f} ({trade.pnl_percent:.1f}%)")
            
            # Send alert
            if self.enable_alerts:
                alert_exit({
                    'symbol': position.symbol,
                    'strategy': position.strategy,
                    'exit_reason': exit_reason,
                    'entry_price': trade.entry_premium,
                    'exit_price': trade.exit_premium,
                    'pnl': trade.pnl,
                })
    
    def run_simulation(self, duration_minutes: int = 60):
        """
        Run paper trading simulation for specified duration
        Uses simulated market data
        """
        print("\n" + "="*60)
        print("       PAPER TRADING SIMULATION")
        print("="*60)
        print(f"Duration: {duration_minutes} minutes")
        print(f"Strategies: {[s['strategy'].name for s in self.strategies.values()]}")
        print("="*60)
        
        start_time = datetime.now()
        end_time = start_time + timedelta(minutes=duration_minutes)
        
        self.is_running = True
        
        while self.is_running and datetime.now() < end_time:
            # Simulate market data
            for key in self.strategies:
                symbol = self.strategies[key]['symbol']
                self.simulate_market_data(symbol)
            
            # Check entries
            self.check_entry_signals()
            
            # Check exits
            self.check_exits()
            
            # Print status every minute
            elapsed = (datetime.now() - start_time).seconds // 60
            remaining = duration_minutes - elapsed
            print(f"\r⏱ Running... {remaining}min remaining | "
                  f"Positions: {len(self.portfolio.positions)} | "
                  f"P&L: ₹{sum(t.pnl for t in self.portfolio.trades):,.0f}", 
                  end="")
            
            time_module.sleep(5)  # 5 second intervals for simulation
        
        self.is_running = False
        print("\n")
        self.portfolio.print_summary()
    
    def start_live(self):
        """Start live paper trading"""
        print("\n" + "="*60)
        print("       LIVE PAPER TRADING")
        print("="*60)
        print("Press Ctrl+C to stop")
        print("="*60)
        
        self.is_running = True
        
        try:
            while self.is_running:
                if not self.is_market_open():
                    print("\r⏸ Market closed. Waiting...", end="")
                    time_module.sleep(60)
                    continue
                
                # Update market data here (from API)
                for key in self.strategies:
                    symbol = self.strategies[key]['symbol']
                    # In live mode, this would fetch real data
                    self.simulate_market_data(symbol)  # Replace with live data
                
                self.check_entry_signals()
                self.check_exits()
                
                # Status
                print(f"\r⏱ Live | Positions: {len(self.portfolio.positions)} | "
                      f"P&L: ₹{sum(t.pnl for t in self.portfolio.trades):,.0f}", end="")
                
                time_module.sleep(self.check_interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Stopping paper trading...")
        
        self.is_running = False
        self.portfolio.print_summary()
        self.portfolio.save_state()
    
    def stop(self):
        """Stop paper trading"""
        self.is_running = False


def run_paper_trading_demo():
    """Run a demo paper trading session"""
    trader = PaperTrader(initial_capital=500000)
    
    # Add strategies
    trader.add_strategy('short_straddle', symbol='NIFTY', lots=1, 
                       config={'entry_time': datetime.now(IST).strftime('%H:%M')})
    trader.add_strategy('short_strangle', symbol='BANKNIFTY', lots=1,
                       config={'entry_time': datetime.now(IST).strftime('%H:%M')})
    
    # Run 5-minute simulation
    trader.run_simulation(duration_minutes=5)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Paper Trading')
    parser.add_argument('--demo', action='store_true', help='Run demo simulation')
    parser.add_argument('--live', action='store_true', help='Start live paper trading')
    parser.add_argument('--capital', type=float, default=500000, help='Initial capital')
    
    args = parser.parse_args()
    
    if args.demo:
        run_paper_trading_demo()
    elif args.live:
        trader = PaperTrader(initial_capital=args.capital)
        trader.add_strategy('short_straddle', symbol='NIFTY', lots=1)
        trader.start_live()
    else:
        print("Paper Trading Module")
        print("Usage:")
        print("  --demo   Run demo simulation")
        print("  --live   Start live paper trading")
