"""
Expiry Day Option Buying Strategy
===================================
High-risk, high-reward trades on expiry day

Strategies:
1. Hero-Zero Trade - ATM options with breakout potential
2. Directional Momentum - Buy when strong move detected
3. Scalping - Quick in-out trades

Risk Warning: These trades can go to ZERO. Only use capital you can lose.
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from real_option_prices import get_real_option_price
    PRICES_OK = True
except ImportError:
    PRICES_OK = False

try:
    from trend_filter import get_trend_analysis
    TREND_OK = True
except ImportError:
    TREND_OK = False

try:
    from notifications import send_telegram_message
    TELEGRAM_OK = True
except ImportError:
    TELEGRAM_OK = False


class TradeType(Enum):
    HERO_ZERO = "Hero-Zero"
    MOMENTUM = "Momentum"
    SCALP = "Scalp"


@dataclass
class ExpiryTrade:
    """Expiry day trade setup"""
    symbol: str
    trade_type: TradeType
    direction: str  # BULLISH or BEARISH
    strike: int
    option_type: str  # CE or PE
    entry_price: float
    target_price: float
    stop_loss: float
    lot_size: int
    reason: str
    confidence: int


class ExpiryDayTrader:
    """Generate expiry day option buying signals"""
    
    # Configuration
    LOT_SIZES = {
        'NIFTY': 75,
        'BANKNIFTY': 30,
        'FINNIFTY': 40,
    }
    
    STRIKE_GAP = {
        'NIFTY': 50,
        'BANKNIFTY': 100,
        'FINNIFTY': 50,
    }
    
    # Expiry days
    EXPIRY_MAP = {
        0: 'MIDCPNIFTY',   # Monday
        1: 'FINNIFTY',     # Tuesday
        2: 'BANKNIFTY',    # Wednesday
        3: 'NIFTY',        # Thursday
    }
    
    def __init__(self):
        self.api = None
    
    def is_expiry_day(self, symbol: str = None) -> Tuple[bool, str]:
        """Check if today is expiry day for given symbol"""
        today = datetime.now(IST)
        weekday = today.weekday()
        
        expiry_symbol = self.EXPIRY_MAP.get(weekday)
        
        if symbol:
            is_expiry = (expiry_symbol == symbol)
            return is_expiry, expiry_symbol or ""
        
        return expiry_symbol is not None, expiry_symbol or ""
    
    def get_spot_price(self, symbol: str) -> Optional[float]:
        """Get current spot price"""
        try:
            from live_data_provider import get_live_spot
            return get_live_spot(symbol)
        except:
            return None
    
    def get_atm_strike(self, symbol: str, spot: float) -> int:
        """Get ATM strike"""
        gap = self.STRIKE_GAP.get(symbol, 50)
        return int(round(spot / gap) * gap)
    
    def generate_hero_zero(self, symbol: str) -> Optional[ExpiryTrade]:
        """
        Generate Hero-Zero trade setup
        
        Logic:
        - Buy ATM option when market is consolidating
        - Target: 100% (2x entry)
        - Stop Loss: 50% of premium
        """
        is_expiry, expiry_symbol = self.is_expiry_day(symbol)
        if not is_expiry:
            return None
        
        spot = self.get_spot_price(symbol)
        if not spot:
            return None
        
        # Get market direction
        direction = "NEUTRAL"
        if TREND_OK:
            trend = get_trend_analysis(symbol)
            change = trend.get('change_percent', 0)
            if change > 0.3:
                direction = "BULLISH"
            elif change < -0.3:
                direction = "BEARISH"
        
        # Decide option type based on direction
        if direction == "BULLISH":
            option_type = "CE"
            strike = self.get_atm_strike(symbol, spot)
        elif direction == "BEARISH":
            option_type = "PE"
            strike = self.get_atm_strike(symbol, spot)
        else:
            # Neutral - skip or pick based on time
            now = datetime.now(IST)
            if now.hour < 12:
                option_type = "CE"  # Morning bullish bias
            else:
                option_type = "PE"  # Afternoon bearish bias
            strike = self.get_atm_strike(symbol, spot)
        
        # Get option price
        if PRICES_OK:
            entry = get_real_option_price(symbol, strike, option_type)
        else:
            entry = 50  # Dummy
        
        if not entry or entry < 5:
            return None
        
        lot_size = self.LOT_SIZES.get(symbol, 50)
        
        return ExpiryTrade(
            symbol=symbol,
            trade_type=TradeType.HERO_ZERO,
            direction=direction,
            strike=strike,
            option_type=option_type,
            entry_price=entry,
            target_price=entry * 2,      # 100% target
            stop_loss=entry * 0.5,       # 50% SL
            lot_size=lot_size,
            reason=f"Expiry day ATM {option_type} - potential breakout",
            confidence=60,
        )
    
    def generate_momentum_trade(self, symbol: str) -> Optional[ExpiryTrade]:
        """
        Generate momentum trade on strong move
        
        Logic:
        - Buy when market moves > 0.5% in direction
        - Target: 50%
        - Stop Loss: 30%
        """
        spot = self.get_spot_price(symbol)
        if not spot:
            return None
        
        if not TREND_OK:
            return None
        
        trend = get_trend_analysis(symbol)
        change = trend.get('change_percent', 0)
        
        # Need strong momentum
        if abs(change) < 0.5:
            return None
        
        if change > 0:
            direction = "BULLISH"
            option_type = "CE"
            # OTM by 1 strike for momentum
            strike = self.get_atm_strike(symbol, spot) + self.STRIKE_GAP.get(symbol, 50)
        else:
            direction = "BEARISH"
            option_type = "PE"
            strike = self.get_atm_strike(symbol, spot) - self.STRIKE_GAP.get(symbol, 50)
        
        if PRICES_OK:
            entry = get_real_option_price(symbol, strike, option_type)
        else:
            entry = 30
        
        if not entry or entry < 3:
            return None
        
        lot_size = self.LOT_SIZES.get(symbol, 50)
        
        return ExpiryTrade(
            symbol=symbol,
            trade_type=TradeType.MOMENTUM,
            direction=direction,
            strike=strike,
            option_type=option_type,
            entry_price=entry,
            target_price=entry * 1.5,    # 50% target
            stop_loss=entry * 0.7,       # 30% SL
            lot_size=lot_size,
            reason=f"Strong momentum {change:+.2f}% - riding the move",
            confidence=70,
        )
    
    def generate_scalp_trade(self, symbol: str) -> Optional[ExpiryTrade]:
        """
        Generate quick scalp trade
        
        Logic:
        - ATM option for quick 20-30% profit
        - Very tight SL (20%)
        - Quick exit
        """
        spot = self.get_spot_price(symbol)
        if not spot:
            return None
        
        atm = self.get_atm_strike(symbol, spot)
        
        # Default to CE for scalp
        option_type = "CE"
        
        if PRICES_OK:
            entry = get_real_option_price(symbol, atm, option_type)
        else:
            entry = 40
        
        if not entry or entry < 10:
            return None
        
        lot_size = self.LOT_SIZES.get(symbol, 50)
        
        return ExpiryTrade(
            symbol=symbol,
            trade_type=TradeType.SCALP,
            direction="NEUTRAL",
            strike=atm,
            option_type=option_type,
            entry_price=entry,
            target_price=entry * 1.25,   # 25% target
            stop_loss=entry * 0.8,       # 20% SL
            lot_size=lot_size,
            reason=f"Quick scalp on ATM {option_type}",
            confidence=55,
        )
    
    def format_alert(self, trade: ExpiryTrade) -> str:
        """Format trade alert for Telegram"""
        
        emoji = "🚀" if trade.trade_type == TradeType.HERO_ZERO else "⚡"
        dir_emoji = "📈" if trade.direction == "BULLISH" else "📉" if trade.direction == "BEARISH" else "↔️"
        
        profit_pct = ((trade.target_price - trade.entry_price) / trade.entry_price) * 100
        loss_pct = ((trade.entry_price - trade.stop_loss) / trade.entry_price) * 100
        
        max_profit = (trade.target_price - trade.entry_price) * trade.lot_size
        max_loss = (trade.entry_price - trade.stop_loss) * trade.lot_size
        
        msg = f"""
╔══════════════════════════════╗
   {emoji} <b>EXPIRY DAY ALERT</b> {emoji}
╚══════════════════════════════╝

📈 <b>{trade.symbol}</b> │ {trade.trade_type.value}
⏰ {datetime.now(IST).strftime('%H:%M')} │ {dir_emoji} {trade.direction}

┌──────── TRADE ────────┐

  <b>BUY</b> {trade.option_type} {trade.strike}
  
  💰 Entry:  <code>₹{trade.entry_price:.2f}</code>
  🎯 Target: <code>₹{trade.target_price:.2f}</code> (+{profit_pct:.0f}%)
  🛑 SL:     <code>₹{trade.stop_loss:.2f}</code> (-{loss_pct:.0f}%)

└────────────────────────┘

┌──────── P&L ──────────┐

  💚 Max Profit: <code>₹{max_profit:,.0f}</code>
  ❌ Max Loss:   <code>₹{max_loss:,.0f}</code>

└────────────────────────┘

📋 {trade.reason}

⚠️ <b>HIGH RISK TRADE - Can go to ZERO!</b>
<i>Only trade what you can afford to lose</i>
"""
        return msg
    
    def scan_and_alert(self, symbol: str = None) -> bool:
        """Scan and send expiry day alerts"""
        
        is_expiry, expiry_symbol = self.is_expiry_day(symbol)
        
        if not is_expiry:
            print(f"❌ Today is not expiry day for {symbol or 'any symbol'}")
            return False
        
        target_symbol = symbol or expiry_symbol
        print(f"🎯 Expiry day for {target_symbol}! Scanning...")
        
        # Try Hero-Zero first
        trade = self.generate_hero_zero(target_symbol)
        
        # If no hero-zero, try momentum
        if not trade:
            trade = self.generate_momentum_trade(target_symbol)
        
        if not trade:
            print(f"❌ No trade setup found for {target_symbol}")
            return False
        
        # Send alert
        msg = self.format_alert(trade)
        
        if TELEGRAM_OK:
            send_telegram_message(msg)
            print(f"✅ Sent {trade.trade_type.value} alert for {target_symbol}")
        else:
            print(msg)
        
        return True


# Singleton
_trader = None


def get_trader() -> ExpiryDayTrader:
    global _trader
    if _trader is None:
        _trader = ExpiryDayTrader()
    return _trader


def scan_expiry_trades(symbol: str = None) -> bool:
    """Scan for expiry day trades"""
    return get_trader().scan_and_alert(symbol)


def is_expiry_day(symbol: str = None) -> Tuple[bool, str]:
    """Check if today is expiry"""
    return get_trader().is_expiry_day(symbol)


if __name__ == "__main__":
    print("="*50)
    print("       EXPIRY DAY TRADER")
    print("="*50)
    
    is_exp, sym = is_expiry_day()
    print(f"\nToday's Expiry: {sym if is_exp else 'None'}")
    
    if is_exp:
        print(f"\nScanning for {sym} trades...")
        scan_expiry_trades(sym)
    else:
        print("\nNo expiry today. Checking NIFTY anyway for demo...")
        trader = get_trader()
        trade = trader.generate_hero_zero('NIFTY')
        if trade:
            print(trader.format_alert(trade))
