"""
Trend Filter
=============
Detects market trend to avoid Iron Condor in trending markets

Rules:
- If 1-hour change > 0.5%, market is TRENDING
- If 1-hour change < 0.3%, market is SIDEWAYS
- Iron Condor only in sideways markets
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from angelone_api import AngelOneAPI
    API_OK = True
except ImportError:
    API_OK = False


class TrendDirection(Enum):
    """Market trend direction"""
    STRONG_BULLISH = "STRONG_BULLISH"  # > 1%
    BULLISH = "BULLISH"                 # 0.5% to 1%
    SIDEWAYS = "SIDEWAYS"               # -0.3% to 0.3%
    BEARISH = "BEARISH"                 # -1% to -0.5%
    STRONG_BEARISH = "STRONG_BEARISH"   # < -1%


class TrendFilter:
    """Filter trades based on market trend"""
    
    THRESHOLDS = {
        'strong': 1.0,      # Strong trend
        'moderate': 0.5,    # Moderate trend
        'sideways': 0.3,    # Sideways boundary
    }
    
    def __init__(self):
        self.api = None
        self._logged_in = False
        
        # Cache for spot history
        self._spot_history = {}
        self._last_fetch = None
    
    def _ensure_login(self) -> bool:
        """Ensure API is logged in"""
        if self._logged_in and self.api:
            return True
        
        if not API_OK:
            return False
        
        try:
            self.api = AngelOneAPI()
            if self.api.login():
                self._logged_in = True
                return True
        except:
            pass
        
        return False
    
    def get_spot(self, symbol: str) -> Optional[float]:
        """Get current spot price"""
        if not self._ensure_login():
            return None
        
        token_map = {
            'NIFTY': ('NSE', 'Nifty 50', '99926000'),
            'BANKNIFTY': ('NSE', 'Nifty Bank', '99926009'),
        }
        
        info = token_map.get(symbol)
        if not info:
            return None
        
        try:
            ltp = self.api.get_ltp(*info)
            if ltp and ltp.get('data'):
                return float(ltp['data']['ltp'])
        except:
            pass
        
        return None
    
    def get_1hr_change(self, symbol: str) -> Optional[float]:
        """Get 1-hour percentage change"""
        
        # Note: Without historical data, we approximate using open price
        if not self._ensure_login():
            return None
        
        token_map = {
            'NIFTY': ('NSE', 'Nifty 50', '99926000'),
            'BANKNIFTY': ('NSE', 'Nifty Bank', '99926009'),
        }
        
        info = token_map.get(symbol)
        if not info:
            return None
        
        try:
            ltp = self.api.get_ltp(*info)
            if ltp and ltp.get('data'):
                current = float(ltp['data']['ltp'])
                # Use open price as proxy for 1-hour ago
                # This is approximation - in production use candle data
                open_price = float(ltp['data'].get('open', current))
                
                if open_price > 0:
                    change = (current - open_price) / open_price * 100
                    return change
        except:
            pass
        
        return None
    
    def get_trend(self, symbol: str) -> Tuple[TrendDirection, float]:
        """Get market trend direction"""
        
        change = self.get_1hr_change(symbol)
        
        if change is None:
            return TrendDirection.SIDEWAYS, 0.0
        
        if change >= self.THRESHOLDS['strong']:
            return TrendDirection.STRONG_BULLISH, change
        elif change >= self.THRESHOLDS['moderate']:
            return TrendDirection.BULLISH, change
        elif change <= -self.THRESHOLDS['strong']:
            return TrendDirection.STRONG_BEARISH, change
        elif change <= -self.THRESHOLDS['moderate']:
            return TrendDirection.BEARISH, change
        else:
            return TrendDirection.SIDEWAYS, change
    
    def is_sideways(self, symbol: str) -> Tuple[bool, str]:
        """Check if market is sideways (good for Iron Condor)"""
        
        trend, change = self.get_trend(symbol)
        
        if trend == TrendDirection.SIDEWAYS:
            return True, f"Market sideways ({change:+.2f}%) - Good for Iron Condor"
        elif trend in [TrendDirection.BULLISH, TrendDirection.BEARISH]:
            return False, f"Market trending ({change:+.2f}%) - Consider directional trade"
        else:
            return False, f"Strong trend ({change:+.2f}%) - AVOID Iron Condor"
    
    def should_trade_iron_condor(self, symbol: str) -> Tuple[bool, str]:
        """Check if Iron Condor is appropriate"""
        
        trend, change = self.get_trend(symbol)
        
        if abs(change) < self.THRESHOLDS['sideways']:
            return True, f"✅ Sideways market ({change:+.2f}%) - Iron Condor OK"
        elif abs(change) < self.THRESHOLDS['moderate']:
            return True, f"⚠️ Mild trend ({change:+.2f}%) - Iron Condor with caution"
        else:
            return False, f"❌ Trending market ({change:+.2f}%) - Skip Iron Condor"
    
    def get_analysis(self, symbol: str) -> dict:
        """Get complete trend analysis"""
        
        trend, change = self.get_trend(symbol)
        is_side, side_msg = self.is_sideways(symbol)
        should_ic, ic_msg = self.should_trade_iron_condor(symbol)
        spot = self.get_spot(symbol)
        
        return {
            'symbol': symbol,
            'spot': spot,
            'change_percent': change,
            'trend': trend.value,
            'is_sideways': is_side,
            'iron_condor_ok': should_ic,
            'message': ic_msg,
        }


# Singleton
_filter = None


def get_filter() -> TrendFilter:
    global _filter
    if _filter is None:
        _filter = TrendFilter()
    return _filter


def is_market_sideways(symbol: str) -> Tuple[bool, str]:
    """Check if market is sideways"""
    return get_filter().is_sideways(symbol)


def should_trade_iron_condor(symbol: str) -> Tuple[bool, str]:
    """Check if Iron Condor is appropriate"""
    return get_filter().should_trade_iron_condor(symbol)


def get_trend_analysis(symbol: str) -> dict:
    """Get trend analysis"""
    return get_filter().get_analysis(symbol)


if __name__ == "__main__":
    print("="*50)
    print("       TREND FILTER")
    print("="*50)
    
    for symbol in ['NIFTY', 'BANKNIFTY']:
        analysis = get_trend_analysis(symbol)
        
        print(f"\n{symbol}:")
        print(f"  Spot: ₹{analysis['spot']:,.2f}")
        print(f"  Change: {analysis['change_percent']:+.2f}%")
        print(f"  Trend: {analysis['trend']}")
        print(f"  Iron Condor OK: {analysis['iron_condor_ok']}")
        print(f"  Message: {analysis['message']}")
