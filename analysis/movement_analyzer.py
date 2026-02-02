"""
Movement Reason Analyzer
=========================
Analyzes WHY a stock moved and correlates with OI data.

Features:
- Correlates price moves with OI patterns
- Identifies support/resistance breakouts
- Tracks sector-wide moves vs individual stock moves
- Historical correlation for pattern learning
- Provides actionable insights for future trading

Schedule: 4:30 PM daily (after predictions generated)
"""

import json
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict, field
from enum import Enum

# Setup
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"movement_analyzer_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("MovementAnalyzer")


class MoveReason(str, Enum):
    """Reasons for stock movement"""
    OI_BUILDUP = "OI_BUILDUP"              # Predicted by OI signals
    OI_UNWINDING = "OI_UNWINDING"          # OI reduction drove move
    SECTOR_MOVE = "SECTOR_MOVE"            # Whole sector moved
    SUPPORT_BREAK = "SUPPORT_BREAK"        # Broke key support
    RESISTANCE_BREAK = "RESISTANCE_BREAK"  # Broke key resistance
    CONTINUATION = "CONTINUATION"          # Continuation of trend
    REVERSAL = "REVERSAL"                  # Trend reversal
    NEWS_DRIVEN = "NEWS_DRIVEN"            # News-based (needs external input)
    UNKNOWN = "UNKNOWN"                    # Cannot determine


@dataclass
class MovementAnalysis:
    """Analysis of why a stock moved"""
    symbol: str
    date: str
    
    # Price movement
    open_price: float
    close_price: float
    high_price: float
    low_price: float
    change_pct: float
    volume: int
    
    # Analysis
    primary_reason: str
    secondary_reasons: List[str]
    oi_correlation: str  # "MATCHED" if OI predicted correctly, "MISSED" if not
    prediction_was_correct: bool
    
    # Detailed breakdown
    oi_analysis: Dict
    technical_analysis: Dict
    sector_analysis: Dict
    
    # Learning insights
    pattern_detected: str
    confidence_score: float
    notes: str


@dataclass
class DailyMovementReport:
    """Daily report of all analyzed movements"""
    date: str
    generated_at: str
    total_analyzed: int
    correct_predictions: int
    prediction_accuracy: float
    
    # Categorized movements
    oi_driven_moves: List[Dict]
    sector_driven_moves: List[Dict]
    technical_breakouts: List[Dict]
    reversals: List[Dict]
    
    # Learning insights
    patterns_detected: List[Dict]
    improvement_suggestions: List[str]


# Sector mapping for F&O stocks
SECTOR_MAPPING = {
    # Banking
    "HDFCBANK": "BANKING", "ICICIBANK": "BANKING", "SBIN": "BANKING",
    "AXISBANK": "BANKING", "KOTAKBANK": "BANKING", "BAJFINANCE": "NBFC",
    "BAJAJFINSV": "NBFC", "INDUSINDBK": "BANKING", "BANKBARODA": "BANKING",
    "PNB": "BANKING",
    
    # IT
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT",
    "TECHM": "IT", "LTI": "IT",
    
    # Metals
    "TATASTEEL": "METALS", "HINDALCO": "METALS", "JSWSTEEL": "METALS",
    "JINDALSTEL": "METALS", "COALINDIA": "METALS",
    
    # Auto
    "MARUTI": "AUTO", "TATAMOTORS": "AUTO", "M&M": "AUTO",
    "BAJAJ-AUTO": "AUTO", "HEROMOTOCO": "AUTO", "EICHERMOT": "AUTO",
    
    # Pharma
    "SUNPHARMA": "PHARMA", "DRREDDY": "PHARMA", "CIPLA": "PHARMA",
    "DIVISLAB": "PHARMA", "APOLLOHOSP": "PHARMA",
    
    # Energy
    "RELIANCE": "ENERGY", "ONGC": "ENERGY", "BPCL": "ENERGY",
    "POWERGRID": "ENERGY", "NTPC": "ENERGY", "TATAPOWER": "ENERGY",
    
    # FMCG
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "TITAN": "FMCG",
    
    # Infra
    "ADANIENT": "INFRA", "ADANIPORTS": "INFRA", "ULTRACEMCO": "INFRA",
    "GRASIM": "INFRA", "ASIANPAINT": "INFRA",
    
    # Insurance
    "SBILIFE": "INSURANCE", "HDFCLIFE": "INSURANCE"
}


class MovementReasonAnalyzer:
    """Analyzes why stocks moved and correlates with predictions."""
    
    def __init__(self):
        self.data_dir = BASE_DIR / 'data' / 'daily_analysis'
        self.predictions_dir = BASE_DIR / 'data' / 'predictions'
        self.correlation_dir = BASE_DIR / 'data' / 'correlations'
        self.correlation_dir.mkdir(parents=True, exist_ok=True)
    
    def load_gainers_losers(self, date: datetime) -> Optional[Dict]:
        """Load gainers/losers data for a date."""
        filepath = self.data_dir / date.strftime('%Y-%m-%d') / 'gainers_losers.json'
        if filepath.exists():
            with open(filepath, 'r') as f:
                return json.load(f)
        return None
    
    def load_oi_spurts(self, date: datetime) -> Optional[Dict]:
        """Load OI spurts data for a date."""
        filepath = self.data_dir / date.strftime('%Y-%m-%d') / 'oi_spurts_analysis.json'
        if filepath.exists():
            with open(filepath, 'r') as f:
                return json.load(f)
        return None
    
    def load_predictions(self, date: datetime) -> Optional[Dict]:
        """Load predictions made for a date."""
        filepath = self.predictions_dir / date.strftime('%Y-%m-%d') / 'predictions.json'
        if filepath.exists():
            with open(filepath, 'r') as f:
                return json.load(f)
        return None
    
    def check_oi_correlation(self, symbol: str, actual_move: float, oi_data: Dict) -> Tuple[str, Dict]:
        """
        Check if OI data correctly predicted the move.
        Returns: (correlation_status, details)
        """
        if not oi_data:
            return ("NO_DATA", {})
        
        predictions = oi_data.get('next_day_predictions', [])
        
        for pred in predictions:
            if pred['symbol'] == symbol:
                predicted_direction = pred['direction']
                
                # Check if prediction matched
                if predicted_direction == "BULLISH" and actual_move > 1:
                    return ("MATCHED", {
                        "predicted": predicted_direction,
                        "actual": "UP",
                        "confidence": pred['confidence'],
                        "success": True
                    })
                elif predicted_direction == "BEARISH" and actual_move < -1:
                    return ("MATCHED", {
                        "predicted": predicted_direction,
                        "actual": "DOWN",
                        "confidence": pred['confidence'],
                        "success": True
                    })
                elif predicted_direction == "RANGE_BOUND" and abs(actual_move) < 1:
                    return ("MATCHED", {
                        "predicted": predicted_direction,
                        "actual": "SIDEWAYS",
                        "confidence": pred['confidence'],
                        "success": True
                    })
                else:
                    return ("MISSED", {
                        "predicted": predicted_direction,
                        "actual": "UP" if actual_move > 0 else "DOWN",
                        "confidence": pred['confidence'],
                        "success": False
                    })
        
        return ("NOT_PREDICTED", {})
    
    def check_sector_correlation(self, symbol: str, actual_move: float, 
                                  all_moves: Dict) -> Tuple[bool, Dict]:
        """
        Check if the move was sector-wide.
        Returns: (is_sector_move, details)
        """
        sector = SECTOR_MAPPING.get(symbol)
        if not sector:
            return (False, {})
        
        # Find other stocks in same sector
        sector_stocks = [s for s, sec in SECTOR_MAPPING.items() if sec == sector and s != symbol]
        
        sector_moves = []
        for stock in sector_stocks:
            for gainer in all_moves.get('top_stock_gainers', []):
                if gainer.get('symbol') == stock:
                    sector_moves.append(gainer.get('change_pct', 0))
            for loser in all_moves.get('top_stock_losers', []):
                if loser.get('symbol') == stock:
                    sector_moves.append(loser.get('change_pct', 0))
        
        if len(sector_moves) >= 2:
            avg_sector_move = sum(sector_moves) / len(sector_moves)
            
            # If sector moved in same direction with similar magnitude
            if (actual_move > 0 and avg_sector_move > 0) or (actual_move < 0 and avg_sector_move < 0):
                if abs(avg_sector_move) > 1:
                    return (True, {
                        "sector": sector,
                        "sector_avg_move": round(avg_sector_move, 2),
                        "stocks_analyzed": len(sector_moves)
                    })
        
        return (False, {})
    
    def detect_technical_breakout(self, symbol: str, data: Dict) -> Tuple[str, Dict]:
        """
        Detect if price broke key levels.
        Returns: (breakout_type, details)
        """
        high = data.get('high', 0)
        low = data.get('low', 0)
        close = data.get('ltp', 0)
        prev_close = data.get('previous_close', 0)
        change_pct = data.get('change_pct', 0)
        
        if not prev_close:
            return ("NONE", {})
        
        # Simple breakout detection based on range expansion
        range_pct = ((high - low) / prev_close) * 100 if prev_close else 0
        
        if change_pct > 3 and close == high:
            return ("RESISTANCE_BREAK", {
                "type": "Closed at day high",
                "strength": "STRONG" if change_pct > 5 else "MODERATE"
            })
        elif change_pct < -3 and close == low:
            return ("SUPPORT_BREAK", {
                "type": "Closed at day low",
                "strength": "STRONG" if change_pct < -5 else "MODERATE"
            })
        elif range_pct > 5:
            return ("RANGE_EXPANSION", {
                "type": "High volatility day",
                "range": round(range_pct, 2)
            })
        
        return ("NONE", {})
    
    def determine_primary_reason(self, oi_corr: str, is_sector: bool, 
                                  technical: str, change_pct: float) -> str:
        """Determine the primary reason for the move."""
        # Priority order for determining reason
        if oi_corr == "MATCHED":
            return MoveReason.OI_BUILDUP.value
        elif is_sector:
            return MoveReason.SECTOR_MOVE.value
        elif technical in ["RESISTANCE_BREAK", "SUPPORT_BREAK"]:
            return technical
        elif oi_corr == "MISSED":
            return MoveReason.REVERSAL.value  # OI predicted wrong, might be reversal
        else:
            return MoveReason.UNKNOWN.value
    
    def analyze_stock_movement(self, stock_data: Dict, date: datetime,
                                oi_data: Dict, all_moves: Dict) -> Optional[MovementAnalysis]:
        """Analyze why a single stock moved."""
        symbol = stock_data.get('symbol', '')
        change_pct = stock_data.get('change_pct', 0)
        
        if not symbol or abs(change_pct) < 0.5:
            return None  # Skip insignificant moves
        
        # Check OI correlation
        oi_corr, oi_details = self.check_oi_correlation(symbol, change_pct, oi_data)
        
        # Check sector correlation
        is_sector, sector_details = self.check_sector_correlation(symbol, change_pct, all_moves)
        
        # Check technical breakout
        technical, tech_details = self.detect_technical_breakout(symbol, stock_data)
        
        # Determine primary reason
        primary = self.determine_primary_reason(oi_corr, is_sector, technical, change_pct)
        
        # Collect secondary reasons
        secondary = []
        if oi_corr == "MATCHED" and is_sector:
            secondary.append(MoveReason.SECTOR_MOVE.value)
        if technical != "NONE" and primary != technical:
            secondary.append(technical)
        
        # Determine if prediction was correct
        pred_correct = oi_corr == "MATCHED"
        
        # Confidence based on how well we understand the move
        confidence = 0.0
        if primary != MoveReason.UNKNOWN.value:
            confidence += 0.4
        if oi_corr == "MATCHED":
            confidence += 0.3
        if is_sector:
            confidence += 0.2
        if technical != "NONE":
            confidence += 0.1
        
        # Pattern detection
        pattern = "Unknown"
        if oi_corr == "MATCHED":
            pattern = "OI-Driven Move - High predictability"
        elif is_sector and not pred_correct:
            pattern = "Sector Tide - Individual OI less relevant"
        elif technical in ["RESISTANCE_BREAK", "SUPPORT_BREAK"]:
            pattern = "Technical Breakout - Key level breach"
        
        return MovementAnalysis(
            symbol=symbol,
            date=date.strftime('%Y-%m-%d'),
            open_price=stock_data.get('open', 0),
            close_price=stock_data.get('ltp', 0),
            high_price=stock_data.get('high', 0),
            low_price=stock_data.get('low', 0),
            change_pct=change_pct,
            volume=stock_data.get('volume', 0),
            primary_reason=primary,
            secondary_reasons=secondary,
            oi_correlation=oi_corr,
            prediction_was_correct=pred_correct,
            oi_analysis=oi_details,
            technical_analysis=tech_details,
            sector_analysis=sector_details,
            pattern_detected=pattern,
            confidence_score=round(confidence, 2),
            notes=""
        )
    
    def generate_improvement_suggestions(self, analyses: List[MovementAnalysis]) -> List[str]:
        """Generate suggestions to improve predictions based on results."""
        suggestions = []
        
        # Count different scenarios
        oi_matched = sum(1 for a in analyses if a.oi_correlation == "MATCHED")
        oi_missed = sum(1 for a in analyses if a.oi_correlation == "MISSED")
        sector_moves = sum(1 for a in analyses if a.primary_reason == MoveReason.SECTOR_MOVE.value)
        
        total = len(analyses)
        if total == 0:
            return ["No movements to analyze today"]
        
        # Generate suggestions
        if oi_missed > oi_matched:
            suggestions.append(
                "OI predictions underperformed. Consider: "
                "1) Increasing OI change threshold, "
                "2) Weighting sector trends higher"
            )
        
        if sector_moves > total * 0.5:
            suggestions.append(
                "Many sector-wide moves today. Consider: "
                "Adding sector momentum as a prediction factor"
            )
        
        if oi_matched > 0:
            suggestions.append(
                f"OI correctly predicted {oi_matched} moves. "
                "Continue monitoring these patterns"
            )
        
        return suggestions
    
    def run_analysis(self, date: datetime = None) -> DailyMovementReport:
        """Run full movement analysis for a date."""
        if date is None:
            date = datetime.now()
        
        logger.info("=" * 60)
        logger.info(f"MOVEMENT ANALYSIS FOR {date.strftime('%Y-%m-%d')}")
        logger.info("=" * 60)
        
        # Get previous day's OI data (which predicted today)
        prev_day = date - timedelta(days=1)
        while prev_day.weekday() >= 5:
            prev_day -= timedelta(days=1)
        
        oi_data = self.load_oi_spurts(prev_day)
        all_moves = self.load_gainers_losers(date)
        
        if not all_moves:
            logger.warning("No movement data available")
            return self._empty_report(date)
        
        # Analyze all movers
        analyses = []
        
        for gainer in all_moves.get('top_stock_gainers', []):
            analysis = self.analyze_stock_movement(gainer, date, oi_data, all_moves)
            if analysis:
                analyses.append(analysis)
        
        for loser in all_moves.get('top_stock_losers', []):
            analysis = self.analyze_stock_movement(loser, date, oi_data, all_moves)
            if analysis:
                analyses.append(analysis)
        
        # Categorize
        oi_driven = [asdict(a) for a in analyses if a.primary_reason == MoveReason.OI_BUILDUP.value]
        sector_driven = [asdict(a) for a in analyses if a.primary_reason == MoveReason.SECTOR_MOVE.value]
        technical = [asdict(a) for a in analyses if a.primary_reason in ["RESISTANCE_BREAK", "SUPPORT_BREAK"]]
        reversals = [asdict(a) for a in analyses if a.primary_reason == MoveReason.REVERSAL.value]
        
        # Calculate accuracy
        correct = sum(1 for a in analyses if a.prediction_was_correct)
        accuracy = correct / len(analyses) if analyses else 0
        
        # Get improvement suggestions
        suggestions = self.generate_improvement_suggestions(analyses)
        
        # Create report
        report = DailyMovementReport(
            date=date.strftime('%Y-%m-%d'),
            generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_analyzed=len(analyses),
            correct_predictions=correct,
            prediction_accuracy=round(accuracy, 2),
            oi_driven_moves=oi_driven[:10],
            sector_driven_moves=sector_driven[:10],
            technical_breakouts=technical[:10],
            reversals=reversals[:10],
            patterns_detected=[
                {"pattern": a.pattern_detected, "symbol": a.symbol, "confidence": a.confidence_score}
                for a in analyses if a.confidence_score > 0.5
            ],
            improvement_suggestions=suggestions
        )
        
        # Save report
        self._save_report(report)
        
        # Log summary
        logger.info(f"Total Analyzed: {report.total_analyzed}")
        logger.info(f"Prediction Accuracy: {report.prediction_accuracy * 100:.1f}%")
        logger.info(f"OI-Driven Moves: {len(oi_driven)}")
        logger.info(f"Sector-Driven: {len(sector_driven)}")
        logger.info(f"Technical Breakouts: {len(technical)}")
        
        logger.info("=" * 60)
        logger.info("MOVEMENT ANALYSIS COMPLETED")
        logger.info("=" * 60)
        
        return report
    
    def _empty_report(self, date: datetime) -> DailyMovementReport:
        """Return empty report when no data."""
        return DailyMovementReport(
            date=date.strftime('%Y-%m-%d'),
            generated_at=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_analyzed=0,
            correct_predictions=0,
            prediction_accuracy=0,
            oi_driven_moves=[],
            sector_driven_moves=[],
            technical_breakouts=[],
            reversals=[],
            patterns_detected=[],
            improvement_suggestions=["No data available for analysis"]
        )
    
    def _save_report(self, report: DailyMovementReport) -> Path:
        """Save movement analysis report."""
        save_dir = self.correlation_dir / report.date
        save_dir.mkdir(parents=True, exist_ok=True)
        
        filepath = save_dir / 'movement_analysis.json'
        
        with open(filepath, 'w') as f:
            json.dump(asdict(report), f, indent=2)
        
        logger.info(f"💾 Saved analysis to {filepath.relative_to(BASE_DIR)}")
        return filepath


def main():
    """Main execution."""
    analyzer = MovementReasonAnalyzer()
    report = analyzer.run_analysis()
    
    print(f"\n📊 Movement Analysis Summary")
    print(f"  Stocks Analyzed: {report.total_analyzed}")
    print(f"  Prediction Accuracy: {report.prediction_accuracy * 100:.1f}%")
    
    if report.improvement_suggestions:
        print("\n💡 Improvement Suggestions:")
        for sugg in report.improvement_suggestions:
            print(f"  • {sugg}")


if __name__ == "__main__":
    main()
