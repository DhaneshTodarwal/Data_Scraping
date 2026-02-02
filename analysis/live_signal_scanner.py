"""
Live Market Signal Scanner
===========================
Scans live market for trading signals and sends detailed alerts
Runs during market hours - DOES NOT place orders (Safe Mode)
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta, time
import time as time_module
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

# Import notifications
try:
    from notifications import send_telegram_message, send_desktop_notification
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False
    print("⚠ notifications module not found")

# Import AngelOne API for live data
try:
    from angelone_api import AngelOneAPI
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False

IST = timezone(timedelta(hours=5, minutes=30))

# Lot sizes
LOT_SIZES = {
    'NIFTY': 75,
    'BANKNIFTY': 30,
    'FINNIFTY': 65,
    'MIDCAPNIFTY': 100,
    'SENSEX': 20,
}


class LiveSignalScanner:
    """
    Scans live market for trading signals
    Sends detailed Telegram alerts with exact trade instructions
    """
    
    def __init__(self):
        self.market_open = time(9, 15)
        self.market_close = time(15, 30)
        self.signals_today = []
        self.is_running = False
        
        # Strategy configurations (from optimization)
        self.strategies = {
            'short_straddle': {
                'name': 'Short Straddle',
                'entry_times': ['09:45', '10:15'],
                'sl_pct': 30,
                'target_pct': 50,
                'symbols': ['NIFTY', 'BANKNIFTY'],
            },
            'short_strangle': {
                'name': 'Short Strangle',
                'entry_times': ['09:45'],
                'otm_distance': 2,
                'sl_pct': 40,
                'target_pct': 40,
                'symbols': ['NIFTY', 'BANKNIFTY'],
            },
        }
    
    def is_market_open(self) -> bool:
        """Check if market is open"""
        now = datetime.now(IST)
        if now.weekday() >= 5:
            return False
        return self.market_open <= now.time() <= self.market_close
    
    def get_strike_gap(self, symbol: str, spot: float) -> int:
        """Get strike gap for symbol"""
        if symbol == 'SENSEX':
            return 100
        elif spot < 25000:
            return 50
        else:
            return 100
    
    def get_atm_strike(self, spot: float, gap: int) -> int:
        """Get ATM strike"""
        return int(round(spot / gap) * gap)
    
    def get_live_spot(self, symbol: str) -> Optional[float]:
        """Get live spot price"""
        if not API_AVAILABLE:
            # Simulated for testing
            import random
            bases = {'NIFTY': 24500, 'BANKNIFTY': 52000, 'FINNIFTY': 23500}
            return bases.get(symbol, 24500) + random.uniform(-50, 50)
        
        try:
            api = AngelOneAPI()
            return api.get_ltp(symbol)
        except Exception as e:
            print(f"Error getting spot: {e}")
            return None
    
    def get_live_option_price(self, symbol: str, strike: int, 
                              option_type: str) -> Optional[float]:
        """Get live option premium"""
        if not API_AVAILABLE:
            import random
            spot = {'NIFTY': 24500, 'BANKNIFTY': 52000}.get(symbol, 24500)
            if option_type == 'CE':
                intrinsic = max(0, spot - strike)
            else:
                intrinsic = max(0, strike - spot)
            return intrinsic + random.uniform(50, 150)
        
        try:
            api = AngelOneAPI()
            return api.get_option_ltp(symbol, strike, option_type)
        except Exception:
            return None
    
    def format_straddle_alert(self, symbol: str, spot: float, atm: int,
                              ce_price: float, pe_price: float,
                              sl_pct: float, target_pct: float) -> str:
        """
        Format detailed Short Straddle alert
        """
        total_premium = ce_price + pe_price
        lot_size = LOT_SIZES.get(symbol, 50)
        
        # Calculate SL and Target
        sl_premium = total_premium * (1 + sl_pct / 100)
        target_premium = total_premium * (1 - target_pct / 100)
        
        # Calculate risk/reward
        max_profit = total_premium * lot_size
        max_loss_sl = (sl_premium - total_premium) * lot_size
        
        # Breakeven points
        upper_be = atm + total_premium
        lower_be = atm - total_premium
        
        msg = f"""
🚨 <b>SHORT STRADDLE SIGNAL</b>

📈 <b>Symbol:</b> {symbol}
💰 <b>Spot:</b> ₹{spot:,.2f}
⏰ <b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🔴 SELL INSTRUCTIONS:</b>

<b>1. SELL {symbol} CE {atm}</b>
   • Premium: ₹{ce_price:.2f}
   • Qty: {lot_size} (1 lot)
   
<b>2. SELL {symbol} PE {atm}</b>
   • Premium: ₹{pe_price:.2f}
   • Qty: {lot_size} (1 lot)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 TRADE DETAILS:</b>
• Total Premium: ₹{total_premium:.2f}
• Max Profit: ₹{max_profit:,.0f}
• Risk (SL): ₹{max_loss_sl:,.0f}

<b>🎯 EXIT RULES:</b>
• <b>TARGET:</b> Exit when total premium = ₹{target_premium:.2f}
  (Profit: ₹{max_profit * target_pct / 100:,.0f})
  
• <b>STOP LOSS:</b> Exit when total premium = ₹{sl_premium:.2f}
  (Loss: ₹{max_loss_sl:,.0f})
  
• <b>TIME EXIT:</b> Close by 3:20 PM

<b>📐 BREAKEVEN:</b>
• Upper: {upper_be:.0f}
• Lower: {lower_be:.0f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ <i>This is an ALERT only. No auto-trading.</i>
<i>Verify prices before trading.</i>
"""
        return msg
    
    def format_strangle_alert(self, symbol: str, spot: float, atm: int,
                              ce_strike: int, pe_strike: int,
                              ce_price: float, pe_price: float,
                              sl_pct: float, target_pct: float) -> str:
        """
        Format detailed Short Strangle alert
        """
        total_premium = ce_price + pe_price
        lot_size = LOT_SIZES.get(symbol, 50)
        
        sl_premium = total_premium * (1 + sl_pct / 100)
        target_premium = total_premium * (1 - target_pct / 100)
        
        max_profit = total_premium * lot_size
        max_loss_sl = (sl_premium - total_premium) * lot_size
        
        upper_be = ce_strike + total_premium
        lower_be = pe_strike - total_premium
        
        msg = f"""
🚨 <b>SHORT STRANGLE SIGNAL</b>

📈 <b>Symbol:</b> {symbol}
💰 <b>Spot:</b> ₹{spot:,.2f}
⏰ <b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🔴 SELL INSTRUCTIONS:</b>

<b>1. SELL {symbol} CE {ce_strike}</b>
   • Premium: ₹{ce_price:.2f}
   • Qty: {lot_size} (1 lot)
   • OTM by: {ce_strike - atm} pts
   
<b>2. SELL {symbol} PE {pe_strike}</b>
   • Premium: ₹{pe_price:.2f}
   • Qty: {lot_size} (1 lot)
   • OTM by: {atm - pe_strike} pts

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 TRADE DETAILS:</b>
• Total Premium: ₹{total_premium:.2f}
• Max Profit: ₹{max_profit:,.0f}
• Risk (SL): ₹{max_loss_sl:,.0f}

<b>🎯 EXIT RULES:</b>
• <b>TARGET:</b> Exit when total premium = ₹{target_premium:.2f}
  (Profit: ₹{max_profit * target_pct / 100:,.0f})
  
• <b>STOP LOSS:</b> Exit when total premium = ₹{sl_premium:.2f}
  (Loss: ₹{max_loss_sl:,.0f})
  
• <b>TIME EXIT:</b> Close by 3:20 PM

<b>📐 BREAKEVEN RANGE:</b>
• Safe if spot stays: {pe_strike:.0f} to {ce_strike:.0f}
• Breakeven: {lower_be:.0f} - {upper_be:.0f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ <i>This is an ALERT only. No auto-trading.</i>
<i>Verify prices before trading.</i>
"""
        return msg
    
    def check_straddle_signal(self, symbol: str) -> Optional[str]:
        """Check for Short Straddle signal"""
        config = self.strategies['short_straddle']
        
        if symbol not in config['symbols']:
            return None
        
        current_time = datetime.now(IST).strftime('%H:%M')
        
        # Only at entry times
        if current_time not in config['entry_times']:
            return None
        
        # Check if already signaled today
        signal_key = f"{symbol}_straddle_{current_time}"
        if signal_key in self.signals_today:
            return None
        
        # Get live data
        spot = self.get_live_spot(symbol)
        if not spot:
            return None
        
        gap = self.get_strike_gap(symbol, spot)
        atm = self.get_atm_strike(spot, gap)
        
        ce_price = self.get_live_option_price(symbol, atm, 'CE')
        pe_price = self.get_live_option_price(symbol, atm, 'PE')
        
        if not ce_price or not pe_price:
            return None
        
        # Mark as signaled
        self.signals_today.append(signal_key)
        
        # Generate alert
        return self.format_straddle_alert(
            symbol, spot, atm, ce_price, pe_price,
            config['sl_pct'], config['target_pct']
        )
    
    def check_strangle_signal(self, symbol: str) -> Optional[str]:
        """Check for Short Strangle signal"""
        config = self.strategies['short_strangle']
        
        if symbol not in config['symbols']:
            return None
        
        current_time = datetime.now(IST).strftime('%H:%M')
        
        if current_time not in config['entry_times']:
            return None
        
        signal_key = f"{symbol}_strangle_{current_time}"
        if signal_key in self.signals_today:
            return None
        
        spot = self.get_live_spot(symbol)
        if not spot:
            return None
        
        gap = self.get_strike_gap(symbol, spot)
        atm = self.get_atm_strike(spot, gap)
        
        otm = config['otm_distance']
        ce_strike = atm + gap * otm
        pe_strike = atm - gap * otm
        
        ce_price = self.get_live_option_price(symbol, ce_strike, 'CE')
        pe_price = self.get_live_option_price(symbol, pe_strike, 'PE')
        
        if not ce_price or not pe_price:
            return None
        
        self.signals_today.append(signal_key)
        
        return self.format_strangle_alert(
            symbol, spot, atm, ce_strike, pe_strike,
            ce_price, pe_price, config['sl_pct'], config['target_pct']
        )
    
    def send_alert(self, message: str) -> bool:
        """Send alert via Telegram"""
        if not NOTIFICATIONS_AVAILABLE:
            print(message)
            return False
        
        return send_telegram_message(message)
    
    def send_market_open_alert(self):
        """Send market open summary"""
        msg = f"""
🔔 <b>MARKET OPEN</b>
📅 {datetime.now(IST).strftime('%Y-%m-%d')}

<b>Active Strategies:</b>
• Short Straddle: 09:45, 10:15
• Short Strangle: 09:45

<b>Symbols:</b> NIFTY, BANKNIFTY

<b>Current Prices:</b>
"""
        for symbol in ['NIFTY', 'BANKNIFTY']:
            spot = self.get_live_spot(symbol)
            if spot:
                msg += f"• {symbol}: ₹{spot:,.2f}\n"
        
        msg += "\n📱 <i>Alerts will be sent when signals trigger.</i>"
        
        self.send_alert(msg)
    
    def run(self, check_interval: int = 30):
        """
        Run live scanner
        Checks for signals every 'check_interval' seconds during market hours
        """
        print("\n" + "="*60)
        print("       LIVE SIGNAL SCANNER (ALERT MODE)")
        print("="*60)
        print("⚠️  NO real orders will be placed")
        print("📱 Signals will be sent to Telegram")
        print("Press Ctrl+C to stop")
        print("="*60)
        
        self.is_running = True
        market_opened_today = False
        
        try:
            while self.is_running:
                now = datetime.now(IST)
                
                # Check market hours
                if not self.is_market_open():
                    if now.time() < self.market_open:
                        wait_mins = (datetime.now(IST).replace(
                            hour=9, minute=15, second=0) - now).seconds // 60
                        print(f"\r⏳ Market opens in {wait_mins} min...", end="")
                    else:
                        print(f"\r⏸ Market closed. ({now.strftime('%H:%M')})", end="")
                        market_opened_today = False
                        self.signals_today = []  # Reset for next day
                    time_module.sleep(60)
                    continue
                
                # Send market open alert once
                if not market_opened_today:
                    print("\n🔔 Market opened!")
                    self.send_market_open_alert()
                    market_opened_today = True
                
                # Check for signals
                print(f"\r🔍 Scanning... ({now.strftime('%H:%M:%S')}) | "
                      f"Signals today: {len(self.signals_today)}", end="")
                
                for symbol in ['NIFTY', 'BANKNIFTY']:
                    # Check straddle
                    alert = self.check_straddle_signal(symbol)
                    if alert:
                        print(f"\n🚨 SIGNAL: Short Straddle on {symbol}")
                        self.send_alert(alert)
                    
                    # Check strangle
                    alert = self.check_strangle_signal(symbol)
                    if alert:
                        print(f"\n🚨 SIGNAL: Short Strangle on {symbol}")
                        self.send_alert(alert)
                
                time_module.sleep(check_interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Scanner stopped")
        
        self.is_running = False
    
    def run_once(self):
        """Run a single scan (for testing or cron)"""
        print(f"🔍 Scanning at {datetime.now(IST).strftime('%H:%M:%S')}...")
        
        for symbol in ['NIFTY', 'BANKNIFTY']:
            alert = self.check_straddle_signal(symbol)
            if alert:
                print(f"🚨 SIGNAL: Short Straddle on {symbol}")
                self.send_alert(alert)
            
            alert = self.check_strangle_signal(symbol)
            if alert:
                print(f"🚨 SIGNAL: Short Strangle on {symbol}")
                self.send_alert(alert)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Live Signal Scanner')
    parser.add_argument('--run', action='store_true', help='Start live scanning')
    parser.add_argument('--once', action='store_true', help='Run single scan')
    parser.add_argument('--test', action='store_true', help='Send test alert')
    parser.add_argument('--interval', type=int, default=30, help='Check interval (seconds)')
    
    args = parser.parse_args()
    
    scanner = LiveSignalScanner()
    
    if args.test:
        # Send a test alert
        msg = scanner.format_straddle_alert(
            'NIFTY', 24520.50, 24500,
            125.50, 118.25, 30, 50
        )
        scanner.send_alert(msg)
        print("✅ Test alert sent!")
    elif args.once:
        scanner.run_once()
    elif args.run:
        scanner.run(check_interval=args.interval)
    else:
        print("Live Signal Scanner")
        print("Usage:")
        print("  --run    Start live scanning")
        print("  --once   Run single scan (for cron)")
        print("  --test   Send test alert")


if __name__ == "__main__":
    main()
