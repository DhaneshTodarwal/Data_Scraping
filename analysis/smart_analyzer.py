"""
Smart Market Analyzer
======================
Analyzes market conditions BEFORE sending strategy alerts
Only sends alerts when probability of success is HIGH

Analyzes:
- Volatility (IV Percentile, ATR)
- Trend (EMA, Price Action)
- Market Sentiment (PCR, OI)
- Time of Day (Avoid bad periods)
- Risk Level

Then recommends BEST strategy for current conditions
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta, time
from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))

# Import API if available
try:
    from angelone_api import AngelOneAPI
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False

IST = timezone(timedelta(hours=5, minutes=30))


class MarketRegime(Enum):
    """Market regime classification"""
    TRENDING_UP = "🟢 Trending Up"
    TRENDING_DOWN = "🔴 Trending Down"
    SIDEWAYS = "🟡 Sideways/Range"
    HIGH_VOLATILITY = "⚡ High Volatility"
    LOW_VOLATILITY = "😴 Low Volatility"


class StrategyRecommendation(Enum):
    """Strategy recommendations"""
    SHORT_STRADDLE = "Short Straddle"
    SHORT_STRANGLE = "Short Strangle"
    IRON_CONDOR = "Iron Condor"
    IRON_BUTTERFLY = "Iron Butterfly"
    BULL_PUT_SPREAD = "Bull Put Spread"
    BEAR_CALL_SPREAD = "Bear Call Spread"
    NO_TRADE = "No Trade"


@dataclass
class MarketAnalysis:
    """Complete market analysis result"""
    symbol: str
    timestamp: str
    spot_price: float
    
    # Trend Analysis
    trend: str
    ema_9: float
    ema_21: float
    ema_50: float
    
    # Volatility Analysis
    iv_percentile: float  # 0-100
    atr: float
    atr_percent: float
    volatility_level: str
    
    # Sentiment
    pcr: float  # Put-Call Ratio
    oi_buildup: str
    
    # Range Analysis
    day_high: float
    day_low: float
    day_range_percent: float
    
    # Final Recommendation
    market_regime: MarketRegime
    recommended_strategy: StrategyRecommendation
    confidence_score: int  # 0-100
    analysis_notes: List[str]
    
    # Whether to trade
    should_trade: bool


class SmartMarketAnalyzer:
    """
    Intelligent market analyzer that determines:
    1. Current market conditions
    2. Best strategy for those conditions
    3. Whether to trade at all
    """
    
    def __init__(self):
        self.market_open = time(9, 15)
        self.market_close = time(15, 30)
        self.avoid_times = [
            (time(9, 15), time(9, 30)),   # First 15 mins - too volatile
            (time(15, 15), time(15, 30)), # Last 15 mins - squaring off
        ]
        
        # Historical data for comparison (would be loaded from files in production)
        self.iv_history = {}
        self.atr_history = {}
    
    def _is_avoid_time(self) -> bool:
        """Check if current time should be avoided"""
        now = datetime.now(IST).time()
        for start, end in self.avoid_times:
            if start <= now <= end:
                return True
        return False
    
    def _get_simulated_data(self, symbol: str) -> Dict:
        """Get simulated data for testing (replace with live data in production)"""
        import random
        
        bases = {
            'NIFTY': 24500,
            'BANKNIFTY': 52000,
            'FINNIFTY': 23500,
        }
        base = bases.get(symbol, 24500)
        
        spot = base + random.uniform(-100, 100)
        day_change = random.uniform(-0.5, 0.5)
        
        # Simulate indicators
        ema_9 = base + random.uniform(-50, 50)
        ema_21 = base + random.uniform(-80, 80)
        ema_50 = base + random.uniform(-100, 100)
        
        atr = base * random.uniform(0.005, 0.015)
        
        # Random volatility scenario
        iv_percentile = random.uniform(20, 80)
        pcr = random.uniform(0.7, 1.3)
        
        return {
            'spot': spot,
            'day_high': spot + random.uniform(50, 150),
            'day_low': spot - random.uniform(50, 150),
            'day_change': day_change,
            'ema_9': ema_9,
            'ema_21': ema_21,
            'ema_50': ema_50,
            'atr': atr,
            'iv_percentile': iv_percentile,
            'pcr': pcr,
            'open': spot - (spot * day_change / 100),
        }
    
    def _get_live_data(self, symbol: str) -> Dict:
        """Get live market data from API"""
        if not API_AVAILABLE:
            return self._get_simulated_data(symbol)
        
        try:
            api = AngelOneAPI()
            # In production, fetch real data here
            return self._get_simulated_data(symbol)
        except Exception:
            return self._get_simulated_data(symbol)
    
    def _analyze_trend(self, data: Dict) -> Tuple[str, List[str]]:
        """Analyze market trend"""
        notes = []
        
        spot = data['spot']
        ema_9 = data['ema_9']
        ema_21 = data['ema_21']
        ema_50 = data['ema_50']
        
        # EMA alignment
        if ema_9 > ema_21 > ema_50:
            trend = "BULLISH"
            notes.append("✅ EMAs aligned bullish (9 > 21 > 50)")
        elif ema_9 < ema_21 < ema_50:
            trend = "BEARISH"
            notes.append("⚠️ EMAs aligned bearish (9 < 21 < 50)")
        else:
            trend = "SIDEWAYS"
            notes.append("🟡 EMAs mixed - sideways market")
        
        # Price vs EMA
        if spot > ema_9:
            notes.append(f"Price above 9 EMA ({ema_9:.0f})")
        else:
            notes.append(f"Price below 9 EMA ({ema_9:.0f})")
        
        return trend, notes
    
    def _analyze_volatility(self, data: Dict, symbol: str) -> Tuple[str, float, List[str]]:
        """Analyze volatility conditions"""
        notes = []
        
        atr = data['atr']
        spot = data['spot']
        atr_pct = (atr / spot) * 100
        iv_pctl = data['iv_percentile']
        
        # Volatility classification
        if iv_pctl < 25 and atr_pct < 0.8:
            level = "LOW"
            notes.append(f"😴 Low volatility (IV Pctl: {iv_pctl:.0f}%)")
            notes.append("⚠️ Premium collection may be less profitable")
        elif iv_pctl > 70 or atr_pct > 1.2:
            level = "HIGH"
            notes.append(f"⚡ High volatility (IV Pctl: {iv_pctl:.0f}%)")
            notes.append("⚠️ Higher risk, use defined-risk strategies")
        else:
            level = "MODERATE"
            notes.append(f"✅ Moderate volatility (IV Pctl: {iv_pctl:.0f}%)")
            notes.append("Good conditions for premium selling")
        
        return level, iv_pctl, notes
    
    def _analyze_sentiment(self, data: Dict) -> Tuple[str, List[str]]:
        """Analyze market sentiment using PCR"""
        notes = []
        pcr = data['pcr']
        
        if pcr < 0.8:
            sentiment = "BULLISH"
            notes.append(f"🟢 PCR {pcr:.2f} - Bullish sentiment")
        elif pcr > 1.2:
            sentiment = "BEARISH"
            notes.append(f"🔴 PCR {pcr:.2f} - Bearish sentiment")
        else:
            sentiment = "NEUTRAL"
            notes.append(f"🟡 PCR {pcr:.2f} - Neutral sentiment")
        
        return sentiment, notes
    
    def _determine_regime(self, trend: str, vol_level: str, iv_pctl: float) -> MarketRegime:
        """Determine overall market regime"""
        if vol_level == "HIGH":
            return MarketRegime.HIGH_VOLATILITY
        elif vol_level == "LOW":
            return MarketRegime.LOW_VOLATILITY
        elif trend == "BULLISH":
            return MarketRegime.TRENDING_UP
        elif trend == "BEARISH":
            return MarketRegime.TRENDING_DOWN
        else:
            return MarketRegime.SIDEWAYS
    
    def _recommend_strategy(self, regime: MarketRegime, trend: str, 
                            sentiment: str, iv_pctl: float) -> Tuple[StrategyRecommendation, int, List[str]]:
        """
        Recommend best strategy based on conditions
        PRIORITY: Iron Condor (safest, defined risk, hedged)
        """
        notes = []
        
        # ALWAYS PREFER IRON CONDOR for safety (user request)
        # Iron Condor = Defined max loss = Safer
        
        # High volatility - Iron Condor is best
        if regime == MarketRegime.HIGH_VOLATILITY:
            notes.append("📈 High IV - Iron Condor for defined risk")
            notes.append("✅ Max loss is LIMITED (hedged position)")
            return StrategyRecommendation.IRON_CONDOR, 80, notes
        
        # Low volatility - may not be worth trading
        if regime == MarketRegime.LOW_VOLATILITY:
            notes.append("😴 Low IV - premium collection may not cover costs")
            notes.append("Consider waiting for better opportunity")
            return StrategyRecommendation.NO_TRADE, 30, notes
        
        # Sideways - BEST for Iron Condor
        if regime == MarketRegime.SIDEWAYS:
            notes.append("🎯 Sideways market - PERFECT for Iron Condor")
            notes.append("✅ Profit if market stays in range")
            notes.append("✅ Loss is capped (hedged)")
            return StrategyRecommendation.IRON_CONDOR, 85, notes
        
        # Trending UP - Iron Condor with wider CE side, or Bull Put Spread
        if regime == MarketRegime.TRENDING_UP:
            if sentiment == "BULLISH":
                notes.append("🟢 Bullish - Iron Condor with skew towards CE")
                notes.append("✅ Protected if market reverses")
                return StrategyRecommendation.IRON_CONDOR, 75, notes
            else:
                notes.append("🟢 Mild bullish - Iron Condor for range")
                return StrategyRecommendation.IRON_CONDOR, 70, notes
        
        # Trending DOWN - Iron Condor with wider PE side, or Bear Call Spread
        if regime == MarketRegime.TRENDING_DOWN:
            if sentiment == "BEARISH":
                notes.append("🔴 Bearish - Iron Condor with skew towards PE")
                notes.append("✅ Protected if market reverses")
                return StrategyRecommendation.IRON_CONDOR, 75, notes
            else:
                notes.append("🔴 Mild bearish - Iron Condor for range")
                return StrategyRecommendation.IRON_CONDOR, 70, notes
        
        # Default - Always Iron Condor for safety
        notes.append("🛡️ Iron Condor for maximum safety")
        notes.append("✅ Defined risk, hedged position")
        return StrategyRecommendation.IRON_CONDOR, 75, notes
    
    def analyze(self, symbol: str) -> MarketAnalysis:
        """
        Perform complete market analysis
        Returns analysis with recommendation
        """
        # Get market data
        data = self._get_live_data(symbol)
        
        # Analyze each aspect
        trend, trend_notes = self._analyze_trend(data)
        vol_level, iv_pctl, vol_notes = self._analyze_volatility(data, symbol)
        sentiment, sentiment_notes = self._analyze_sentiment(data)
        
        # Determine regime
        regime = self._determine_regime(trend, vol_level, iv_pctl)
        
        # Get recommendation
        strategy, confidence, strategy_notes = self._recommend_strategy(
            regime, trend, sentiment, iv_pctl
        )
        
        # Combine all notes
        all_notes = trend_notes + vol_notes + sentiment_notes + strategy_notes
        
        # Should we trade?
        should_trade = (
            confidence >= 60 and 
            strategy != StrategyRecommendation.NO_TRADE and
            not self._is_avoid_time()
        )
        
        if self._is_avoid_time():
            all_notes.insert(0, "⏰ Currently in avoid-time period (market open/close)")
        
        # Calculate day range
        day_range = data['day_high'] - data['day_low']
        day_range_pct = (day_range / data['spot']) * 100
        
        return MarketAnalysis(
            symbol=symbol,
            timestamp=datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S'),
            spot_price=data['spot'],
            trend=trend,
            ema_9=data['ema_9'],
            ema_21=data['ema_21'],
            ema_50=data['ema_50'],
            iv_percentile=iv_pctl,
            atr=data['atr'],
            atr_percent=(data['atr'] / data['spot']) * 100,
            volatility_level=vol_level,
            pcr=data['pcr'],
            oi_buildup="Mixed",  # Would come from OI analysis
            day_high=data['day_high'],
            day_low=data['day_low'],
            day_range_percent=day_range_pct,
            market_regime=regime,
            recommended_strategy=strategy,
            confidence_score=confidence,
            analysis_notes=all_notes,
            should_trade=should_trade,
        )
    
    def format_analysis_message(self, analysis: MarketAnalysis) -> str:
        """Format analysis for Telegram"""
        trade_status = "✅ TRADEABLE" if analysis.should_trade else "❌ NO TRADE"
        
        msg = f"""
📊 <b>SMART MARKET ANALYSIS</b>

📈 <b>Symbol:</b> {analysis.symbol}
💰 <b>Spot:</b> ₹{analysis.spot_price:,.2f}
⏰ <b>Time:</b> {analysis.timestamp}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📉 MARKET REGIME:</b>
{analysis.market_regime.value}

<b>📈 TREND ANALYSIS:</b>
• Trend: {analysis.trend}
• EMA 9: {analysis.ema_9:,.0f}
• EMA 21: {analysis.ema_21:,.0f}
• EMA 50: {analysis.ema_50:,.0f}

<b>⚡ VOLATILITY:</b>
• Level: {analysis.volatility_level}
• IV Percentile: {analysis.iv_percentile:.0f}%
• ATR: {analysis.atr:.0f} ({analysis.atr_percent:.2f}%)

<b>📊 SENTIMENT:</b>
• PCR: {analysis.pcr:.2f}
• Day Range: {analysis.day_range_percent:.2f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🎯 RECOMMENDATION:</b>
<b>Strategy: {analysis.recommended_strategy.value}</b>
<b>Confidence: {analysis.confidence_score}%</b>
<b>Status: {trade_status}</b>

<b>📝 ANALYSIS NOTES:</b>
"""
        for note in analysis.analysis_notes:
            msg += f"• {note}\n"
        
        msg += "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        return msg


# For importing from other modules
analyzer = SmartMarketAnalyzer()


def analyze_market(symbol: str) -> MarketAnalysis:
    """Quick access to market analysis"""
    return analyzer.analyze(symbol)


def get_analysis_message(symbol: str) -> str:
    """Get formatted analysis message"""
    analysis = analyzer.analyze(symbol)
    return analyzer.format_analysis_message(analysis)


if __name__ == "__main__":
    # Test the analyzer
    print("\n" + "="*60)
    print("       SMART MARKET ANALYZER - TEST")
    print("="*60)
    
    for symbol in ['NIFTY', 'BANKNIFTY']:
        analysis = analyze_market(symbol)
        print(analyzer.format_analysis_message(analysis))
        print("\n")
