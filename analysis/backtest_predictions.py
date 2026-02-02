"""
Prediction Backtester
======================
Tests prediction accuracy using historical data.

Uses existing NIFTY/BANKNIFTY daily data to:
1. Generate predictions based on Day N
2. Check if prediction was correct on Day N+1
3. Calculate accuracy stats

Run: python3 backtest_predictions.py
"""

import csv
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
from dataclasses import dataclass

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / 'data' / 'index_ohlcv'


@dataclass
class DayData:
    date: str
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    change_pct: float
    trend: str
    momentum: str


@dataclass
class BacktestResult:
    prediction_date: str
    symbol: str
    predicted_direction: str
    confidence: int
    actual_direction: str
    actual_change_pct: float
    was_correct: bool
    profit_if_traded: float


def load_daily_data(filepath: Path) -> List[Dict]:
    """Load daily 1-min data and compute OHLC."""
    candles = []
    try:
        with open(filepath, 'r') as f:
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


def compute_day_stats(candles: List[Dict], date_str: str) -> DayData:
    """Compute daily stats from 1-min candles."""
    if not candles:
        return None
    
    open_price = candles[0]['open']
    close_price = candles[-1]['close']
    high_price = max(c['high'] for c in candles)
    low_price = min(c['low'] for c in candles)
    
    change_pct = ((close_price - open_price) / open_price) * 100
    
    if change_pct > 0.5:
        trend = "UP"
    elif change_pct < -0.5:
        trend = "DOWN"
    else:
        trend = "SIDEWAYS"
    
    day_range = high_price - low_price
    if day_range > 0:
        close_pos = (close_price - low_price) / day_range
        if close_pos > 0.7:
            momentum = "STRONG"
        elif close_pos > 0.4:
            momentum = "MODERATE"
        else:
            momentum = "WEAK"
    else:
        momentum = "WEAK"
    
    return DayData(
        date=date_str,
        open_price=round(open_price, 2),
        close_price=round(close_price, 2),
        high_price=round(high_price, 2),
        low_price=round(low_price, 2),
        change_pct=round(change_pct, 2),
        trend=trend,
        momentum=momentum
    )


def predict_next_day(today: DayData) -> Tuple[str, int]:
    """Generate prediction for next day based on today's data."""
    confidence = 50
    
    # Trend factor
    if today.trend == "UP":
        confidence += 15
    elif today.trend == "DOWN":
        confidence -= 15
    
    # Momentum factor
    if today.momentum == "STRONG":
        confidence += 12
    elif today.momentum == "WEAK":
        confidence -= 12
    
    # Change magnitude
    if abs(today.change_pct) > 1:
        if today.change_pct > 0:
            confidence += 8
        else:
            confidence -= 8
    
    confidence = max(25, min(85, confidence))
    
    if confidence >= 55:
        return ("BULLISH", confidence)
    elif confidence <= 45:
        return ("BEARISH", confidence)
    else:
        return ("NEUTRAL", confidence)


def run_backtest(symbol: str = "NIFTY") -> List[BacktestResult]:
    """Run backtest for a symbol."""
    symbol_dir = DATA_DIR / "2026" / "Jan" / symbol
    
    if not symbol_dir.exists():
        print(f"No data found for {symbol}")
        return []
    
    # Load all available days
    day_files = sorted(symbol_dir.glob("*.csv"))
    
    if len(day_files) < 2:
        print(f"Need at least 2 days of data, found {len(day_files)}")
        return []
    
    # Compute stats for each day
    days_data = []
    for filepath in day_files:
        date_str = filepath.stem  # e.g., "2026-01-16"
        candles = load_daily_data(filepath)
        day_data = compute_day_stats(candles, date_str)
        if day_data:
            days_data.append(day_data)
    
    print(f"\n📅 Found {len(days_data)} days of data for {symbol}")
    
    # Run predictions
    results = []
    
    for i in range(len(days_data) - 1):
        today = days_data[i]
        tomorrow = days_data[i + 1]
        
        # Generate prediction based on today
        predicted_dir, confidence = predict_next_day(today)
        
        # Check actual result
        if tomorrow.change_pct > 0.3:
            actual_dir = "BULLISH"
        elif tomorrow.change_pct < -0.3:
            actual_dir = "BEARISH"
        else:
            actual_dir = "NEUTRAL"
        
        # Check if correct
        was_correct = (predicted_dir == actual_dir) or (
            predicted_dir == "NEUTRAL" and abs(tomorrow.change_pct) < 0.5
        )
        
        # Calculate profit (simplified)
        if predicted_dir == "BULLISH":
            profit = tomorrow.change_pct if tomorrow.change_pct > 0 else -0.5
        elif predicted_dir == "BEARISH":
            profit = -tomorrow.change_pct if tomorrow.change_pct < 0 else -0.5
        else:
            profit = 0
        
        results.append(BacktestResult(
            prediction_date=today.date,
            symbol=symbol,
            predicted_direction=predicted_dir,
            confidence=confidence,
            actual_direction=actual_dir,
            actual_change_pct=tomorrow.change_pct,
            was_correct=was_correct,
            profit_if_traded=round(profit, 2)
        ))
    
    return results


def main():
    """Run full backtest."""
    print("=" * 60)
    print("🔍 PREDICTION BACKTESTER")
    print("Testing prediction accuracy using historical data")
    print("=" * 60)
    
    all_results = []
    
    for symbol in ["NIFTY", "BANKNIFTY"]:
        results = run_backtest(symbol)
        all_results.extend(results)
        
        if not results:
            continue
        
        # Print results
        print(f"\n{'='*60}")
        print(f"📊 {symbol} BACKTEST RESULTS")
        print(f"{'='*60}")
        
        correct = sum(1 for r in results if r.was_correct)
        total = len(results)
        accuracy = (correct / total) * 100 if total > 0 else 0
        
        total_profit = sum(r.profit_if_traded for r in results)
        
        print(f"\n📈 Accuracy: {correct}/{total} = {accuracy:.1f}%")
        print(f"💰 Total Profit (if traded): {total_profit:+.2f}%")
        
        print(f"\n📋 Detailed Results:")
        print("-" * 60)
        print(f"{'Date':<12} {'Predicted':<10} {'Conf':<6} {'Actual':<10} {'Change':<8} {'Result'}")
        print("-" * 60)
        
        for r in results:
            result_icon = "✅" if r.was_correct else "❌"
            print(f"{r.prediction_date:<12} {r.predicted_direction:<10} {r.confidence}%    {r.actual_direction:<10} {r.actual_change_pct:>+6.2f}%  {result_icon}")
    
    # Overall stats
    if all_results:
        print("\n" + "=" * 60)
        print("📊 OVERALL SUMMARY")
        print("=" * 60)
        
        correct = sum(1 for r in all_results if r.was_correct)
        total = len(all_results)
        accuracy = (correct / total) * 100 if total > 0 else 0
        total_profit = sum(r.profit_if_traded for r in all_results)
        
        print(f"\n🎯 Total Predictions: {total}")
        print(f"✅ Correct: {correct}")
        print(f"❌ Wrong: {total - correct}")
        print(f"📈 Accuracy: {accuracy:.1f}%")
        print(f"💰 Total Profit: {total_profit:+.2f}%")
        
        # By confidence level
        high_conf = [r for r in all_results if r.confidence >= 65]
        if high_conf:
            high_correct = sum(1 for r in high_conf if r.was_correct)
            high_acc = (high_correct / len(high_conf)) * 100
            print(f"\n📊 High Confidence (≥65%) Predictions:")
            print(f"   Total: {len(high_conf)}, Correct: {high_correct}, Accuracy: {high_acc:.1f}%")
    
    print("\n" + "=" * 60)
    print("✅ BACKTEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
