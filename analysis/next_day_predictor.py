"""
Next Day Predictor
===================
Uses OI patterns and historical data to predict next-day movers.

Features:
- Combines OI spurts, gainers/losers, and technical signals
- Confidence scoring based on historical accuracy
- Telegram alerts for high-confidence predictions
- Tracks prediction outcomes for self-improvement

Schedule: 4:00 PM daily (after all data collected)
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field

# Setup
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"predictor_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NextDayPredictor")

# Try to import notifications
try:
    from scripts.notifications import TelegramNotifier
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    logger.info("Telegram notifications not available")


@dataclass
class Prediction:
    """Individual stock prediction"""
    symbol: str
    direction: str  # BULLISH, BEARISH, RANGE_BOUND
    confidence: float  # 0.0 to 1.0
    target_move_pct: float  # Expected % move
    stop_loss_pct: float  # SL for options trade
    
    # Reasoning
    reasons: List[str]
    oi_signal: str
    gainer_loser_signal: str
    technical_signal: str
    
    # Risk assessment
    risk_level: str  # LOW, MEDIUM, HIGH
    suggested_strategy: str
    
    # For tracking
    predicted_at: str = field(default_factory=lambda: datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    actual_result: Optional[str] = None
    was_correct: Optional[bool] = None


@dataclass
class DailyPredictions:
    """Daily predictions summary"""
    date: str
    generated_at: str
    predictions: List[Dict]
    top_bullish: List[Dict]
    top_bearish: List[Dict]
    model_accuracy: float  # Historical accuracy
    alerts_sent: bool


class NextDayPredictor:
    """Predicts next-day movers based on multiple signals."""
    
    # Weights for different signals
    WEIGHTS = {
        'oi_spurt': 0.40,           # OI signals are primary
        'gainers_losers': 0.25,     # Recent momentum
        'trending': 0.20,           # Multi-day trends
        'technical': 0.15           # Support/resistance
    }
    
    def __init__(self):
        self.data_dir = BASE_DIR / 'data' / 'daily_analysis'
        self.predictions_dir = BASE_DIR / 'data' / 'predictions'
        self.predictions_dir.mkdir(parents=True, exist_ok=True)
        
        if TELEGRAM_AVAILABLE:
            self.telegram = TelegramNotifier()
        else:
            self.telegram = None
    
    def load_oi_spurts(self, date: datetime) -> Optional[Dict]:
        """Load OI spurts analysis for a date."""
        filepath = self.data_dir / date.strftime('%Y-%m-%d') / 'oi_spurts_analysis.json'
        
        if filepath.exists():
            with open(filepath, 'r') as f:
                return json.load(f)
        return None
    
    def load_gainers_losers(self, date: datetime) -> Optional[Dict]:
        """Load gainers/losers data for a date."""
        filepath = self.data_dir / date.strftime('%Y-%m-%d') / 'gainers_losers.json'
        
        if filepath.exists():
            with open(filepath, 'r') as f:
                return json.load(f)
        return None
    
    def load_historical_accuracy(self) -> float:
        """Load historical prediction accuracy."""
        filepath = self.predictions_dir / 'accuracy_history.json'
        
        if filepath.exists():
            try:
                with open(filepath, 'r') as f:
                    data = json.load(f)
                return data.get('overall_accuracy', 0.5)
            except:
                pass
        return 0.5  # Default 50%
    
    def analyze_oi_signal(self, symbol: str, oi_data: Dict) -> Tuple[str, float, str]:
        """
        Analyze OI data for a symbol.
        Returns: (direction, confidence, reason)
        """
        if not oi_data:
            return ("NEUTRAL", 0.0, "No OI data available")
        
        predictions = oi_data.get('next_day_predictions', [])
        
        for pred in predictions:
            if pred['symbol'] == symbol:
                return (
                    pred['direction'],
                    pred['confidence'],
                    f"OI: {pred['strong_signals']} strong spurts, {pred['direction']} bias"
                )
        
        # Check market sentiment as fallback
        sentiment = oi_data.get('market_sentiment', 'NEUTRAL')
        return (sentiment, 0.3, f"Following overall market sentiment: {sentiment}")
    
    def analyze_momentum_signal(self, symbol: str, gl_data: Dict) -> Tuple[str, float, str]:
        """
        Analyze gainers/losers data for momentum.
        Returns: (direction, confidence, reason)
        """
        if not gl_data:
            return ("NEUTRAL", 0.0, "No momentum data")
        
        # Check if in gainers
        for gainer in gl_data.get('top_stock_gainers', []):
            if gainer.get('symbol') == symbol:
                change_pct = gainer.get('change_pct', 0)
                
                # Strong gainer = potential continuation or reversal
                if change_pct > 5:
                    return ("BULLISH", 0.6, f"Strong gainer today ({change_pct}%), momentum likely")
                elif change_pct > 3:
                    return ("BULLISH", 0.4, f"Gainer today ({change_pct}%), moderate momentum")
                else:
                    return ("NEUTRAL", 0.2, f"Small gain ({change_pct}%), no clear direction")
        
        # Check if in losers
        for loser in gl_data.get('top_stock_losers', []):
            if loser.get('symbol') == symbol:
                change_pct = loser.get('change_pct', 0)
                
                if change_pct < -5:
                    return ("BEARISH", 0.6, f"Strong loser today ({change_pct}%), selling pressure")
                elif change_pct < -3:
                    return ("BEARISH", 0.4, f"Loser today ({change_pct}%), moderate weakness")
                else:
                    return ("NEUTRAL", 0.2, f"Small loss ({change_pct}%), no clear direction")
        
        return ("NEUTRAL", 0.0, "Not in top movers")
    
    def analyze_trending_signal(self, symbol: str, gl_data: Dict) -> Tuple[str, float, str]:
        """
        Analyze if symbol is trending across multiple days.
        Returns: (direction, confidence, reason)
        """
        if not gl_data:
            return ("NEUTRAL", 0.0, "No trend data")
        
        trending_stocks = gl_data.get('trending_stocks', [])
        
        if symbol in trending_stocks:
            # Check which direction it's trending
            for gainer in gl_data.get('top_stock_gainers', []):
                if gainer.get('symbol') == symbol:
                    return ("BULLISH", 0.5, "Multi-day gainer - trend continuation likely")
            
            for loser in gl_data.get('top_stock_losers', []):
                if loser.get('symbol') == symbol:
                    return ("BEARISH", 0.5, "Multi-day loser - trend continuation likely")
        
        return ("NEUTRAL", 0.0, "Not trending")
    
    def combine_signals(self, 
                       oi_signal: Tuple, 
                       momentum_signal: Tuple, 
                       trending_signal: Tuple) -> Tuple[str, float, List[str]]:
        """
        Combine multiple signals into final prediction.
        Returns: (direction, confidence, reasons)
        """
        signals = {
            'oi': oi_signal,
            'momentum': momentum_signal,
            'trending': trending_signal
        }
        
        # Calculate weighted score for each direction
        bullish_score = 0
        bearish_score = 0
        reasons = []
        
        for sig_name, (direction, confidence, reason) in signals.items():
            if direction == "BULLISH":
                bullish_score += confidence * self.WEIGHTS.get(sig_name.replace('_signal', ''), 0.2)
            elif direction == "BEARISH":
                bearish_score += confidence * self.WEIGHTS.get(sig_name.replace('_signal', ''), 0.2)
            
            if confidence > 0.3:
                reasons.append(reason)
        
        # Determine final direction
        if bullish_score > bearish_score + 0.1:
            direction = "BULLISH"
            confidence = min(0.9, bullish_score)
        elif bearish_score > bullish_score + 0.1:
            direction = "BEARISH"
            confidence = min(0.9, bearish_score)
        else:
            direction = "RANGE_BOUND"
            confidence = max(bullish_score, bearish_score)
        
        return direction, round(confidence, 2), reasons
    
    def get_target_and_sl(self, direction: str, confidence: float) -> Tuple[float, float]:
        """Get target and stop loss based on direction and confidence."""
        if direction == "BULLISH":
            target = 1.5 + (confidence * 1.5)  # 1.5% to 3%
            sl = 1.0 + (0.5 * (1 - confidence))  # 1% to 1.5%
        elif direction == "BEARISH":
            target = 1.5 + (confidence * 1.5)
            sl = 1.0 + (0.5 * (1 - confidence))
        else:
            target = 0.5  # Range bound - small moves
            sl = 1.0
        
        return round(target, 1), round(sl, 1)
    
    def get_risk_level(self, confidence: float, direction: str) -> str:
        """Assess risk level of the prediction."""
        if confidence >= 0.7:
            return "LOW"
        elif confidence >= 0.5:
            return "MEDIUM"
        else:
            return "HIGH"
    
    def get_suggested_strategy(self, direction: str, risk_level: str) -> str:
        """Suggest options trading strategy."""
        if direction == "BULLISH":
            if risk_level == "LOW":
                return "Buy ITM Call or Sell OTM Put"
            elif risk_level == "MEDIUM":
                return "Buy ATM Call with defined SL"
            else:
                return "Small position Bull Call Spread"
        
        elif direction == "BEARISH":
            if risk_level == "LOW":
                return "Buy ITM Put or Sell OTM Call"
            elif risk_level == "MEDIUM":
                return "Buy ATM Put with defined SL"
            else:
                return "Small position Bear Put Spread"
        
        else:
            return "Short Straddle/Strangle if IV high, else wait"
    
    def generate_prediction(self, symbol: str, oi_data: Dict, gl_data: Dict) -> Optional[Prediction]:
        """Generate prediction for a symbol."""
        # Analyze all signals
        oi_signal = self.analyze_oi_signal(symbol, oi_data)
        momentum_signal = self.analyze_momentum_signal(symbol, gl_data)
        trending_signal = self.analyze_trending_signal(symbol, gl_data)
        
        # Combine signals
        direction, confidence, reasons = self.combine_signals(
            oi_signal, momentum_signal, trending_signal
        )
        
        # Skip low confidence predictions
        if confidence < 0.3:
            return None
        
        # Get target and SL
        target, sl = self.get_target_and_sl(direction, confidence)
        
        # Assess risk
        risk_level = self.get_risk_level(confidence, direction)
        
        # Suggest strategy
        strategy = self.get_suggested_strategy(direction, risk_level)
        
        return Prediction(
            symbol=symbol,
            direction=direction,
            confidence=confidence,
            target_move_pct=target,
            stop_loss_pct=sl,
            reasons=reasons,
            oi_signal=oi_signal[0],
            gainer_loser_signal=momentum_signal[0],
            technical_signal="N/A",  # Can integrate with existing analysis
            risk_level=risk_level,
            suggested_strategy=strategy
        )
    
    def generate_all_predictions(self) -> DailyPredictions:
        """Generate predictions for all tracked symbols."""
        logger.info("=" * 60)
        logger.info("GENERATING NEXT DAY PREDICTIONS")
        logger.info("=" * 60)
        
        today = datetime.now()
        
        # Load data
        oi_data = self.load_oi_spurts(today)
        gl_data = self.load_gainers_losers(today)
        
        # Get candidate symbols
        candidates = set()
        
        if oi_data and oi_data.get('next_day_predictions'):
            for pred in oi_data['next_day_predictions']:
                candidates.add(pred['symbol'])
        
        if gl_data:
            for g in gl_data.get('top_stock_gainers', [])[:10]:
                candidates.add(g.get('symbol', ''))
            for l in gl_data.get('top_stock_losers', [])[:10]:
                candidates.add(l.get('symbol', ''))
            for t in gl_data.get('trending_stocks', []):
                candidates.add(t)
        
        candidates.discard('')
        
        # Generate predictions
        predictions = []
        for symbol in candidates:
            pred = self.generate_prediction(symbol, oi_data, gl_data)
            if pred:
                predictions.append(asdict(pred))
        
        # Sort by confidence
        predictions.sort(key=lambda x: x['confidence'], reverse=True)
        
        # Split into bullish and bearish
        top_bullish = [p for p in predictions if p['direction'] == 'BULLISH'][:5]
        top_bearish = [p for p in predictions if p['direction'] == 'BEARISH'][:5]
        
        # Load historical accuracy
        accuracy = self.load_historical_accuracy()
        
        daily_preds = DailyPredictions(
            date=today.strftime('%Y-%m-%d'),
            generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            predictions=predictions,
            top_bullish=top_bullish,
            top_bearish=top_bearish,
            model_accuracy=accuracy,
            alerts_sent=False
        )
        
        logger.info(f"Generated {len(predictions)} predictions")
        logger.info(f"  Top Bullish: {[p['symbol'] for p in top_bullish]}")
        logger.info(f"  Top Bearish: {[p['symbol'] for p in top_bearish]}")
        
        return daily_preds
    
    def save_predictions(self, preds: DailyPredictions) -> Path:
        """Save predictions to file."""
        save_dir = self.predictions_dir / preds.date
        save_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = save_dir / 'predictions.json'
        
        with open(filepath, 'w') as f:
            json.dump(asdict(preds), f, indent=2)
        
        logger.info(f"💾 Saved predictions to {filepath.relative_to(BASE_DIR)}")
        return filepath
    
    def format_telegram_alert(self, preds: DailyPredictions) -> str:
        """Format predictions for Telegram alert."""
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%d-%b-%Y')
        
        msg = f"🎯 *NEXT DAY PREDICTIONS*\n"
        msg += f"📅 For: {tomorrow}\n"
        msg += f"📊 Model Accuracy: {preds.model_accuracy*100:.0f}%\n"
        msg += f"─" * 30 + "\n\n"
        
        if preds.top_bullish:
            msg += "📈 *BULLISH STOCKS:*\n"
            for p in preds.top_bullish[:3]:
                msg += f"  • {p['symbol']}: {p['confidence']*100:.0f}% conf\n"
                msg += f"    Target: +{p['target_move_pct']}% | SL: {p['stop_loss_pct']}%\n"
                msg += f"    Strategy: {p['suggested_strategy']}\n\n"
        
        if preds.top_bearish:
            msg += "📉 *BEARISH STOCKS:*\n"
            for p in preds.top_bearish[:3]:
                msg += f"  • {p['symbol']}: {p['confidence']*100:.0f}% conf\n"
                msg += f"    Target: +{p['target_move_pct']}% | SL: {p['stop_loss_pct']}%\n"
                msg += f"    Strategy: {p['suggested_strategy']}\n\n"
        
        msg += f"─" * 30 + "\n"
        msg += f"⚠️ DYOR. Trade with proper risk management."
        
        return msg
    
    def send_alerts(self, preds: DailyPredictions):
        """Send predictions via Telegram."""
        if not self.telegram:
            logger.info("Telegram not available, skipping alerts")
            return
        
        if not preds.top_bullish and not preds.top_bearish:
            logger.info("No high-confidence predictions, skipping alerts")
            return
        
        try:
            msg = self.format_telegram_alert(preds)
            self.telegram.send_message(msg)
            logger.info("✅ Telegram alert sent")
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")
    
    def run(self, send_telegram: bool = True) -> DailyPredictions:
        """Run the full prediction pipeline."""
        # Generate predictions
        preds = self.generate_all_predictions()
        
        # Save
        self.save_predictions(preds)
        
        # Send alerts
        if send_telegram:
            self.send_alerts(preds)
        
        logger.info("=" * 60)
        logger.info("PREDICTION GENERATION COMPLETED")
        logger.info("=" * 60)
        
        return preds


def main():
    """Main execution."""
    predictor = NextDayPredictor()
    predictions = predictor.run(send_telegram=False)
    
    print(f"\n🎯 Generated {len(predictions.predictions)} predictions")
    
    if predictions.top_bullish:
        print("\n📈 Top Bullish:")
        for p in predictions.top_bullish[:3]:
            print(f"  {p['symbol']}: {p['confidence']*100:.0f}% confident")
    
    if predictions.top_bearish:
        print("\n📉 Top Bearish:")
        for p in predictions.top_bearish[:3]:
            print(f"  {p['symbol']}: {p['confidence']*100:.0f}% confident")


if __name__ == "__main__":
    main()
