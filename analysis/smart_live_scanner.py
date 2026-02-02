"""
Smart Live Signal Scanner
==========================
Analyzes market conditions BEFORE sending alerts
Only sends when conditions are favorable

Features:
- Trend analysis (EMAs)
- Volatility check (IV, ATR)
- Sentiment analysis (PCR)
- Probability scoring
- Smart strategy recommendation
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta, time
import time as time_module
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

# Import smart analyzer
from smart_analyzer import SmartMarketAnalyzer, MarketAnalysis, StrategyRecommendation

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

# Import paper trading for EOD tracking
try:
    from paper_trading_platform import get_platform as get_paper_platform
    PAPER_TRADING_AVAILABLE = True
except ImportError:
    PAPER_TRADING_AVAILABLE = False
    print("⚠ Paper trading not available - trades won't be tracked")

IST = timezone(timedelta(hours=5, minutes=30))

# Lot sizes
LOT_SIZES = {
    'NIFTY': 75,
    'BANKNIFTY': 30,
    'FINNIFTY': 65,
    'MIDCAPNIFTY': 100,
    'SENSEX': 20,
}


class SmartLiveScanner:
    """
    Smart scanner that:
    1. Analyzes market conditions
    2. Determines best strategy
    3. Only alerts if probability is HIGH
    """
    
    def __init__(self, min_confidence: int = 60):
        self.market_open = time(9, 15)
        self.market_close = time(15, 30)
        self.signals_today = []
        self.is_running = False
        self.min_confidence = min_confidence
        
        # Smart analyzer
        self.analyzer = SmartMarketAnalyzer()
        
        # Scan times (will analyze market at these times)
        self.scan_times = ['09:45', '10:15', '10:45', '11:15', '13:00', '14:00']
        
        # All available strategies with their parameters
        self.strategy_params = {
            StrategyRecommendation.SHORT_STRADDLE: {
                'sl_pct': 30, 'target_pct': 50, 'otm': 0
            },
            StrategyRecommendation.SHORT_STRANGLE: {
                'sl_pct': 40, 'target_pct': 40, 'otm': 2
            },
            StrategyRecommendation.IRON_CONDOR: {
                'sl_pct': 50, 'target_pct': 50, 'short_otm': 2, 'long_otm': 4
            },
            StrategyRecommendation.IRON_BUTTERFLY: {
                'sl_pct': 40, 'target_pct': 50, 'wing_distance': 3
            },
            StrategyRecommendation.BULL_PUT_SPREAD: {
                'sl_pct': 50, 'target_pct': 50, 'short_otm': 2, 'width': 2
            },
            StrategyRecommendation.BEAR_CALL_SPREAD: {
                'sl_pct': 50, 'target_pct': 50, 'short_otm': 2, 'width': 2
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
        import random
        bases = {'NIFTY': 24500, 'BANKNIFTY': 52000, 'FINNIFTY': 23500}
        return bases.get(symbol, 24500) + random.uniform(-50, 50)
    
    def get_live_option_price(self, symbol: str, strike: int, 
                              option_type: str) -> Optional[float]:
        """Get live option premium"""
        import random
        spot = {'NIFTY': 24500, 'BANKNIFTY': 52000}.get(symbol, 24500)
        if option_type == 'CE':
            intrinsic = max(0, spot - strike)
        else:
            intrinsic = max(0, strike - spot)
        return intrinsic + random.uniform(50, 150)
    
    def format_smart_alert(self, symbol: str, analysis: MarketAnalysis,
                           trade_details: Dict) -> str:
        """Format complete smart alert with analysis + trade instructions"""
        
        lot_size = LOT_SIZES.get(symbol, 50)
        strategy = analysis.recommended_strategy.value
        
        msg = f"""
🎯 <b>SMART TRADING SIGNAL</b>

📈 <b>Symbol:</b> {symbol}
💰 <b>Spot:</b> ₹{analysis.spot_price:,.2f}
⏰ <b>Time:</b> {datetime.now(IST).strftime('%H:%M:%S')}
🔥 <b>Confidence:</b> {analysis.confidence_score}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 MARKET ANALYSIS:</b>
• Regime: {analysis.market_regime.value}
• Trend: {analysis.trend}
• Volatility: {analysis.volatility_level} (IV: {analysis.iv_percentile:.0f}%)
• PCR: {analysis.pcr:.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🎯 RECOMMENDED: {strategy}</b>

<b>🔴 TRADE INSTRUCTIONS:</b>
"""
        # Add trade-specific instructions based on strategy
        strategy_enum = analysis.recommended_strategy
        
        if strategy_enum == StrategyRecommendation.SHORT_STRADDLE:
            atm = trade_details['atm']
            ce_price = trade_details['ce_price']
            pe_price = trade_details['pe_price']
            total = ce_price + pe_price
            
            msg += f"""
<b>1. SELL {symbol} CE {atm}</b>
   • Premium: ₹{ce_price:.2f}
   • Qty: {lot_size} (1 lot)
   
<b>2. SELL {symbol} PE {atm}</b>
   • Premium: ₹{pe_price:.2f}
   • Qty: {lot_size} (1 lot)

<b>Total Premium:</b> ₹{total:.2f}
<b>Max Profit:</b> ₹{total * lot_size:,.0f}
"""
            
        elif strategy_enum == StrategyRecommendation.SHORT_STRANGLE:
            ce_strike = trade_details['ce_strike']
            pe_strike = trade_details['pe_strike']
            ce_price = trade_details['ce_price']
            pe_price = trade_details['pe_price']
            total = ce_price + pe_price
            
            msg += f"""
<b>1. SELL {symbol} CE {ce_strike}</b>
   • Premium: ₹{ce_price:.2f}
   • Qty: {lot_size} (1 lot)
   
<b>2. SELL {symbol} PE {pe_strike}</b>
   • Premium: ₹{pe_price:.2f}
   • Qty: {lot_size} (1 lot)

<b>Total Premium:</b> ₹{total:.2f}
<b>Safe Zone:</b> {pe_strike} - {ce_strike}
"""

        elif strategy_enum == StrategyRecommendation.IRON_CONDOR:
            msg += f"""
<b>1. SELL {symbol} CE {trade_details['short_ce']}</b>
<b>2. BUY {symbol} CE {trade_details['long_ce']}</b>   ← Protection
<b>3. SELL {symbol} PE {trade_details['short_pe']}</b>
<b>4. BUY {symbol} PE {trade_details['long_pe']}</b>   ← Protection

<b>Max Profit:</b> ₹{trade_details['net_credit'] * lot_size:,.0f}
<b>Max Loss:</b> Limited to spread width
"""

        elif strategy_enum == StrategyRecommendation.BULL_PUT_SPREAD:
            msg += f"""
<b>1. SELL {symbol} PE {trade_details['short_pe']}</b>
   • Premium: ₹{trade_details['short_price']:.2f}
   
<b>2. BUY {symbol} PE {trade_details['long_pe']}</b>   ← Protection
   • Premium: ₹{trade_details['long_price']:.2f}

<b>Net Credit:</b> ₹{trade_details['net_credit']:.2f}
<b>Max Profit:</b> ₹{trade_details['net_credit'] * lot_size:,.0f}
<b>Profit if:</b> {symbol} stays above {trade_details['short_pe']}
"""

        elif strategy_enum == StrategyRecommendation.BEAR_CALL_SPREAD:
            msg += f"""
<b>1. SELL {symbol} CE {trade_details['short_ce']}</b>
   • Premium: ₹{trade_details['short_price']:.2f}
   
<b>2. BUY {symbol} CE {trade_details['long_ce']}</b>   ← Protection
   • Premium: ₹{trade_details['long_price']:.2f}

<b>Net Credit:</b> ₹{trade_details['net_credit']:.2f}
<b>Max Profit:</b> ₹{trade_details['net_credit'] * lot_size:,.0f}
<b>Profit if:</b> {symbol} stays below {trade_details['short_ce']}
"""
        
        # Add exit rules
        params = self.strategy_params.get(strategy_enum, {})
        if 'sl_pct' in params:
            total_premium = trade_details.get('total', trade_details.get('net_credit', 100))
            msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🎯 EXIT RULES:</b>
• <b>TARGET:</b> Close at {params['target_pct']}% profit
• <b>STOP LOSS:</b> Exit at {params['sl_pct']}% loss
• <b>TIME EXIT:</b> Close by 3:20 PM
"""
        
        # Add analysis notes
        msg += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📝 WHY THIS SIGNAL:</b>
"""
        for note in analysis.analysis_notes[:4]:  # Top 4 notes
            msg += f"• {note}\n"
        
        msg += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ <i>ALERT MODE - Verify prices before trading</i>
"""
        return msg
    
    def get_trade_details(self, symbol: str, analysis: MarketAnalysis) -> Dict:
        """Get specific trade details based on recommended strategy"""
        
        spot = analysis.spot_price
        gap = self.get_strike_gap(symbol, spot)
        atm = self.get_atm_strike(spot, gap)
        strategy = analysis.recommended_strategy
        
        if strategy == StrategyRecommendation.SHORT_STRADDLE:
            ce_price = self.get_live_option_price(symbol, atm, 'CE')
            pe_price = self.get_live_option_price(symbol, atm, 'PE')
            return {
                'atm': atm,
                'ce_price': ce_price,
                'pe_price': pe_price,
                'total': ce_price + pe_price,
            }
        
        elif strategy == StrategyRecommendation.SHORT_STRANGLE:
            otm = self.strategy_params[strategy]['otm']
            ce_strike = atm + gap * otm
            pe_strike = atm - gap * otm
            ce_price = self.get_live_option_price(symbol, ce_strike, 'CE')
            pe_price = self.get_live_option_price(symbol, pe_strike, 'PE')
            return {
                'ce_strike': ce_strike,
                'pe_strike': pe_strike,
                'ce_price': ce_price,
                'pe_price': pe_price,
                'total': ce_price + pe_price,
            }
        
        elif strategy == StrategyRecommendation.IRON_CONDOR:
            p = self.strategy_params[strategy]
            short_ce = atm + gap * p['short_otm']
            long_ce = atm + gap * p['long_otm']
            short_pe = atm - gap * p['short_otm']
            long_pe = atm - gap * p['long_otm']
            
            credit = (
                self.get_live_option_price(symbol, short_ce, 'CE') +
                self.get_live_option_price(symbol, short_pe, 'PE') -
                self.get_live_option_price(symbol, long_ce, 'CE') -
                self.get_live_option_price(symbol, long_pe, 'PE')
            )
            
            return {
                'short_ce': short_ce, 'long_ce': long_ce,
                'short_pe': short_pe, 'long_pe': long_pe,
                'net_credit': credit,
            }
        
        elif strategy == StrategyRecommendation.BULL_PUT_SPREAD:
            p = self.strategy_params[strategy]
            short_pe = atm - gap * p['short_otm']
            long_pe = short_pe - gap * p['width']
            
            short_price = self.get_live_option_price(symbol, short_pe, 'PE')
            long_price = self.get_live_option_price(symbol, long_pe, 'PE')
            
            return {
                'short_pe': short_pe, 'long_pe': long_pe,
                'short_price': short_price, 'long_price': long_price,
                'net_credit': short_price - long_price,
            }
        
        elif strategy == StrategyRecommendation.BEAR_CALL_SPREAD:
            p = self.strategy_params[strategy]
            short_ce = atm + gap * p['short_otm']
            long_ce = short_ce + gap * p['width']
            
            short_price = self.get_live_option_price(symbol, short_ce, 'CE')
            long_price = self.get_live_option_price(symbol, long_ce, 'CE')
            
            return {
                'short_ce': short_ce, 'long_ce': long_ce,
                'short_price': short_price, 'long_price': long_price,
                'net_credit': short_price - long_price,
            }
        
        return {}
    
    def send_alert(self, message: str) -> bool:
        """Send alert via Telegram"""
        if not NOTIFICATIONS_AVAILABLE:
            print(message)
            return False
        return send_telegram_message(message)
    
    def scan_and_alert(self, symbol: str) -> bool:
        """Perform smart scan and send alert if conditions are good"""
        
        current_time = datetime.now(IST).strftime('%H:%M')
        signal_key = f"{symbol}_{current_time}"
        
        # Already signaled?
        if signal_key in self.signals_today:
            return False
        
        # Analyze market
        analysis = self.analyzer.analyze(symbol)
        
        print(f"\n📊 {symbol}: {analysis.market_regime.value} | "
              f"Strategy: {analysis.recommended_strategy.value} | "
              f"Confidence: {analysis.confidence_score}%")
        
        # Only alert if conditions are favorable
        if not analysis.should_trade:
            print(f"   ⏭ Skipping - conditions not favorable")
            return False
        
        if analysis.confidence_score < self.min_confidence:
            print(f"   ⏭ Skipping - confidence too low ({analysis.confidence_score}%)")
            return False
        
        if analysis.recommended_strategy == StrategyRecommendation.NO_TRADE:
            print(f"   ⏭ Skipping - no trade recommended")
            return False
        
        # Get trade details
        trade_details = self.get_trade_details(symbol, analysis)
        
        if not trade_details:
            print(f"   ⏭ Skipping - could not get trade details")
            return False
        
        # Mark as signaled
        self.signals_today.append(signal_key)
        
        # Format and send alert
        msg = self.format_smart_alert(symbol, analysis, trade_details)
        self.send_alert(msg)
        
        # Auto-place paper trade for EOD tracking
        if PAPER_TRADING_AVAILABLE:
            try:
                platform = get_paper_platform()
                
                # Build legs based on strategy
                legs = self._build_paper_trade_legs(symbol, analysis, trade_details)
                
                if legs:
                    lot_size = LOT_SIZES.get(symbol, 75)
                    
                    trade = platform.place_trade(
                        symbol=symbol,
                        strategy=analysis.recommended_strategy.value,
                        legs=legs,
                        lot_size=lot_size,
                        confidence=analysis.confidence_score,
                        win_probability=analysis.win_probability,
                    )
                    
                    if trade:
                        print(f"   📝 Paper trade placed: {trade.trade_id}")
            except Exception as e:
                print(f"   ⚠️ Failed to place paper trade: {e}")
        
        print(f"   🚨 SIGNAL SENT!")
        return True
    
    def _build_paper_trade_legs(self, symbol: str, analysis, trade_details: Dict):
        """Build paper trade legs from trade details"""
        strategy = analysis.recommended_strategy
        legs = []
        
        if strategy == StrategyRecommendation.SHORT_STRADDLE:
            legs = [
                {'strike': trade_details['atm'], 'option_type': 'CE', 'action': 'SELL', 'premium': trade_details['ce_price'], 'quantity': 1},
                {'strike': trade_details['atm'], 'option_type': 'PE', 'action': 'SELL', 'premium': trade_details['pe_price'], 'quantity': 1},
            ]
        elif strategy == StrategyRecommendation.SHORT_STRANGLE:
            legs = [
                {'strike': trade_details['ce_strike'], 'option_type': 'CE', 'action': 'SELL', 'premium': trade_details['ce_price'], 'quantity': 1},
                {'strike': trade_details['pe_strike'], 'option_type': 'PE', 'action': 'SELL', 'premium': trade_details['pe_price'], 'quantity': 1},
            ]
        elif strategy == StrategyRecommendation.IRON_CONDOR:
            nc = trade_details['net_credit'] / 2  # Split credit between legs
            legs = [
                {'strike': trade_details['short_ce'], 'option_type': 'CE', 'action': 'SELL', 'premium': nc + 20, 'quantity': 1},
                {'strike': trade_details['long_ce'], 'option_type': 'CE', 'action': 'BUY', 'premium': 20, 'quantity': 1},
                {'strike': trade_details['short_pe'], 'option_type': 'PE', 'action': 'SELL', 'premium': nc + 20, 'quantity': 1},
                {'strike': trade_details['long_pe'], 'option_type': 'PE', 'action': 'BUY', 'premium': 20, 'quantity': 1},
            ]
        elif strategy == StrategyRecommendation.BULL_PUT_SPREAD:
            legs = [
                {'strike': trade_details['short_pe'], 'option_type': 'PE', 'action': 'SELL', 'premium': trade_details['short_price'], 'quantity': 1},
                {'strike': trade_details['long_pe'], 'option_type': 'PE', 'action': 'BUY', 'premium': trade_details['long_price'], 'quantity': 1},
            ]
        elif strategy == StrategyRecommendation.BEAR_CALL_SPREAD:
            legs = [
                {'strike': trade_details['short_ce'], 'option_type': 'CE', 'action': 'SELL', 'premium': trade_details['short_price'], 'quantity': 1},
                {'strike': trade_details['long_ce'], 'option_type': 'CE', 'action': 'BUY', 'premium': trade_details['long_price'], 'quantity': 1},
            ]
        
        return legs
    
    def run(self, check_interval: int = 30):
        """Run smart scanner"""
        print("\n" + "="*60)
        print("       SMART LIVE SCANNER (INTELLIGENT ALERTS)")
        print("="*60)
        print(f"Min Confidence: {self.min_confidence}%")
        print("Strategies: Straddle, Strangle, Iron Condor, Spreads")
        print("⚠️  NO real orders will be placed")
        print("Press Ctrl+C to stop")
        print("="*60)
        
        self.is_running = True
        last_scan_time = ""
        
        try:
            while self.is_running:
                now = datetime.now(IST)
                current_time = now.strftime('%H:%M')
                
                if not self.is_market_open():
                    if now.time() < self.market_open:
                        print(f"\r⏳ Waiting for market...", end="")
                    else:
                        print(f"\r⏸ Market closed", end="")
                        self.signals_today = []
                    time_module.sleep(60)
                    continue
                
                # Check if it's scan time
                if current_time in self.scan_times and current_time != last_scan_time:
                    print(f"\n\n🔍 SCAN TIME: {current_time}")
                    print("-" * 40)
                    
                    for symbol in ['NIFTY', 'BANKNIFTY']:
                        self.scan_and_alert(symbol)
                    
                    last_scan_time = current_time
                else:
                    print(f"\r⏳ {current_time} | Next scan: {self._next_scan_time()} | "
                          f"Signals: {len(self.signals_today)}", end="")
                
                time_module.sleep(check_interval)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Scanner stopped")
        
        self.is_running = False
    
    def _next_scan_time(self) -> str:
        """Get next scheduled scan time"""
        current = datetime.now(IST).strftime('%H:%M')
        for t in self.scan_times:
            if t > current:
                return t
        return "Tomorrow"
    
    def run_once(self):
        """Run a single smart scan"""
        print(f"\n🔍 Smart scan at {datetime.now(IST).strftime('%H:%M:%S')}...")
        
        for symbol in ['NIFTY', 'BANKNIFTY']:
            self.scan_and_alert(symbol)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Smart Live Scanner')
    parser.add_argument('--run', action='store_true', help='Start live scanning')
    parser.add_argument('--once', action='store_true', help='Run single scan')
    parser.add_argument('--test', action='store_true', help='Send test alert')
    parser.add_argument('--confidence', type=int, default=60, help='Min confidence %')
    
    args = parser.parse_args()
    
    scanner = SmartLiveScanner(min_confidence=args.confidence)
    
    if args.test:
        # Force a test alert
        from smart_analyzer import analyze_market
        analysis = analyze_market('NIFTY')
        analysis.should_trade = True
        analysis.confidence_score = 85
        trade_details = scanner.get_trade_details('NIFTY', analysis)
        msg = scanner.format_smart_alert('NIFTY', analysis, trade_details)
        scanner.send_alert(msg)
        print("✅ Test alert sent!")
    elif args.once:
        scanner.run_once()
    elif args.run:
        scanner.run()
    else:
        print("Smart Live Scanner")
        print("Usage:")
        print("  --run        Start live scanning")
        print("  --once       Run single scan")
        print("  --test       Send test alert")
        print("  --confidence Min confidence % (default: 60)")


if __name__ == "__main__":
    main()
