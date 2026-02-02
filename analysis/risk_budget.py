"""
Risk Budgeting Module
======================
Ensures proper position sizing and capital protection

Rules:
- Max 2% capital per trade
- Max 5% capital per day
- Stop trading when daily loss > 3%
"""
import sys
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
from typing import Dict, Optional, Tuple
import json

sys.path.insert(0, str(Path(__file__).parent))

IST = timezone(timedelta(hours=5, minutes=30))


class RiskBudget:
    """Manage risk and position sizing"""
    
    def __init__(self, 
                 total_capital: float = 100000,       # ₹1 Lakh
                 max_risk_per_trade: float = 0.02,    # 2%
                 max_risk_per_day: float = 0.05,      # 5%
                 daily_loss_limit: float = 0.03):     # 3%
        
        self.total_capital = total_capital
        self.max_risk_per_trade = max_risk_per_trade
        self.max_risk_per_day = max_risk_per_day
        self.daily_loss_limit = daily_loss_limit
        
        # Track daily activity
        self.daily_file = Path(__file__).parent / "daily_risk.json"
        self._load_daily_data()
    
    def _load_daily_data(self):
        """Load today's risk data"""
        self.today = date.today().isoformat()
        
        if self.daily_file.exists():
            try:
                with open(self.daily_file, 'r') as f:
                    data = json.load(f)
                    if data.get('date') == self.today:
                        self.daily_pnl = data.get('pnl', 0)
                        self.daily_trades = data.get('trades', 0)
                        self.capital_used = data.get('capital_used', 0)
                        return
            except:
                pass
        
        # New day - reset
        self.daily_pnl = 0
        self.daily_trades = 0
        self.capital_used = 0
        self._save_daily_data()
    
    def _save_daily_data(self):
        """Save daily risk data"""
        data = {
            'date': self.today,
            'pnl': self.daily_pnl,
            'trades': self.daily_trades,
            'capital_used': self.capital_used,
        }
        with open(self.daily_file, 'w') as f:
            json.dump(data, f, indent=2)
    
    def can_take_trade(self) -> Tuple[bool, str]:
        """Check if we can take a new trade"""
        
        # Check daily loss limit
        if self.daily_pnl <= -(self.total_capital * self.daily_loss_limit):
            return False, f"❌ Daily loss limit hit (₹{self.daily_pnl:,.0f}). No more trades today."
        
        # Check daily capital usage
        daily_limit = self.total_capital * self.max_risk_per_day
        if self.capital_used >= daily_limit:
            return False, f"❌ Daily capital limit reached (₹{self.capital_used:,.0f}). No more trades."
        
        return True, "✅ Within risk limits"
    
    def calculate_position_size(self, max_loss_per_lot: float, lot_size: int) -> int:
        """
        Calculate optimal position size based on risk
        
        Args:
            max_loss_per_lot: Maximum loss per lot (in ₹)
            lot_size: Standard lot size
        
        Returns:
            Number of lots to trade
        """
        # Max risk per trade
        max_risk = self.total_capital * self.max_risk_per_trade
        
        # Remaining daily limit
        daily_limit = self.total_capital * self.max_risk_per_day
        remaining = daily_limit - self.capital_used
        
        # Use the smaller of the two
        available_risk = min(max_risk, remaining)
        
        if max_loss_per_lot <= 0:
            return 1
        
        # Calculate lots
        lots = int(available_risk / max_loss_per_lot)
        
        # Minimum 1 lot if allowed
        return max(1, lots)
    
    def get_suggested_lot_size(self, symbol: str, spread_width: int = 100) -> int:
        """
        Get suggested lot size based on risk budget
        
        Args:
            symbol: NIFTY, BANKNIFTY
            spread_width: Width of spread (100 for NIFTY, 200 for BANKNIFTY)
        
        Returns:
            Suggested number of lots
        """
        # Standard lot sizes
        lot_sizes = {
            'NIFTY': 75,
            'BANKNIFTY': 30,
        }
        
        lot = lot_sizes.get(symbol, 75)
        
        # Max loss = spread width * lot size
        max_loss_per_lot = spread_width * lot
        
        return self.calculate_position_size(max_loss_per_lot, lot)
    
    def record_trade(self, capital_at_risk: float):
        """Record a new trade"""
        self.daily_trades += 1
        self.capital_used += capital_at_risk
        self._save_daily_data()
    
    def record_pnl(self, pnl: float):
        """Record P&L from a trade"""
        self.daily_pnl += pnl
        self._save_daily_data()
    
    def get_status(self) -> Dict:
        """Get current risk status"""
        
        can_trade, msg = self.can_take_trade()
        
        daily_limit = self.total_capital * self.max_risk_per_day
        remaining = daily_limit - self.capital_used
        
        return {
            'total_capital': self.total_capital,
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'capital_used': self.capital_used,
            'capital_remaining': remaining,
            'can_trade': can_trade,
            'message': msg,
            'max_risk_per_trade': self.total_capital * self.max_risk_per_trade,
        }
    
    def reset_daily(self):
        """Reset daily counters"""
        self.daily_pnl = 0
        self.daily_trades = 0
        self.capital_used = 0
        self.today = date.today().isoformat()
        self._save_daily_data()


# Singleton
_budget = None


def get_risk_budget() -> RiskBudget:
    global _budget
    if _budget is None:
        _budget = RiskBudget()
    return _budget


def can_take_trade() -> Tuple[bool, str]:
    """Check if we can take a trade"""
    return get_risk_budget().can_take_trade()


def get_suggested_lots(symbol: str, spread_width: int = 100) -> int:
    """Get suggested lot size"""
    return get_risk_budget().get_suggested_lot_size(symbol, spread_width)


def get_risk_status() -> Dict:
    """Get risk status"""
    return get_risk_budget().get_status()


if __name__ == "__main__":
    print("="*50)
    print("       RISK BUDGETING")
    print("="*50)
    
    status = get_risk_status()
    
    print(f"\nTotal Capital: ₹{status['total_capital']:,.0f}")
    print(f"Daily P&L: ₹{status['daily_pnl']:+,.0f}")
    print(f"Daily Trades: {status['daily_trades']}")
    print(f"Capital Used: ₹{status['capital_used']:,.0f}")
    print(f"Capital Remaining: ₹{status['capital_remaining']:,.0f}")
    print(f"Max Risk/Trade: ₹{status['max_risk_per_trade']:,.0f}")
    print(f"Can Trade: {status['can_trade']}")
    print(f"Message: {status['message']}")
    
    print("\nSuggested Lots:")
    for symbol in ['NIFTY', 'BANKNIFTY']:
        lots = get_suggested_lots(symbol)
        print(f"  {symbol}: {lots} lot(s)")
