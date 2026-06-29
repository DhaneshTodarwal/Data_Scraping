"""
Real-Time Continuous Scanner
==============================
Scans market CONTINUOUSLY during trading hours
No fixed times - alerts when conditions are met!

Features:
- Runs 9:20 AM to 3:25 PM
- Scans every 1-2 minutes
- Real-time condition monitoring
- Immediate alerts when setup forms
- No missed opportunities
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone, timedelta, time
import time as time_module
from pathlib import Path
import sys
import signal
import json

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# Import modules
from advanced_analysis import get_advanced_analysis, AdvancedMarketAnalyzer
from smart_analyzer import SmartMarketAnalyzer, StrategyRecommendation
from pro_trading_alerts import ProTradeGenerator, ProAlertFormatter, TradeSetup
from exit_alerts import ProExitAlerts, ActivePosition, PositionTracker

try:
    from notifications import send_telegram_message, send_desktop_notification
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False
    print("⚠ Notifications not available")

# Expiry day trading
try:
    from expiry_day_trader import get_trader as get_expiry_trader, is_expiry_day
    EXPIRY_TRADER_AVAILABLE = True
except ImportError:
    EXPIRY_TRADER_AVAILABLE = False

# Paper trading for EOD tracking
try:
    from paper_trading_platform import get_platform as get_paper_platform
    PAPER_TRADING_AVAILABLE = True
except ImportError:
    PAPER_TRADING_AVAILABLE = False
    print("⚠ Paper trading not available - trades won't be tracked")

IST = timezone(timedelta(hours=5, minutes=30))


class RealTimeScanner:
    """
    Continuous real-time market scanner
    Scans every minute and alerts immediately when conditions are met
    """
    
    def __init__(self, 
                 scan_interval: int = 60,  # seconds
                 min_confidence: int = 85,
                 min_probability: int = 55):
        
        # Timing
        self.scan_interval = scan_interval
        self.market_open = time(9, 20)  # Start scanning 5 min after open
        self.market_close = time(15, 25)  # Stop 5 min before close
        
        # Thresholds
        self.min_confidence = min_confidence
        self.min_probability = min_probability
        
        # Generators
        self.trade_generator = ProTradeGenerator()
        self.alert_formatter = ProAlertFormatter()
        self.exit_alerts = ProExitAlerts()
        self.position_tracker = PositionTracker()
        
        # State tracking
        self.is_running = False
        self.signals_today: Set[str] = set()  # Avoid duplicate signals
        self.last_conditions: Dict[str, Dict] = {}  # Track condition changes
        self.scan_count = 0
        
        # Cooldown to prevent spam (min minutes between signals for same strategy)
        self.signal_cooldown_minutes = 30
        self.signal_timestamps: Dict[str, datetime] = {}
        
        # Symbols to scan
        self.symbols = ['NIFTY', 'BANKNIFTY']
        
        # Strategies that can be signaled
        self.strategies = [
            StrategyRecommendation.SHORT_STRADDLE,
            StrategyRecommendation.SHORT_STRANGLE,
            StrategyRecommendation.IRON_CONDOR,
            StrategyRecommendation.IRON_BUTTERFLY,
            StrategyRecommendation.BULL_PUT_SPREAD,
            StrategyRecommendation.BEAR_CALL_SPREAD,
        ]
        
        # Lot sizes for paper trading
        self.lot_sizes = {
            'NIFTY': 75,
            'BANKNIFTY': 30,
            'FINNIFTY': 65,
            'MIDCAPNIFTY': 100,
            'SENSEX': 20,
        }
    
    def is_market_hours(self) -> bool:
        """Check if within market hours"""
        now = datetime.now(IST)
        
        # Weekend check
        if now.weekday() >= 5:
            return False
        
        return self.market_open <= now.time() <= self.market_close
    
    def get_cooldown_key(self, symbol: str, strategy: str) -> str:
        """Get cooldown key for signal"""
        return f"{symbol}_{strategy}"
    
    def is_on_cooldown(self, symbol: str, strategy: str) -> bool:
        """Check if signal is on cooldown"""
        key = self.get_cooldown_key(symbol, strategy)
        
        if key not in self.signal_timestamps:
            return False
        
        last_signal = self.signal_timestamps[key]
        elapsed = (datetime.now(IST) - last_signal).total_seconds() / 60
        
        return elapsed < self.signal_cooldown_minutes
    
    def record_signal(self, symbol: str, strategy: str):
        """Record signal timestamp for cooldown"""
        key = self.get_cooldown_key(symbol, strategy)
        self.signal_timestamps[key] = datetime.now(IST)
    
    def has_conditions_changed(self, symbol: str, analysis) -> bool:
        """Check if conditions have meaningfully changed since last scan"""
        key = symbol
        
        current = {
            'regime': analysis.total_score,
            'oi_bias': analysis.oi.oi_bias,
            'iv_level': round(analysis.greeks.iv_percentile / 10) * 10,
        }
        
        if key not in self.last_conditions:
            self.last_conditions[key] = current
            return True
        
        last = self.last_conditions[key]
        
        # Check for significant changes
        score_change = abs(current['regime'] - last['regime']) >= 10
        bias_change = current['oi_bias'] != last['oi_bias']
        iv_change = abs(current['iv_level'] - last['iv_level']) >= 10
        
        self.last_conditions[key] = current
        
        return score_change or bias_change or iv_change
    
    def send_alert(self, message: str) -> bool:
        """Send alert to Telegram"""
        if not NOTIFICATIONS_AVAILABLE:
            print(message)
            return False
        return send_telegram_message(message)
    
    def scan_symbol(self, symbol: str) -> Optional[TradeSetup]:
        """Scan a single symbol for trading opportunity"""
        
        # Get advanced analysis
        analysis = get_advanced_analysis(symbol)
        
        # Check if conditions changed (avoid repeat alerts for same condition)
        if not self.has_conditions_changed(symbol, analysis):
            return None
        
        # Check minimum thresholds
        if analysis.total_score < self.min_confidence:
            return None
        
        if not analysis.should_trade:
            return None
        
        # Generate trade setup
        setup = self.trade_generator.generate_intraday_setup(symbol)
        
        if not setup:
            return None
            
        # Skip Iron Condor alerts per user request
        if setup.strategy == StrategyRecommendation.IRON_CONDOR or setup.strategy == "Iron Condor":
            return None
        
        # Check probability threshold
        if setup.win_probability < self.min_probability:
            return None
        
        # Check if on cooldown
        if self.is_on_cooldown(symbol, setup.strategy):
            return None
        
        # Check recommendation
        if "AVOID" in setup.recommendation:
            return None
        
        return setup
    
    def process_signal(self, setup: TradeSetup):
        """Process and send a trading signal + place paper trade"""
        
        # Format and send alert
        msg = self.alert_formatter.format_setup(setup)
        self.send_alert(msg)
        
        # Record for cooldown
        self.record_signal(setup.symbol, setup.strategy)
        
        # Auto-place paper trade for EOD tracking
        if PAPER_TRADING_AVAILABLE:
            try:
                platform = get_paper_platform()
                
                # Convert TradeSetup legs to paper trading format
                legs = []
                for leg in setup.legs:
                    legs.append({
                        'strike': leg.strike,
                        'option_type': leg.option_type,
                        'action': leg.action,
                        'premium': leg.premium,
                        'quantity': 1,  # 1 lot
                    })
                
                lot_size = self.lot_sizes.get(setup.symbol, 75)
                
                trade = platform.place_trade(
                    symbol=setup.symbol,
                    strategy=setup.strategy,
                    legs=legs,
                    lot_size=lot_size,
                    confidence=setup.confidence_score,
                    win_probability=setup.win_probability,
                )
                
                if trade:
                    print(f"\n📝 Paper trade placed: {trade.trade_id}")
            except Exception as e:
                print(f"\n⚠️ Failed to place paper trade: {e}")
        
        # Log
        print(f"\n🚨 SIGNAL: {setup.symbol} | {setup.strategy} | "
              f"Confidence: {setup.confidence_score}% | "
              f"Win Prob: {setup.win_probability:.0f}%")
    
    def run_single_scan(self):
        """Run a single scan of all symbols"""
        self.scan_count += 1
        now = datetime.now(IST)
        
        # Regular Iron Condor scan
        for symbol in self.symbols:
            try:
                setup = self.scan_symbol(symbol)
                
                if setup:
                    self.process_signal(setup)
            except Exception as e:
                print(f"Error scanning {symbol}: {e}")
        
        # Expiry day trading scan (once per hour)
        if EXPIRY_TRADER_AVAILABLE:
            try:
                is_exp, exp_symbol = is_expiry_day()
                if is_exp and now.minute < 5:  # Scan in first 5 mins of each hour
                    # Check cooldown
                    exp_key = f"EXPIRY_{exp_symbol}"
                    if exp_key not in self.signal_timestamps:
                        trader = get_expiry_trader()
                        trade = trader.generate_hero_zero(exp_symbol)
                        if trade:
                            msg = trader.format_alert(trade)
                            self.send_alert(msg)
                            self.signal_timestamps[exp_key] = now
                            print(f"\n🚀 EXPIRY SIGNAL: {exp_symbol} Hero-Zero!")
            except Exception as e:
                print(f"Expiry scan error: {e}")
    
    def send_startup_message(self):
        """Send startup notification"""
        msg = f"""
🟢 <b>REAL-TIME SCANNER STARTED</b>

⏰ {datetime.now(IST).strftime('%H:%M:%S')}

<b>Configuration:</b>
• Scan Interval: Every {self.scan_interval} seconds
• Min Confidence: {self.min_confidence}%
• Min Win Probability: {self.min_probability}%
• Signal Cooldown: {self.signal_cooldown_minutes} min

<b>Monitoring:</b>
• Symbols: {', '.join(self.symbols)}
• Strategies: 6 option selling strategies

<b>Market Hours:</b>
• Start: 9:20 AM
• End: 3:25 PM

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📱 <i>Alerts will come IMMEDIATELY when conditions are met!</i>
🔕 <i>No fixed times - real-time monitoring</i>
"""
        self.send_alert(msg)
    
    def send_shutdown_message(self, reason: str = "Manual stop"):
        """Send shutdown notification"""
        msg = f"""
🔴 <b>SCANNER STOPPED</b>

⏰ {datetime.now(IST).strftime('%H:%M:%S')}
📊 Total Scans: {self.scan_count}
📱 Signals Sent: {len(self.signal_timestamps)}

<b>Reason:</b> {reason}
"""
        self.send_alert(msg)
    
    def send_market_summary(self):
        """Send end of day summary"""
        msg = f"""
📊 <b>END OF DAY SUMMARY</b>

📅 {datetime.now(IST).strftime('%Y-%m-%d')}

<b>Scanner Statistics:</b>
• Total Scans: {self.scan_count}
• Signals Generated: {len(self.signal_timestamps)}

<b>Signals Today:</b>
"""
        if self.signal_timestamps:
            for key, timestamp in self.signal_timestamps.items():
                msg += f"• {key}: {timestamp.strftime('%H:%M')}\n"
        else:
            msg += "• No signals today\n"
        
        msg += "\n📱 <i>See you tomorrow!</i>"
        
        self.send_alert(msg)
    
    def run(self):
        """
        Main run loop - continuously scan during market hours
        """
        print("\n" + "="*60)
        print("     REAL-TIME CONTINUOUS SCANNER")
        print("="*60)
        print(f"⏱️  Scan Interval: {self.scan_interval} seconds")
        print(f"📊 Min Confidence: {self.min_confidence}%")
        print(f"🎯 Min Win Prob: {self.min_probability}%")
        print(f"⏰ Market Hours: {self.market_open} - {self.market_close}")
        print("="*60)
        print("\n⚠️  Press Ctrl+C to stop\n")
        
        self.is_running = True
        market_was_open = False
        
        # Handle graceful shutdown
        def signal_handler(sig, frame):
            print("\n\n🛑 Stopping scanner...")
            self.is_running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        
        try:
            while self.is_running:
                now = datetime.now(IST)
                
                if not self.is_market_hours():
                    # Market closed
                    if market_was_open:
                        # Just closed - send summary
                        self.send_market_summary()
                        market_was_open = False
                        # Reset for next day
                        self.signals_today.clear()
                        self.signal_timestamps.clear()
                        self.scan_count = 0
                    
                    if now.time() < self.market_open:
                        market_open_dt = now.replace(hour=self.market_open.hour, minute=self.market_open.minute, second=0, microsecond=0)
                        wait_mins = (market_open_dt - now).seconds // 60
                        print(f"\r⏳ Market opens in {wait_mins} minutes...", end="")
                    else:
                        print(f"\r⏸️  Market closed. Waiting...", end="")
                    
                    time_module.sleep(60)
                    continue
                
                # Market is open
                if not market_was_open:
                    # Just opened
                    self.send_startup_message()
                    market_was_open = True
                    print(f"\n🔔 Market OPEN - Scanner active!")
                
                # Run scan
                print(f"\r🔍 Scan #{self.scan_count + 1} at {now.strftime('%H:%M:%S')} | "
                      f"Signals: {len(self.signal_timestamps)}", end="")
                
                self.run_single_scan()
                
                # Wait for next scan
                time_module.sleep(self.scan_interval)
        
        except Exception as e:
            print(f"\n❌ Error: {e}")
            self.send_shutdown_message(f"Error: {e}")
        
        finally:
            self.is_running = False
            if market_was_open:
                self.send_shutdown_message()
            print("\n✅ Scanner stopped")
    
    def run_once(self):
        """Run a single scan (for testing)"""
        print(f"\n🔍 Single scan at {datetime.now(IST).strftime('%H:%M:%S')}...")
        self.run_single_scan()
        print(f"✅ Scan complete. Signals: {len(self.signal_timestamps)}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Real-Time Continuous Scanner')
    parser.add_argument('--run', action='store_true', help='Start continuous scanning')
    parser.add_argument('--once', action='store_true', help='Run single scan')
    parser.add_argument('--test', action='store_true', help='Send startup message')
    parser.add_argument('--interval', type=int, default=60, help='Scan interval in seconds')
    parser.add_argument('--confidence', type=int, default=60, help='Min confidence %')
    parser.add_argument('--probability', type=int, default=55, help='Min win probability %')
    
    args = parser.parse_args()
    
    scanner = RealTimeScanner(
        scan_interval=args.interval,
        min_confidence=args.confidence,
        min_probability=args.probability,
    )
    
    if args.test:
        scanner.send_startup_message()
        print("✅ Startup message sent!")
    elif args.once:
        scanner.run_once()
    elif args.run:
        scanner.run()
    else:
        print("Real-Time Continuous Scanner")
        print("\nUsage:")
        print("  --run         Start continuous scanning")
        print("  --once        Run single scan")
        print("  --test        Send startup message")
        print("  --interval N  Scan interval in seconds (default: 60)")
        print("  --confidence  Min confidence % (default: 60)")
        print("  --probability Min win probability % (default: 55)")
        print("\nExample:")
        print("  python realtime_scanner.py --run --interval 60 --confidence 70")


if __name__ == "__main__":
    main()
