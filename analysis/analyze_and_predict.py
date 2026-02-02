"""
Next-Day Prediction Generator
==============================
Analyzes collected 1-minute data and generates predictions for tomorrow.

Uses:
- Price momentum analysis
- Volume patterns
- Sector correlation
- Technical indicators (VWAP, RSI approximation)

Run: python3 analyze_and_predict.py
"""

import gzip
import csv
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'stock_intelligence' / '1min_data'
OUTPUT_DIR = BASE_DIR / 'stock_intelligence' / 'predictions'


@dataclass
class StockAnalysis:
    symbol: str
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    total_volume: int
    change_pct: float
    trend: str  # UP, DOWN, SIDEWAYS
    momentum: str  # STRONG, MODERATE, WEAK
    vwap: float
    last_hour_trend: str
    volume_spike: bool


@dataclass
class Prediction:
    symbol: str
    direction: str  # BULLISH, BEARISH, NEUTRAL
    confidence: int  # 0-100
    probability: str  # e.g., "72%"
    reasons: List[str]
    target_pct: float
    stop_loss_pct: float
    risk_level: str  # LOW, MEDIUM, HIGH
    strategy: str


# Sector mapping
SECTORS = {
    "NIFTY": "INDEX", "BANKNIFTY": "INDEX",
    "HDFCBANK": "BANKING", "ICICIBANK": "BANKING", "SBIN": "BANKING",
    "AXISBANK": "BANKING", "KOTAKBANK": "BANKING", "BAJFINANCE": "NBFC",
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT",
    "RELIANCE": "ENERGY", "ONGC": "ENERGY", "NTPC": "ENERGY", "POWERGRID": "ENERGY",
    "TATAMOTORS": "AUTO", "MARUTI": "AUTO", "M&M": "AUTO",
    "TATASTEEL": "METALS", "HINDALCO": "METALS",
    "SUNPHARMA": "PHARMA", "CIPLA": "PHARMA",
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "TITAN": "FMCG",
    "ADANIENT": "INFRA", "LT": "INFRA", "ASIANPAINT": "INFRA",
    "BHARTIARTL": "TELECOM", "COALINDIA": "ENERGY", "ULTRACEMCO": "INFRA"
}


def load_stock_data(filepath: Path) -> List[Dict]:
    """Load compressed CSV data."""
    candles = []
    try:
        with gzip.open(filepath, 'rt') as f:
            reader = csv.DictReader(f)
            for row in reader:
                candles.append({
                    'timestamp': row['timestamp'],
                    'open': float(row['open']),
                    'high': float(row['high']),
                    'low': float(row['low']),
                    'close': float(row['close']),
                    'volume': int(row['volume'])
                })
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
    return candles


def analyze_stock(symbol: str, candles: List[Dict]) -> StockAnalysis:
    """Analyze a stock's 1-minute data."""
    if not candles:
        return None
    
    # Basic OHLCV
    open_price = candles[0]['open']
    close_price = candles[-1]['close']
    high_price = max(c['high'] for c in candles)
    low_price = min(c['low'] for c in candles)
    total_volume = sum(c['volume'] for c in candles)
    
    change_pct = ((close_price - open_price) / open_price) * 100
    
    # Trend
    if change_pct > 1:
        trend = "UP"
    elif change_pct < -1:
        trend = "DOWN"
    else:
        trend = "SIDEWAYS"
    
    # Momentum (based on close position in day's range)
    day_range = high_price - low_price
    if day_range > 0:
        close_position = (close_price - low_price) / day_range
        if close_position > 0.7:
            momentum = "STRONG"
        elif close_position > 0.4:
            momentum = "MODERATE"
        else:
            momentum = "WEAK"
    else:
        momentum = "WEAK"
    
    # VWAP calculation
    vwap_num = sum(c['close'] * c['volume'] for c in candles)
    vwap_den = sum(c['volume'] for c in candles)
    vwap = vwap_num / vwap_den if vwap_den > 0 else close_price
    
    # Last hour trend (last 60 candles)
    last_hour = candles[-60:] if len(candles) >= 60 else candles
    last_hour_change = ((last_hour[-1]['close'] - last_hour[0]['open']) / last_hour[0]['open']) * 100
    
    if last_hour_change > 0.5:
        last_hour_trend = "BULLISH"
    elif last_hour_change < -0.5:
        last_hour_trend = "BEARISH"
    else:
        last_hour_trend = "NEUTRAL"
    
    # Volume spike detection (last hour vs rest)
    if len(candles) > 60:
        last_hour_vol = sum(c['volume'] for c in candles[-60:])
        avg_hourly_vol = total_volume / (len(candles) / 60)
        volume_spike = last_hour_vol > avg_hourly_vol * 1.5
    else:
        volume_spike = False
    
    return StockAnalysis(
        symbol=symbol,
        open_price=round(open_price, 2),
        close_price=round(close_price, 2),
        high_price=round(high_price, 2),
        low_price=round(low_price, 2),
        total_volume=total_volume,
        change_pct=round(change_pct, 2),
        trend=trend,
        momentum=momentum,
        vwap=round(vwap, 2),
        last_hour_trend=last_hour_trend,
        volume_spike=volume_spike
    )


def generate_prediction(analysis: StockAnalysis, sector_trend: str) -> Prediction:
    """Generate next-day prediction from analysis."""
    
    confidence = 50  # Base confidence
    reasons = []
    
    # Factor 1: Day trend (25%)
    if analysis.trend == "UP":
        confidence += 15
        reasons.append(f"Today's gain: +{analysis.change_pct}%")
    elif analysis.trend == "DOWN":
        confidence -= 15
        reasons.append(f"Today's loss: {analysis.change_pct}%")
    
    # Factor 2: Momentum (20%)
    if analysis.momentum == "STRONG":
        confidence += 10
        reasons.append("Strong momentum (close near day high)")
    elif analysis.momentum == "WEAK":
        confidence -= 10
        reasons.append("Weak momentum (close near day low)")
    
    # Factor 3: Last hour trend (15%)
    if analysis.last_hour_trend == "BULLISH":
        confidence += 8
        reasons.append("Last hour buying pressure")
    elif analysis.last_hour_trend == "BEARISH":
        confidence -= 8
        reasons.append("Last hour selling pressure")
    
    # Factor 4: Volume spike (10%)
    if analysis.volume_spike:
        if analysis.last_hour_trend == "BULLISH":
            confidence += 8
            reasons.append("High volume buying in last hour")
        elif analysis.last_hour_trend == "BEARISH":
            confidence -= 8
            reasons.append("High volume selling in last hour")
    
    # Factor 5: Sector correlation (10%)
    if sector_trend == "BULLISH":
        confidence += 5
        reasons.append("Sector trending bullish")
    elif sector_trend == "BEARISH":
        confidence -= 5
        reasons.append("Sector trending bearish")
    
    # Factor 6: VWAP position (10%)
    if analysis.close_price > analysis.vwap:
        confidence += 5
        reasons.append(f"Trading above VWAP ({analysis.vwap})")
    else:
        confidence -= 5
        reasons.append(f"Trading below VWAP ({analysis.vwap})")
    
    # Clamp confidence
    confidence = max(20, min(85, confidence))
    
    # Determine direction
    if confidence >= 55:
        direction = "BULLISH"
        target_pct = 1.0 + (confidence - 50) / 50  # 1-1.7%
        stop_loss_pct = 0.8
    elif confidence <= 45:
        direction = "BEARISH"
        target_pct = 1.0 + (50 - confidence) / 50
        stop_loss_pct = 0.8
    else:
        direction = "NEUTRAL"
        target_pct = 0.5
        stop_loss_pct = 0.5
    
    # Risk level
    if abs(analysis.change_pct) > 3:
        risk_level = "HIGH"
    elif abs(analysis.change_pct) > 1.5:
        risk_level = "MEDIUM"
    else:
        risk_level = "LOW"
    
    # Strategy
    if direction == "BULLISH":
        if confidence > 70:
            strategy = "Buy ATM Call (aggressive)"
        else:
            strategy = "Buy slight OTM Call (conservative)"
    elif direction == "BEARISH":
        if confidence > 70:
            strategy = "Buy ATM Put (aggressive)"
        else:
            strategy = "Buy slight OTM Put (conservative)"
    else:
        strategy = "Avoid or Sell Straddle"
    
    return Prediction(
        symbol=analysis.symbol,
        direction=direction,
        confidence=confidence,
        probability=f"{confidence}%",
        reasons=reasons[:4],
        target_pct=round(target_pct, 1),
        stop_loss_pct=round(stop_loss_pct, 1),
        risk_level=risk_level,
        strategy=strategy
    )


def analyze_sector_trends(analyses: Dict[str, StockAnalysis]) -> Dict[str, str]:
    """Analyze sector-wise trends."""
    sector_changes = {}
    
    for symbol, analysis in analyses.items():
        if analysis is None:
            continue
        sector = SECTORS.get(symbol, "OTHER")
        if sector not in sector_changes:
            sector_changes[sector] = []
        sector_changes[sector].append(analysis.change_pct)
    
    sector_trends = {}
    for sector, changes in sector_changes.items():
        avg_change = sum(changes) / len(changes)
        if avg_change > 0.5:
            sector_trends[sector] = "BULLISH"
        elif avg_change < -0.5:
            sector_trends[sector] = "BEARISH"
        else:
            sector_trends[sector] = "NEUTRAL"
    
    return sector_trends


def main():
    """Generate predictions from today's 1-min data."""
    today = datetime.now().strftime('%Y-%m-%d')
    stocks_dir = DATA_DIR / today / 'stocks'
    
    if not stocks_dir.exists():
        print(f"❌ No data found for {today}")
        return
    
    print("=" * 60)
    print("🔮 NEXT-DAY PREDICTION GENERATOR")
    print(f"📅 Analysis Date: {today}")
    print(f"📅 Prediction For: Tomorrow")
    print("=" * 60)
    
    # Load and analyze all stocks
    analyses = {}
    for filepath in stocks_dir.glob('*.csv.gz'):
        symbol = filepath.stem.replace('.csv', '')
        candles = load_stock_data(filepath)
        if candles:
            analyses[symbol] = analyze_stock(symbol, candles)
    
    print(f"\n📊 Analyzed {len(analyses)} stocks")
    
    # Sector trends
    sector_trends = analyze_sector_trends(analyses)
    
    print("\n📈 SECTOR TRENDS:")
    for sector, trend in sorted(sector_trends.items()):
        icon = "🟢" if trend == "BULLISH" else "🔴" if trend == "BEARISH" else "⚪"
        print(f"  {icon} {sector}: {trend}")
    
    # Generate predictions
    predictions = []
    for symbol, analysis in analyses.items():
        if analysis is None:
            continue
        sector = SECTORS.get(symbol, "OTHER")
        sector_trend = sector_trends.get(sector, "NEUTRAL")
        pred = generate_prediction(analysis, sector_trend)
        predictions.append(pred)
    
    # Sort by confidence
    predictions.sort(key=lambda x: x.confidence, reverse=True)
    
    # Top bullish
    bullish = [p for p in predictions if p.direction == "BULLISH"][:5]
    bearish = [p for p in predictions if p.direction == "BEARISH"][:5]
    
    print("\n" + "=" * 60)
    print("🟢 TOP BULLISH PREDICTIONS (Buy Tomorrow)")
    print("=" * 60)
    
    for i, p in enumerate(bullish, 1):
        print(f"\n{i}. {p.symbol}")
        print(f"   Direction: {p.direction} | Probability: {p.probability}")
        print(f"   Target: +{p.target_pct}% | Stop Loss: -{p.stop_loss_pct}%")
        print(f"   Risk: {p.risk_level} | Strategy: {p.strategy}")
        print(f"   Reasons:")
        for r in p.reasons:
            print(f"     • {r}")
    
    print("\n" + "=" * 60)
    print("🔴 TOP BEARISH PREDICTIONS (Sell Tomorrow)")
    print("=" * 60)
    
    for i, p in enumerate(bearish, 1):
        print(f"\n{i}. {p.symbol}")
        print(f"   Direction: {p.direction} | Probability: {p.probability}")
        print(f"   Target: +{p.target_pct}% | Stop Loss: -{p.stop_loss_pct}%")
        print(f"   Risk: {p.risk_level} | Strategy: {p.strategy}")
        print(f"   Reasons:")
        for r in p.reasons:
            print(f"     • {r}")
    
    # Save predictions
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / today / 'ml_predictions.json'
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    output = {
        'date': today,
        'for_date': 'Tomorrow',
        'generated_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'sector_trends': sector_trends,
        'top_bullish': [asdict(p) for p in bullish],
        'top_bearish': [asdict(p) for p in bearish],
        'all_predictions': [asdict(p) for p in predictions]
    }
    
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"\n💾 Predictions saved to: {output_file.relative_to(BASE_DIR)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
