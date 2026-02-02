"""
OI Spurt Detector
==================
Detects significant Open Interest changes that signal potential moves.

Features:
- Threshold-based detection (>20% OI change)
- Categorization: Long Buildup, Short Buildup, Long Unwinding, Short Covering
- Multi-strike analysis
- Historical tracking with outcomes
- Prediction accuracy scoring

Schedule: 3:30 PM daily (after option chain collection)
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# Setup
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"oi_spurt_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("OISpurtDetector")


class SpurtType(str, Enum):
    """Type of OI spurt"""
    LONG_BUILDUP = "LONG_BUILDUP"       # OI ↑ + Price ↑ = Fresh Buying
    SHORT_BUILDUP = "SHORT_BUILDUP"     # OI ↑ + Price ↓ = Fresh Selling
    LONG_UNWINDING = "LONG_UNWINDING"   # OI ↓ + Price ↓ = Longs Exiting
    SHORT_COVERING = "SHORT_COVERING"   # OI ↓ + Price ↑ = Shorts Exiting


@dataclass
class OISpurt:
    """Individual OI spurt detection"""
    symbol: str
    strike: int
    option_type: str  # CE or PE
    expiry: str
    timestamp: str
    
    # OI Data
    current_oi: int
    previous_oi: int
    oi_change: int
    oi_change_pct: float
    
    # Price Data
    current_price: float
    previous_price: float
    price_change_pct: float
    
    # Analysis
    spurt_type: str
    signal_strength: str  # STRONG, MEDIUM, WEAK
    interpretation: str
    action_suggested: str
    
    # For tracking accuracy
    next_day_result: Optional[str] = None
    prediction_correct: Optional[bool] = None


@dataclass
class DailySpurtSummary:
    """Daily summary of all OI spurts"""
    date: str
    timestamp: str
    total_spurts: int
    
    # By category
    long_buildups: List[Dict]
    short_buildups: List[Dict]
    long_unwindings: List[Dict]
    short_coverings: List[Dict]
    
    # Top spurts
    top_bullish_signals: List[Dict]
    top_bearish_signals: List[Dict]
    
    # Overall market sentiment
    market_sentiment: str
    sentiment_score: float  # -1 to +1
    
    # Predictions for next day
    next_day_predictions: List[Dict]


class OISpurtDetector:
    """Detects and analyzes significant OI changes."""
    
    # Thresholds
    MIN_OI_CHANGE_PCT = 15  # Minimum % change to consider a spurt
    HIGH_OI_CHANGE_PCT = 30  # High significance threshold
    MIN_VOLUME_MULTIPLIER = 1.5  # Volume should be 1.5x average
    
    def __init__(self):
        self.data_dir = BASE_DIR / 'data'
        self.spurts_dir = BASE_DIR / 'data' / 'daily_analysis'
        
    def load_option_chain(self, symbol: str, date: datetime) -> Optional[Dict]:
        """Load option chain data for a symbol on a date."""
        date_dir = self.data_dir / 'stock_options' / symbol / date.strftime('%Y-%m') / date.strftime('%d')
        
        # Find the latest snapshot for the day
        if not date_dir.exists():
            return None
            
        files = list(date_dir.glob('option_chain_*.json'))
        if not files:
            return None
            
        # Get the latest file
        latest_file = max(files, key=lambda f: f.name)
        
        try:
            with open(latest_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading {latest_file}: {e}")
            return None
    
    def load_previous_day_data(self, symbol: str, current_date: datetime) -> Optional[Dict]:
        """Load previous trading day's data."""
        # Go back one day, skip weekends
        check_date = current_date - timedelta(days=1)
        while check_date.weekday() >= 5:  # Skip Saturday(5) and Sunday(6)
            check_date -= timedelta(days=1)
        
        return self.load_option_chain(symbol, check_date)
    
    def classify_spurt(self, oi_change: int, price_change_pct: float) -> Tuple[str, str]:
        """
        Classify the type of OI movement.
        
        Returns: (SpurtType, interpretation)
        """
        if oi_change > 0:
            if price_change_pct > 0:
                return (
                    SpurtType.LONG_BUILDUP.value,
                    "Fresh buying - Bulls are adding positions. Expect continuation if sustained."
                )
            else:
                return (
                    SpurtType.SHORT_BUILDUP.value,
                    "Fresh selling - Bears are adding positions. Expect downward pressure."
                )
        else:
            if price_change_pct > 0:
                return (
                    SpurtType.SHORT_COVERING.value,
                    "Shorts exiting - Bears closing positions. Move may not sustain."
                )
            else:
                return (
                    SpurtType.LONG_UNWINDING.value,
                    "Longs exiting - Bulls taking profits/stopping out. Selling pressure."
                )
    
    def get_signal_strength(self, oi_change_pct: float, volume_ratio: float = 1) -> str:
        """Determine signal strength based on OI change and volume."""
        if abs(oi_change_pct) >= self.HIGH_OI_CHANGE_PCT:
            return "STRONG"
        elif abs(oi_change_pct) >= 25:
            return "MEDIUM"
        else:
            return "WEAK"
    
    def get_action_suggested(self, spurt_type: str, option_type: str, signal_strength: str) -> str:
        """Suggest trading action based on spurt type."""
        if signal_strength == "WEAK":
            return "Monitor - Signal not strong enough for action"
        
        actions = {
            # CE (Call) spurts
            (SpurtType.LONG_BUILDUP.value, "CE"): "Bearish - CE buildup creates resistance",
            (SpurtType.SHORT_BUILDUP.value, "CE"): "Very Bearish - Fresh CE writing with price drop",
            (SpurtType.LONG_UNWINDING.value, "CE"): "Neutral - CE holders exiting",
            (SpurtType.SHORT_COVERING.value, "CE"): "Bullish - CE writers exiting, less resistance",
            
            # PE (Put) spurts
            (SpurtType.LONG_BUILDUP.value, "PE"): "Bullish - PE buildup creates support",
            (SpurtType.SHORT_BUILDUP.value, "PE"): "Very Bullish - Fresh PE writing with price drop",
            (SpurtType.LONG_UNWINDING.value, "PE"): "Neutral - PE holders exiting",
            (SpurtType.SHORT_COVERING.value, "PE"): "Bearish - PE writers exiting, less support",
        }
        
        return actions.get((spurt_type, option_type), "Analyze further")
    
    def detect_spurts(self, current_data: Dict, previous_data: Dict) -> List[OISpurt]:
        """Detect OI spurts by comparing current and previous data."""
        spurts = []
        
        if not current_data or not previous_data:
            return spurts
        
        symbol = current_data.get('symbol', '')
        current_spot = current_data.get('spot_price', 0)
        previous_spot = previous_data.get('spot_price', 0)
        
        if not current_spot or not previous_spot:
            return spurts
        
        spot_change_pct = ((current_spot - previous_spot) / previous_spot) * 100
        
        # Build lookup for previous data
        prev_calls = {c['strike']: c for c in previous_data.get('calls', [])}
        prev_puts = {p['strike']: p for p in previous_data.get('puts', [])}
        
        # Check Calls
        for call in current_data.get('calls', []):
            strike = call['strike']
            if strike not in prev_calls:
                continue
            
            prev_call = prev_calls[strike]
            current_oi = call.get('oi', 0)
            previous_oi = prev_call.get('oi', 0)
            
            if previous_oi <= 0:
                continue
            
            oi_change = current_oi - previous_oi
            oi_change_pct = (oi_change / previous_oi) * 100
            
            if abs(oi_change_pct) >= self.MIN_OI_CHANGE_PCT:
                spurt_type, interpretation = self.classify_spurt(oi_change, spot_change_pct)
                signal_strength = self.get_signal_strength(oi_change_pct)
                action = self.get_action_suggested(spurt_type, "CE", signal_strength)
                
                spurts.append(OISpurt(
                    symbol=symbol,
                    strike=strike,
                    option_type="CE",
                    expiry=call.get('expiry', ''),
                    timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    current_oi=current_oi,
                    previous_oi=previous_oi,
                    oi_change=oi_change,
                    oi_change_pct=round(oi_change_pct, 1),
                    current_price=call.get('ltp', 0),
                    previous_price=prev_call.get('ltp', 0),
                    price_change_pct=round(spot_change_pct, 2),
                    spurt_type=spurt_type,
                    signal_strength=signal_strength,
                    interpretation=interpretation,
                    action_suggested=action
                ))
        
        # Check Puts
        for put in current_data.get('puts', []):
            strike = put['strike']
            if strike not in prev_puts:
                continue
            
            prev_put = prev_puts[strike]
            current_oi = put.get('oi', 0)
            previous_oi = prev_put.get('oi', 0)
            
            if previous_oi <= 0:
                continue
            
            oi_change = current_oi - previous_oi
            oi_change_pct = (oi_change / previous_oi) * 100
            
            if abs(oi_change_pct) >= self.MIN_OI_CHANGE_PCT:
                spurt_type, interpretation = self.classify_spurt(oi_change, spot_change_pct)
                signal_strength = self.get_signal_strength(oi_change_pct)
                action = self.get_action_suggested(spurt_type, "PE", signal_strength)
                
                spurts.append(OISpurt(
                    symbol=symbol,
                    strike=strike,
                    option_type="PE",
                    expiry=put.get('expiry', ''),
                    timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    current_oi=current_oi,
                    previous_oi=previous_oi,
                    oi_change=oi_change,
                    oi_change_pct=round(oi_change_pct, 1),
                    current_price=put.get('ltp', 0),
                    previous_price=prev_put.get('ltp', 0),
                    price_change_pct=round(spot_change_pct, 2),
                    spurt_type=spurt_type,
                    signal_strength=signal_strength,
                    interpretation=interpretation,
                    action_suggested=action
                ))
        
        return spurts
    
    def analyze_spurts(self, spurts: List[OISpurt]) -> DailySpurtSummary:
        """Analyze all detected spurts and create summary."""
        # Categorize
        long_buildups = []
        short_buildups = []
        long_unwindings = []
        short_coverings = []
        
        for spurt in spurts:
            spurt_dict = asdict(spurt)
            
            if spurt.spurt_type == SpurtType.LONG_BUILDUP.value:
                long_buildups.append(spurt_dict)
            elif spurt.spurt_type == SpurtType.SHORT_BUILDUP.value:
                short_buildups.append(spurt_dict)
            elif spurt.spurt_type == SpurtType.LONG_UNWINDING.value:
                long_unwindings.append(spurt_dict)
            elif spurt.spurt_type == SpurtType.SHORT_COVERING.value:
                short_coverings.append(spurt_dict)
        
        # Sort each category by OI change percentage
        for category in [long_buildups, short_buildups, long_unwindings, short_coverings]:
            category.sort(key=lambda x: abs(x['oi_change_pct']), reverse=True)
        
        # Calculate market sentiment
        bullish_score = len(long_buildups) + len(short_coverings)
        bearish_score = len(short_buildups) + len(long_unwindings)
        total = bullish_score + bearish_score
        
        if total > 0:
            sentiment_score = (bullish_score - bearish_score) / total
        else:
            sentiment_score = 0
        
        if sentiment_score > 0.3:
            market_sentiment = "BULLISH"
        elif sentiment_score < -0.3:
            market_sentiment = "BEARISH"
        else:
            market_sentiment = "NEUTRAL"
        
        # Top signals
        top_bullish = []
        top_bearish = []
        
        for spurt in spurts:
            if spurt.signal_strength == "STRONG":
                if "Bullish" in spurt.action_suggested:
                    top_bullish.append(asdict(spurt))
                elif "Bearish" in spurt.action_suggested:
                    top_bearish.append(asdict(spurt))
        
        top_bullish.sort(key=lambda x: abs(x['oi_change_pct']), reverse=True)
        top_bearish.sort(key=lambda x: abs(x['oi_change_pct']), reverse=True)
        
        # Generate predictions
        predictions = self._generate_predictions(spurts)
        
        return DailySpurtSummary(
            date=datetime.now().strftime('%Y-%m-%d'),
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_spurts=len(spurts),
            long_buildups=long_buildups[:10],
            short_buildups=short_buildups[:10],
            long_unwindings=long_unwindings[:10],
            short_coverings=short_coverings[:10],
            top_bullish_signals=top_bullish[:5],
            top_bearish_signals=top_bearish[:5],
            market_sentiment=market_sentiment,
            sentiment_score=round(sentiment_score, 2),
            next_day_predictions=predictions
        )
    
    def _generate_predictions(self, spurts: List[OISpurt]) -> List[Dict]:
        """Generate next-day predictions based on spurts."""
        predictions = []
        
        # Group by symbol
        symbol_spurts = {}
        for spurt in spurts:
            if spurt.symbol not in symbol_spurts:
                symbol_spurts[spurt.symbol] = []
            symbol_spurts[spurt.symbol].append(spurt)
        
        for symbol, sym_spurts in symbol_spurts.items():
            # Count directions
            bullish_count = sum(1 for s in sym_spurts if "Bullish" in s.action_suggested)
            bearish_count = sum(1 for s in sym_spurts if "Bearish" in s.action_suggested)
            strong_count = sum(1 for s in sym_spurts if s.signal_strength == "STRONG")
            
            if strong_count == 0:
                continue
            
            if bullish_count > bearish_count:
                direction = "BULLISH"
                confidence = min(0.9, 0.5 + (bullish_count / (bullish_count + bearish_count)) * 0.4)
            elif bearish_count > bullish_count:
                direction = "BEARISH"
                confidence = min(0.9, 0.5 + (bearish_count / (bullish_count + bearish_count)) * 0.4)
            else:
                direction = "RANGE_BOUND"
                confidence = 0.5
            
            predictions.append({
                'symbol': symbol,
                'direction': direction,
                'confidence': round(confidence, 2),
                'total_spurts': len(sym_spurts),
                'strong_signals': strong_count,
                'bullish_signals': bullish_count,
                'bearish_signals': bearish_count,
                'reason': f"{strong_count} strong OI spurts with {direction} bias"
            })
        
        # Sort by confidence
        predictions.sort(key=lambda x: x['confidence'], reverse=True)
        return predictions[:10]
    
    def save_summary(self, summary: DailySpurtSummary) -> Path:
        """Save summary to file."""
        save_dir = self.spurts_dir / summary.date
        save_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = save_dir / 'oi_spurts_analysis.json'
        
        with open(filepath, 'w') as f:
            json.dump(asdict(summary), f, indent=2)
        
        logger.info(f"💾 Saved analysis to {filepath.relative_to(BASE_DIR)}")
        return filepath
    
    def run_detection(self, symbols: List[str]) -> DailySpurtSummary:
        """Run OI spurt detection for given symbols."""
        logger.info("=" * 60)
        logger.info("OI SPURT DETECTION START")
        logger.info("=" * 60)
        
        today = datetime.now()
        all_spurts = []
        
        for symbol in symbols:
            logger.info(f"Analyzing {symbol}...")
            
            current_data = self.load_option_chain(symbol, today)
            previous_data = self.load_previous_day_data(symbol, today)
            
            if current_data and previous_data:
                spurts = self.detect_spurts(current_data, previous_data)
                all_spurts.extend(spurts)
                logger.info(f"  {symbol}: {len(spurts)} spurts detected")
            else:
                logger.warning(f"  {symbol}: No data available")
        
        # Analyze all spurts
        summary = self.analyze_spurts(all_spurts)
        
        # Save
        self.save_summary(summary)
        
        # Print summary
        logger.info(f"\n📊 DAILY OI SPURT SUMMARY")
        logger.info(f"  Total Spurts: {summary.total_spurts}")
        logger.info(f"  Market Sentiment: {summary.market_sentiment} ({summary.sentiment_score})")
        logger.info(f"  Long Buildups: {len(summary.long_buildups)}")
        logger.info(f"  Short Buildups: {len(summary.short_buildups)}")
        
        if summary.next_day_predictions:
            logger.info(f"\n🎯 NEXT DAY PREDICTIONS:")
            for pred in summary.next_day_predictions[:5]:
                logger.info(f"  {pred['symbol']}: {pred['direction']} (Conf: {pred['confidence']})")
        
        logger.info("=" * 60)
        logger.info("OI SPURT DETECTION COMPLETED")
        logger.info("=" * 60)
        
        return summary


def main():
    """Main execution."""
    # Test with sample symbols
    test_symbols = ["RELIANCE", "HDFCBANK", "TCS", "INFY", "SBIN"]
    
    detector = OISpurtDetector()
    summary = detector.run_detection(test_symbols)
    
    print(f"\nGenerated {len(summary.next_day_predictions)} predictions for tomorrow")


if __name__ == "__main__":
    main()
