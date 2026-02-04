"""
Prediction Verification Script
==============================
Verifies ML predictions from Jan 21, 2026 against actual market data on Jan 22, 2026.
Shows what happened after predictions and accuracy analysis.
"""

import json
import csv
import gzip
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

BASE_DIR = Path(__file__).parent.parent
PREDICTIONS_DIR = BASE_DIR / "stock_intelligence" / "predictions"
OHLCV_DIR = BASE_DIR / "data" / "index_ohlcv"
STOCK_DATA_DIR = BASE_DIR / "stock_intelligence" / "1min_data"


@dataclass
class PredictionResult:
    symbol: str
    prediction_date: str
    direction: str
    confidence: int
    target_pct: float
    stop_loss_pct: float
    reasons: List[str]
    strategy: str
    # Actual results
    actual_open: Optional[float] = None
    actual_close: Optional[float] = None
    actual_high: Optional[float] = None
    actual_low: Optional[float] = None
    actual_change_pct: Optional[float] = None
    was_correct: Optional[bool] = None
    target_hit: Optional[bool] = None
    sl_hit: Optional[bool] = None
    pnl_pct: Optional[float] = None


def load_predictions(date: str) -> Dict:
    """Load ML predictions for a specific date."""
    pred_file = PREDICTIONS_DIR / date / "ml_predictions.json"
    if pred_file.exists():
        with open(pred_file, 'r') as f:
            return json.load(f)
    return {}


def load_index_data(symbol: str, date: str) -> List[Dict]:
    """Load 1-min OHLCV data for NIFTY/BANKNIFTY."""
    # Parse date to get month
    dt = datetime.strptime(date, "%Y-%m-%d")
    month = dt.strftime("%b")  # Jan, Feb, etc.
    
    filepath = OHLCV_DIR / "2026" / month / symbol / f"{date}.csv"
    
    candles = []
    if filepath.exists():
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
    return candles


def load_stock_data(symbol: str, date: str) -> List[Dict]:
    """Load 1-min data for individual stocks from gzipped files."""
    filepath = STOCK_DATA_DIR / date / "stocks" / f"{symbol}.csv.gz"
    
    candles = []
    if filepath.exists():
        try:
            with gzip.open(filepath, 'rt') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    candles.append({
                        'timestamp': row.get('timestamp', row.get('datetime', '')),
                        'open': float(row['open']),
                        'high': float(row['high']),
                        'low': float(row['low']),
                        'close': float(row['close']),
                        'volume': int(row.get('volume', 0))
                    })
        except Exception as e:
            print(f"Error loading {symbol}: {e}")
    return candles


def compute_day_stats(candles: List[Dict]) -> Dict:
    """Compute OHLC stats for a day."""
    if not candles:
        return None
    
    return {
        'open': candles[0]['open'],
        'close': candles[-1]['close'],
        'high': max(c['high'] for c in candles),
        'low': min(c['low'] for c in candles),
        'change_pct': ((candles[-1]['close'] - candles[0]['open']) / candles[0]['open']) * 100
    }


def verify_single_prediction(pred: Dict, next_day_data: Dict) -> PredictionResult:
    """Verify a single prediction against actual data."""
    result = PredictionResult(
        symbol=pred['symbol'],
        prediction_date=pred.get('prediction_date', '2026-01-21'),
        direction=pred['direction'],
        confidence=pred['confidence'],
        target_pct=pred['target_pct'],
        stop_loss_pct=pred['stop_loss_pct'],
        reasons=pred['reasons'],
        strategy=pred['strategy']
    )
    
    if next_day_data:
        result.actual_open = round(next_day_data['open'], 2)
        result.actual_close = round(next_day_data['close'], 2)
        result.actual_high = round(next_day_data['high'], 2)
        result.actual_low = round(next_day_data['low'], 2)
        result.actual_change_pct = round(next_day_data['change_pct'], 2)
        
        # Check if prediction was correct
        if pred['direction'] == 'BULLISH':
            result.was_correct = next_day_data['change_pct'] > 0
            # Check if target was hit (intraday high reached target)
            max_gain = ((next_day_data['high'] - next_day_data['open']) / next_day_data['open']) * 100
            max_loss = ((next_day_data['low'] - next_day_data['open']) / next_day_data['open']) * 100
            result.target_hit = max_gain >= pred['target_pct']
            result.sl_hit = max_loss <= -pred['stop_loss_pct']
            # Calculate PnL
            if result.sl_hit and not result.target_hit:
                result.pnl_pct = -pred['stop_loss_pct']
            elif result.target_hit:
                result.pnl_pct = pred['target_pct']
            else:
                result.pnl_pct = next_day_data['change_pct']
        else:  # BEARISH
            result.was_correct = next_day_data['change_pct'] < 0
            max_gain = ((next_day_data['open'] - next_day_data['low']) / next_day_data['open']) * 100
            max_loss = ((next_day_data['high'] - next_day_data['open']) / next_day_data['open']) * 100
            result.target_hit = max_gain >= pred['target_pct']
            result.sl_hit = max_loss >= pred['stop_loss_pct']
            if result.sl_hit and not result.target_hit:
                result.pnl_pct = -pred['stop_loss_pct']
            elif result.target_hit:
                result.pnl_pct = pred['target_pct']
            else:
                result.pnl_pct = -next_day_data['change_pct']
    
    return result


def main():
    """Run prediction verification."""
    print("=" * 80)
    print("🔍 STOCK PREDICTION VERIFICATION REPORT")
    print("=" * 80)
    print(f"\n📅 Predictions from: 2026-01-21 (for next day: 2026-01-22)\n")
    
    # Load predictions from Jan 21
    predictions = load_predictions("2026-01-21")
    
    if not predictions:
        print("❌ No predictions found for 2026-01-21")
        return
    
    print(f"📊 Total Predictions: {len(predictions.get('all_predictions', []))}")
    print(f"📈 Top Bullish: {len(predictions.get('top_bullish', []))}")
    print(f"📉 Top Bearish: {len(predictions.get('top_bearish', []))}")
    
    # First check index predictions (NIFTY, BANKNIFTY)
    print("\n" + "=" * 80)
    print("📊 INDEX PREDICTIONS VERIFICATION")
    print("=" * 80)
    
    for symbol in ['NIFTY', 'BANKNIFTY']:
        candles = load_index_data(symbol, "2026-01-22")
        if candles:
            stats = compute_day_stats(candles)
            # Find prediction for this symbol
            pred = next((p for p in predictions.get('all_predictions', []) if p['symbol'] == symbol), None)
            if pred:
                result = verify_single_prediction(pred, stats)
                print(f"\n{'='*60}")
                print(f"📌 {symbol}")
                print(f"{'='*60}")
                print(f"Prediction: {result.direction} ({result.confidence}% confidence)")
                print(f"Reasons:")
                for r in result.reasons:
                    print(f"  • {r}")
                print(f"\n📈 Actual Next Day (2026-01-22):")
                print(f"  Open:  {result.actual_open:>10.2f}")
                print(f"  High:  {result.actual_high:>10.2f}")
                print(f"  Low:   {result.actual_low:>10.2f}")
                print(f"  Close: {result.actual_close:>10.2f}")
                print(f"  Change: {result.actual_change_pct:>+.2f}%")
                print(f"\n{'✅ CORRECT' if result.was_correct else '❌ WRONG'} (Target Hit: {'Yes' if result.target_hit else 'No'}, SL Hit: {'Yes' if result.sl_hit else 'No'})")
                print(f"PnL if traded: {result.pnl_pct:+.2f}%")
        else:
            print(f"\n⚠️ No data found for {symbol} on 2026-01-22")
    
    # Verify all predictions with available data
    print("\n" + "=" * 80)
    print("📊 ALL PREDICTIONS SUMMARY")
    print("=" * 80)
    
    results = []
    all_preds = predictions.get('all_predictions', [])
    
    for pred in all_preds:
        symbol = pred['symbol']
        # Try index data first
        if symbol in ['NIFTY', 'BANKNIFTY']:
            candles = load_index_data(symbol, "2026-01-22")
        else:
            candles = load_stock_data(symbol, "2026-01-22")
        
        stats = compute_day_stats(candles) if candles else None
        result = verify_single_prediction(pred, stats)
        results.append(result)
    
    # Print summary table
    print(f"\n{'Symbol':<12} {'Pred':<8} {'Conf':>5} {'Actual':>8} {'Result':<8} {'PnL':>8}")
    print("-" * 60)
    
    verified_results = [r for r in results if r.actual_change_pct is not None]
    unverified = [r for r in results if r.actual_change_pct is None]
    
    for r in sorted(verified_results, key=lambda x: x.confidence, reverse=True):
        status = "✅" if r.was_correct else "❌"
        pnl_str = f"{r.pnl_pct:+.2f}%" if r.pnl_pct else "N/A"
        actual_str = f"{r.actual_change_pct:+.2f}%" if r.actual_change_pct else "N/A"
        print(f"{r.symbol:<12} {r.direction:<8} {r.confidence:>4}% {actual_str:>8} {status:<8} {pnl_str:>8}")
    
    # Overall stats
    if verified_results:
        print("\n" + "=" * 80)
        print("📊 PERFORMANCE STATISTICS")
        print("=" * 80)
        
        correct = sum(1 for r in verified_results if r.was_correct)
        total = len(verified_results)
        accuracy = (correct / total) * 100 if total > 0 else 0
        
        bullish = [r for r in verified_results if r.direction == 'BULLISH']
        bearish = [r for r in verified_results if r.direction == 'BEARISH']
        
        bullish_correct = sum(1 for r in bullish if r.was_correct)
        bearish_correct = sum(1 for r in bearish if r.was_correct)
        
        total_pnl = sum(r.pnl_pct for r in verified_results if r.pnl_pct)
        avg_pnl = total_pnl / len(verified_results) if verified_results else 0
        
        targets_hit = sum(1 for r in verified_results if r.target_hit)
        sls_hit = sum(1 for r in verified_results if r.sl_hit)
        
        print(f"\n🎯 Overall Accuracy: {correct}/{total} = {accuracy:.1f}%")
        print(f"📈 Bullish Predictions: {bullish_correct}/{len(bullish)} correct ({(bullish_correct/len(bullish)*100) if bullish else 0:.1f}%)")
        print(f"📉 Bearish Predictions: {bearish_correct}/{len(bearish)} correct ({(bearish_correct/len(bearish)*100) if bearish else 0:.1f}%)")
        print(f"\n💰 Total PnL (if traded all): {total_pnl:+.2f}%")
        print(f"📊 Average PnL per trade: {avg_pnl:+.2f}%")
        print(f"🎯 Targets Hit: {targets_hit}/{total}")
        print(f"🛑 Stop Losses Hit: {sls_hit}/{total}")
        
        # High confidence predictions
        high_conf = [r for r in verified_results if r.confidence >= 80]
        if high_conf:
            hc_correct = sum(1 for r in high_conf if r.was_correct)
            hc_pnl = sum(r.pnl_pct for r in high_conf if r.pnl_pct)
            print(f"\n🌟 High Confidence (≥80%) Predictions:")
            print(f"   Accuracy: {hc_correct}/{len(high_conf)} = {(hc_correct/len(high_conf)*100):.1f}%")
            print(f"   Total PnL: {hc_pnl:+.2f}%")
    
    if unverified:
        print(f"\n⚠️ {len(unverified)} predictions could not be verified (no next-day data available)")
        print("Unverified symbols: " + ", ".join(r.symbol for r in unverified[:10]))
    
    # Show prediction methodology
    print("\n" + "=" * 80)
    print("📖 PREDICTION METHODOLOGY")
    print("=" * 80)
    print("""
The prediction system uses multiple signals to generate next-day predictions:

1️⃣ MOMENTUM ANALYSIS
   • Analyzes today's price change percentage
   • Checks if close is near day high (bullish) or low (bearish)
   • Strong momentum = higher confidence

2️⃣ VWAP ANALYSIS
   • If price trading above VWAP = bullish signal
   • If price trading below VWAP = bearish signal

3️⃣ LAST HOUR ANALYSIS
   • Buying pressure in last hour = bullish
   • Selling pressure in last hour = bearish

4️⃣ SECTOR TRENDS
   • Sector analysis (Banking, IT, Auto, etc.)
   • Strong sector = individual stocks likely to follow

5️⃣ CONFIDENCE SCORING
   • Multiple confirming signals = higher confidence
   • Conflicting signals = lower confidence
   • Range: 20% (low) to 85% (high)

6️⃣ RISK MANAGEMENT
   • Target: 1.1% to 1.7% based on confidence
   • Stop Loss: 0.8% (fixed)
   • Risk:Reward = 1:1.4 to 1:2.1
""")
    
    print("\n" + "=" * 80)
    print("✅ VERIFICATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
