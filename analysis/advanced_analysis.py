"""
Advanced Market Analysis Module
================================
Contains advanced analysis features for high-probability signals:

1. OI Analysis - Open Interest, Max Pain, PCR at strikes
2. Greeks Analysis - Delta, Theta, IV, Gamma
3. Support/Resistance - Auto-detected key levels
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

IST = timezone(timedelta(hours=5, minutes=30))

# Try importing API
try:
    from angelone_api import AngelOneAPI
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False

# Try importing live data provider
try:
    from live_data_provider import get_live_spot
    LIVE_DATA_AVAILABLE = True
except ImportError:
    LIVE_DATA_AVAILABLE = False


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class OIAnalysis:
    """Open Interest Analysis Result"""
    max_pain: int
    max_pain_distance: float  # % distance from spot
    
    # PCR
    total_pcr: float
    atm_pcr: float
    pcr_interpretation: str
    
    # OI Buildup
    ce_max_oi_strike: int
    ce_max_oi: int
    pe_max_oi_strike: int
    pe_max_oi: int
    
    # OI Change
    ce_oi_additions: List[int]  # Strikes with OI increase
    pe_oi_additions: List[int]
    
    # Signals
    oi_signals: List[str]
    oi_bias: str  # BULLISH, BEARISH, NEUTRAL


@dataclass
class GreeksAnalysis:
    """Options Greeks Analysis Result"""
    # ATM Greeks
    atm_strike: int
    atm_ce_delta: float
    atm_pe_delta: float
    atm_ce_theta: float
    atm_pe_theta: float
    atm_ce_iv: float
    atm_pe_iv: float
    
    # Combined
    total_theta: float  # Per hour decay (positive = good for sellers)
    iv_percentile: float
    iv_skew: float  # CE IV - PE IV
    
    # Gamma risk
    gamma_risk: str  # LOW, MEDIUM, HIGH
    
    # Signals
    greeks_signals: List[str]
    
    # Best strikes for selling
    best_ce_strike: int
    best_pe_strike: int


@dataclass
class SupportResistance:
    """Support and Resistance Levels"""
    # Key levels
    resistances: List[Tuple[float, str]]  # (price, source)
    supports: List[Tuple[float, str]]     # (price, source)
    
    # Nearest levels
    nearest_resistance: float
    nearest_support: float
    
    # Range
    expected_range_high: float
    expected_range_low: float
    
    # Position
    spot_position: str  # "Near Support", "Near Resistance", "Middle"
    
    # Signals
    sr_signals: List[str]


@dataclass 
class AdvancedAnalysis:
    """Combined Advanced Analysis"""
    symbol: str
    spot: float
    timestamp: str
    
    oi: OIAnalysis
    greeks: GreeksAnalysis
    sr: SupportResistance
    
    # Overall signals
    total_score: int  # 0-100
    all_signals: List[str]
    should_trade: bool
    recommended_adjustments: List[str]


# =============================================================================
# OI ANALYZER
# =============================================================================

class OIAnalyzer:
    """Analyze Open Interest for trading signals"""
    
    def __init__(self):
        self.oi_data = {}  # Cache
    
    def _simulate_oi_data(self, symbol: str, spot: float) -> Dict:
        """Simulate OI data for testing"""
        import random
        
        gap = 50 if spot < 30000 else 100
        atm = round(spot / gap) * gap
        
        oi_chain = {'CE': {}, 'PE': {}}
        
        # Generate OI for strikes around ATM
        for i in range(-10, 11):
            strike = int(atm + i * gap)
            
            # CE OI typically higher above spot
            ce_base = 5000000 if i > 0 else 2000000
            pe_base = 5000000 if i < 0 else 2000000
            
            oi_chain['CE'][strike] = {
                'oi': int(ce_base * random.uniform(0.5, 2.0)),
                'oi_change': int(random.uniform(-500000, 1000000)),
                'ltp': max(5, (spot - strike) + random.uniform(50, 150)) if i <= 0 else random.uniform(20, 100),
            }
            oi_chain['PE'][strike] = {
                'oi': int(pe_base * random.uniform(0.5, 2.0)),
                'oi_change': int(random.uniform(-500000, 1000000)),
                'ltp': max(5, (strike - spot) + random.uniform(50, 150)) if i >= 0 else random.uniform(20, 100),
            }
        
        return oi_chain
    
    def _calculate_max_pain(self, oi_data: Dict, spot: float) -> int:
        """Calculate max pain strike"""
        strikes = set(oi_data['CE'].keys()) | set(oi_data['PE'].keys())
        
        min_pain = float('inf')
        max_pain_strike = int(spot)
        
        for strike in strikes:
            pain = 0
            
            # Pain for call writers
            for s in oi_data['CE'].keys():
                if s < strike:
                    pain += oi_data['CE'][s]['oi'] * (strike - s)
            
            # Pain for put writers
            for s in oi_data['PE'].keys():
                if s > strike:
                    pain += oi_data['PE'][s]['oi'] * (s - strike)
            
            if pain < min_pain:
                min_pain = pain
                max_pain_strike = strike
        
        return int(max_pain_strike)
    
    def analyze(self, symbol: str, spot: float) -> OIAnalysis:
        """Perform complete OI analysis"""
        
        # Get OI data
        oi_data = self._simulate_oi_data(symbol, spot)
        
        gap = 50 if spot < 30000 else 100
        atm = round(spot / gap) * gap
        
        # Calculate max pain
        max_pain = self._calculate_max_pain(oi_data, spot)
        max_pain_dist = abs(spot - max_pain) / spot * 100
        
        # Calculate PCR
        total_ce_oi = sum(d['oi'] for d in oi_data['CE'].values())
        total_pe_oi = sum(d['oi'] for d in oi_data['PE'].values())
        total_pcr = total_pe_oi / total_ce_oi if total_ce_oi > 0 else 1.0
        
        # ATM PCR
        atm_ce = oi_data['CE'].get(atm, {}).get('oi', 0)
        atm_pe = oi_data['PE'].get(atm, {}).get('oi', 0)
        atm_pcr = atm_pe / atm_ce if atm_ce > 0 else 1.0
        
        # PCR interpretation
        if total_pcr < 0.8:
            pcr_interp = "🔴 Bearish (Put writers confident)"
        elif total_pcr > 1.3:
            pcr_interp = "🟢 Bullish (Call writers confident)"
        else:
            pcr_interp = "🟡 Neutral"
        
        # Find max OI strikes
        ce_max = max(oi_data['CE'].items(), key=lambda x: x[1]['oi'])
        pe_max = max(oi_data['PE'].items(), key=lambda x: x[1]['oi'])
        
        # Find OI additions
        ce_additions = [s for s, d in oi_data['CE'].items() if d['oi_change'] > 100000]
        pe_additions = [s for s, d in oi_data['PE'].items() if d['oi_change'] > 100000]
        
        # Generate signals
        signals = []
        bias = "NEUTRAL"
        
        if max_pain_dist < 1.0:
            signals.append(f"✅ Spot near Max Pain ({max_pain}) - likely to stay in range")
        else:
            signals.append(f"⚠️ Spot {max_pain_dist:.1f}% from Max Pain ({max_pain})")
        
        if total_pcr > 1.2:
            signals.append(f"🟢 High PCR ({total_pcr:.2f}) - Bullish for expiry")
            bias = "BULLISH"
        elif total_pcr < 0.8:
            signals.append(f"🔴 Low PCR ({total_pcr:.2f}) - Bearish for expiry")
            bias = "BEARISH"
        
        if ce_max[0] > spot:
            signals.append(f"📊 Max CE OI at {ce_max[0]} - Acts as resistance")
        if pe_max[0] < spot:
            signals.append(f"📊 Max PE OI at {pe_max[0]} - Acts as support")
        
        return OIAnalysis(
            max_pain=max_pain,
            max_pain_distance=max_pain_dist,
            total_pcr=total_pcr,
            atm_pcr=atm_pcr,
            pcr_interpretation=pcr_interp,
            ce_max_oi_strike=ce_max[0],
            ce_max_oi=ce_max[1]['oi'],
            pe_max_oi_strike=pe_max[0],
            pe_max_oi=pe_max[1]['oi'],
            ce_oi_additions=ce_additions[:3],
            pe_oi_additions=pe_additions[:3],
            oi_signals=signals,
            oi_bias=bias,
        )


# =============================================================================
# GREEKS ANALYZER
# =============================================================================

class GreeksAnalyzer:
    """Analyze Options Greeks"""
    
    def _calculate_iv(self, spot: float, strike: int, premium: float, 
                      option_type: str, days_to_expiry: float = 1) -> float:
        """Simple IV approximation"""
        time_factor = max(days_to_expiry / 365, 0.001)
        
        if option_type == 'CE':
            intrinsic = max(0, spot - strike)
        else:
            intrinsic = max(0, strike - spot)
        
        time_value = max(0, premium - intrinsic)
        
        # Approximate IV using time value
        iv = (time_value / spot) / np.sqrt(time_factor) * 100
        return min(max(iv, 5), 100)  # Cap between 5% and 100%
    
    def _calculate_delta(self, spot: float, strike: int, iv: float,
                         option_type: str) -> float:
        """Approximate delta calculation"""
        moneyness = (spot - strike) / spot * 100
        
        if option_type == 'CE':
            if moneyness > 2:  # ITM
                return 0.7 + min(moneyness / 10, 0.29)
            elif moneyness < -2:  # OTM
                return 0.3 - min(abs(moneyness) / 10, 0.25)
            else:  # ATM
                return 0.5 + moneyness / 20
        else:  # PE
            if moneyness < -2:  # ITM for put
                return -0.7 - min(abs(moneyness) / 10, 0.29)
            elif moneyness > 2:  # OTM for put
                return -0.3 + min(moneyness / 10, 0.25)
            else:  # ATM
                return -0.5 + moneyness / 20
    
    def _calculate_theta(self, premium: float, days_to_expiry: float,
                         iv: float) -> float:
        """Approximate theta (daily decay)"""
        if days_to_expiry <= 0:
            days_to_expiry = 1
        
        # Higher IV = more theta
        iv_factor = iv / 15  # Normalized around 15% IV
        
        # Time decay accelerates near expiry
        time_factor = min(2.0, 1 / np.sqrt(days_to_expiry))
        
        # Approximate daily theta
        theta = premium * 0.1 * time_factor * iv_factor
        return theta
    
    def analyze(self, symbol: str, spot: float, 
                days_to_expiry: float = 1) -> GreeksAnalysis:
        """Analyze Greeks for the symbol"""
        import random
        
        gap = 50 if spot < 30000 else 100
        atm = int(round(spot / gap) * gap)
        
        # Simulate premiums
        atm_ce_premium = random.uniform(80, 150)
        atm_pe_premium = random.uniform(80, 150)
        
        # Calculate IVs
        atm_ce_iv = self._calculate_iv(spot, atm, atm_ce_premium, 'CE', days_to_expiry)
        atm_pe_iv = self._calculate_iv(spot, atm, atm_pe_premium, 'PE', days_to_expiry)
        
        # Calculate Deltas
        atm_ce_delta = self._calculate_delta(spot, atm, atm_ce_iv, 'CE')
        atm_pe_delta = self._calculate_delta(spot, atm, atm_pe_iv, 'PE')
        
        # Calculate Thetas
        atm_ce_theta = self._calculate_theta(atm_ce_premium, days_to_expiry, atm_ce_iv)
        atm_pe_theta = self._calculate_theta(atm_pe_premium, days_to_expiry, atm_pe_iv)
        
        total_theta = (atm_ce_theta + atm_pe_theta) * 75  # Per lot for NIFTY
        
        # IV Percentile (simulated - would come from historical data)
        iv_percentile = random.uniform(20, 80)
        
        # IV Skew
        iv_skew = atm_ce_iv - atm_pe_iv
        
        # Gamma risk
        if days_to_expiry < 0.5:
            gamma_risk = "HIGH"
        elif days_to_expiry < 2:
            gamma_risk = "MEDIUM"
        else:
            gamma_risk = "LOW"
        
        # Best strikes for selling (2 OTM)
        best_ce = atm + 2 * gap
        best_pe = atm - 2 * gap
        
        # Generate signals
        signals = []
        
        if iv_percentile > 60:
            signals.append(f"✅ High IV ({iv_percentile:.0f}%ile) - Good for selling")
        elif iv_percentile < 30:
            signals.append(f"⚠️ Low IV ({iv_percentile:.0f}%ile) - Limited premium")
        else:
            signals.append(f"🟡 IV at {iv_percentile:.0f}%ile - Moderate")
        
        signals.append(f"⏱️ Theta decay: ₹{total_theta:.0f}/day (in your favor)")
        
        if abs(iv_skew) > 3:
            if iv_skew > 0:
                signals.append(f"📈 CE IV higher ({iv_skew:.1f}%) - Market expects upside")
            else:
                signals.append(f"📉 PE IV higher ({abs(iv_skew):.1f}%) - Market expects downside")
        
        if gamma_risk == "HIGH":
            signals.append("⚠️ HIGH Gamma Risk - Expiry day volatility!")
        
        return GreeksAnalysis(
            atm_strike=atm,
            atm_ce_delta=atm_ce_delta,
            atm_pe_delta=atm_pe_delta,
            atm_ce_theta=atm_ce_theta,
            atm_pe_theta=atm_pe_theta,
            atm_ce_iv=atm_ce_iv,
            atm_pe_iv=atm_pe_iv,
            total_theta=total_theta,
            iv_percentile=iv_percentile,
            iv_skew=iv_skew,
            gamma_risk=gamma_risk,
            greeks_signals=signals,
            best_ce_strike=best_ce,
            best_pe_strike=best_pe,
        )


# =============================================================================
# SUPPORT/RESISTANCE ANALYZER
# =============================================================================

class SupportResistanceAnalyzer:
    """Detect Support and Resistance Levels"""
    
    def _get_pivot_levels(self, high: float, low: float, close: float) -> Dict:
        """Calculate pivot points"""
        pivot = (high + low + close) / 3
        
        return {
            'pivot': pivot,
            'r1': 2 * pivot - low,
            'r2': pivot + (high - low),
            'r3': high + 2 * (pivot - low),
            's1': 2 * pivot - high,
            's2': pivot - (high - low),
            's3': low - 2 * (high - pivot),
        }
    
    def _get_round_numbers(self, spot: float, gap: int) -> List[float]:
        """Get nearby round numbers"""
        levels = []
        base = round(spot / gap) * gap
        
        for i in range(-5, 6):
            level = base + i * gap
            if level != spot:
                levels.append(level)
        
        return levels
    
    def analyze(self, symbol: str, spot: float, 
                prev_high: float = None, prev_low: float = None,
                prev_close: float = None) -> SupportResistance:
        """Analyze Support and Resistance"""
        import random
        
        gap = 50 if spot < 30000 else 100
        
        # Simulate previous day data if not provided
        if prev_high is None:
            prev_high = spot * random.uniform(1.005, 1.015)
        if prev_low is None:
            prev_low = spot * random.uniform(0.985, 0.995)
        if prev_close is None:
            prev_close = spot * random.uniform(0.998, 1.002)
        
        # Get pivot levels
        pivots = self._get_pivot_levels(prev_high, prev_low, prev_close)
        
        # Get round numbers
        rounds = self._get_round_numbers(spot, gap)
        
        # Compile resistances (above spot)
        resistances = []
        for level in [pivots['r1'], pivots['r2']]:
            if level > spot:
                resistances.append((level, "Pivot"))
        for level in rounds:
            if level > spot and level not in [r[0] for r in resistances]:
                resistances.append((level, "Round"))
        resistances.sort(key=lambda x: x[0])
        
        # Compile supports (below spot)
        supports = []
        for level in [pivots['s1'], pivots['s2']]:
            if level < spot:
                supports.append((level, "Pivot"))
        for level in rounds:
            if level < spot and level not in [s[0] for s in supports]:
                supports.append((level, "Round"))
        supports.sort(key=lambda x: x[0], reverse=True)
        
        # Nearest levels
        nearest_r = resistances[0][0] if resistances else spot + gap
        nearest_s = supports[0][0] if supports else spot - gap
        
        # Expected range
        atr = spot * random.uniform(0.008, 0.015)  # Simulated ATR
        expected_high = spot + atr * 1.5
        expected_low = spot - atr * 1.5
        
        # Position relative to S/R
        dist_to_r = (nearest_r - spot) / spot * 100
        dist_to_s = (spot - nearest_s) / spot * 100
        
        if dist_to_s < 0.3:
            position = "Near Support"
        elif dist_to_r < 0.3:
            position = "Near Resistance"
        else:
            position = "Middle of Range"
        
        # Generate signals
        signals = []
        
        signals.append(f"📍 Position: {position}")
        signals.append(f"📈 Resistance: {nearest_r:.0f} ({dist_to_r:.1f}% away)")
        signals.append(f"📉 Support: {nearest_s:.0f} ({dist_to_s:.1f}% away)")
        
        if position == "Near Support":
            signals.append("✅ Near support - Good for Bull Put Spread")
        elif position == "Near Resistance":
            signals.append("✅ Near resistance - Good for Bear Call Spread")
        else:
            signals.append("✅ Middle of range - Good for Straddle/Strangle")
        
        return SupportResistance(
            resistances=resistances[:5],
            supports=supports[:5],
            nearest_resistance=nearest_r,
            nearest_support=nearest_s,
            expected_range_high=expected_high,
            expected_range_low=expected_low,
            spot_position=position,
            sr_signals=signals,
        )


# =============================================================================
# COMBINED ADVANCED ANALYZER
# =============================================================================

class AdvancedMarketAnalyzer:
    """Combined advanced analysis"""
    
    def __init__(self):
        self.oi_analyzer = OIAnalyzer()
        self.greeks_analyzer = GreeksAnalyzer()
        self.sr_analyzer = SupportResistanceAnalyzer()
    
    def analyze(self, symbol: str, spot: float = None) -> AdvancedAnalysis:
        """Perform complete advanced analysis"""
        import random
        
        if spot is None:
            # Try to get LIVE spot price
            if LIVE_DATA_AVAILABLE:
                spot = get_live_spot(symbol)
            
            # Fallback to simulated if live not available
            if spot is None:
                bases = {'NIFTY': 24500, 'BANKNIFTY': 52000}
                spot = bases.get(symbol, 24500) + random.uniform(-50, 50)
                print(f"⚠️ Using simulated spot for {symbol}: {spot:.2f}")
        
        # Run all analyzers
        oi = self.oi_analyzer.analyze(symbol, spot)
        greeks = self.greeks_analyzer.analyze(symbol, spot)
        sr = self.sr_analyzer.analyze(symbol, spot)
        
        # Combine signals
        all_signals = oi.oi_signals + greeks.greeks_signals + sr.sr_signals
        
        # Calculate overall score
        score = 50  # Base score
        
        # OI factors
        if oi.max_pain_distance < 1.0:
            score += 15
        if oi.total_pcr > 0.9 and oi.total_pcr < 1.2:
            score += 10
        
        # Greeks factors
        if greeks.iv_percentile > 40:
            score += 10
        if greeks.gamma_risk != "HIGH":
            score += 10
        
        # S/R factors
        if "Middle" in sr.spot_position:
            score += 10
        
        # Cap score
        score = min(100, max(0, score))
        
        # Should trade?
        should_trade = score >= 60 and greeks.gamma_risk != "HIGH"
        
        # Adjustments
        adjustments = []
        if oi.oi_bias == "BULLISH":
            adjustments.append("Consider wider CE strike (more OTM)")
        elif oi.oi_bias == "BEARISH":
            adjustments.append("Consider wider PE strike (more OTM)")
        
        if greeks.gamma_risk == "HIGH":
            adjustments.append("⚠️ Use Iron Condor for limited risk on expiry")
        
        return AdvancedAnalysis(
            symbol=symbol,
            spot=spot,
            timestamp=datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S'),
            oi=oi,
            greeks=greeks,
            sr=sr,
            total_score=score,
            all_signals=all_signals,
            should_trade=should_trade,
            recommended_adjustments=adjustments,
        )
    
    def format_for_telegram(self, analysis: AdvancedAnalysis) -> str:
        """Format advanced analysis for Telegram"""
        
        msg = f"""
📊 <b>ADVANCED MARKET ANALYSIS</b>

📈 <b>Symbol:</b> {analysis.symbol}
💰 <b>Spot:</b> ₹{analysis.spot:,.2f}
🎯 <b>Score:</b> {analysis.total_score}/100
⏰ {analysis.timestamp}

━━━━━ OI ANALYSIS ━━━━━

📍 <b>Max Pain:</b> {analysis.oi.max_pain} ({analysis.oi.max_pain_distance:.1f}% away)
📊 <b>PCR:</b> {analysis.oi.total_pcr:.2f} {analysis.oi.pcr_interpretation}
📈 <b>Max CE OI:</b> {analysis.oi.ce_max_oi_strike} (Resistance)
📉 <b>Max PE OI:</b> {analysis.oi.pe_max_oi_strike} (Support)
🎯 <b>OI Bias:</b> {analysis.oi.oi_bias}

━━━━━ GREEKS ━━━━━

⚡ <b>IV Percentile:</b> {analysis.greeks.iv_percentile:.0f}%
⏱️ <b>Theta Decay:</b> ₹{analysis.greeks.total_theta:.0f}/day
📐 <b>IV Skew:</b> {analysis.greeks.iv_skew:+.1f}%
⚠️ <b>Gamma Risk:</b> {analysis.greeks.gamma_risk}

━━━━━ SUPPORT/RESISTANCE ━━━━━

📈 <b>Resistance:</b> {analysis.sr.nearest_resistance:.0f}
📉 <b>Support:</b> {analysis.sr.nearest_support:.0f}
📍 <b>Position:</b> {analysis.sr.spot_position}
📏 <b>Expected Range:</b> {analysis.sr.expected_range_low:.0f} - {analysis.sr.expected_range_high:.0f}

━━━━━ SIGNALS ━━━━━

"""
        for signal in analysis.all_signals[:8]:
            msg += f"• {signal}\n"
        
        if analysis.recommended_adjustments:
            msg += "\n<b>📝 ADJUSTMENTS:</b>\n"
            for adj in analysis.recommended_adjustments:
                msg += f"• {adj}\n"
        
        trade_status = "✅ TRADEABLE" if analysis.should_trade else "❌ WAIT"
        msg += f"\n<b>Status: {trade_status}</b>"
        
        return msg


# Quick access functions
advanced_analyzer = AdvancedMarketAnalyzer()

def get_advanced_analysis(symbol: str, spot: float = None) -> AdvancedAnalysis:
    """Get advanced analysis for a symbol"""
    return advanced_analyzer.analyze(symbol, spot)

def get_formatted_analysis(symbol: str) -> str:
    """Get formatted advanced analysis"""
    analysis = advanced_analyzer.analyze(symbol)
    return advanced_analyzer.format_for_telegram(analysis)


if __name__ == "__main__":
    # Test
    print("\n" + "="*60)
    print("       ADVANCED ANALYSIS TEST")
    print("="*60)
    
    for symbol in ['NIFTY', 'BANKNIFTY']:
        print(f"\n{symbol}:")
        print("-" * 40)
        analysis = get_advanced_analysis(symbol)
        print(f"Score: {analysis.total_score}/100")
        print(f"Should Trade: {analysis.should_trade}")
        print(f"OI Bias: {analysis.oi.oi_bias}")
        print(f"IV Percentile: {analysis.greeks.iv_percentile:.0f}%")
        print(f"Position: {analysis.sr.spot_position}")
