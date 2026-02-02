"""
India VIX Analyzer
===================
Fetches India VIX and provides trading safety filters

VIX Rules:
- VIX < 13: SAFE - aggressive selling
- VIX 13-18: SAFE - normal selling  
- VIX 18-22: CAUTION - reduced position
- VIX > 22: AVOID - no selling
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from angelone_api import AngelOneAPI
    API_OK = True
except ImportError:
    API_OK = False


class VIXLevel(Enum):
    """VIX safety levels"""
    VERY_LOW = "VERY_LOW"    # < 13 - Aggressive selling
    LOW = "LOW"              # 13-15 - Normal selling
    NORMAL = "NORMAL"        # 15-18 - Careful selling
    ELEVATED = "ELEVATED"    # 18-22 - Reduced positions
    HIGH = "HIGH"            # 22-25 - Avoid selling
    EXTREME = "EXTREME"      # > 25 - No trading


class VIXAnalyzer:
    """Analyze India VIX for trading safety"""
    
    # VIX thresholds
    THRESHOLDS = {
        'very_low': 13,
        'low': 15,
        'normal': 18,
        'elevated': 22,
        'high': 25,
    }
    
    def __init__(self):
        self.api = None
        self._logged_in = False
        self._cached_vix = None
        self._cache_time = None
        self._cache_duration = timedelta(minutes=5)  # Cache for 5 min
    
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
    
    def get_india_vix(self) -> Optional[float]:
        """Get current India VIX value"""
        
        # Check cache
        if self._cached_vix and self._cache_time:
            if datetime.now(IST) - self._cache_time < self._cache_duration:
                return self._cached_vix
        
        if not self._ensure_login():
            return None
        
        try:
            # Try multiple methods to get VIX
            
            # Method 1: Direct quote
            try:
                quote = self.api.smart_api.getMarketData(
                    mode='LTP',
                    exchangeTokens={'NSE': ['26017']}
                )
                if quote and quote.get('data') and quote['data'].get('fetched'):
                    vix = float(quote['data']['fetched'][0]['ltp'])
                    self._cached_vix = vix
                    self._cache_time = datetime.now(IST)
                    return vix
            except:
                pass
            
            # Method 2: Try INDIAVIX
            try:
                quote = self.api.smart_api.getMarketData(
                    mode='LTP',
                    exchangeTokens={'NSE': ['26017']}
                )
                if quote and quote.get('data'):
                    vix = float(quote['data']['fetched'][0]['ltp'])
                    self._cached_vix = vix
                    self._cache_time = datetime.now(IST)
                    return vix
            except:
                pass
            
            # Fallback: Use default based on market conditions
            # In absence of VIX, assume normal conditions
            print("⚠️ VIX unavailable, using default 15")
            return 15.0
                
        except Exception as e:
            print(f"VIX fetch error: {e}")
        
        return 15.0  # Default to normal VIX
    
    def get_vix_level(self, vix: float = None) -> VIXLevel:
        """Get VIX safety level"""
        
        if vix is None:
            vix = self.get_india_vix()
        
        if vix is None:
            return VIXLevel.NORMAL  # Default if can't fetch
        
        if vix < self.THRESHOLDS['very_low']:
            return VIXLevel.VERY_LOW
        elif vix < self.THRESHOLDS['low']:
            return VIXLevel.LOW
        elif vix < self.THRESHOLDS['normal']:
            return VIXLevel.NORMAL
        elif vix < self.THRESHOLDS['elevated']:
            return VIXLevel.ELEVATED
        elif vix < self.THRESHOLDS['high']:
            return VIXLevel.HIGH
        else:
            return VIXLevel.EXTREME
    
    def is_safe_to_trade(self, vix: float = None) -> Tuple[bool, str]:
        """Check if VIX allows trading"""
        
        if vix is None:
            vix = self.get_india_vix()
        
        if vix is None:
            return True, "VIX unavailable, proceeding with caution"
        
        level = self.get_vix_level(vix)
        
        if level in [VIXLevel.VERY_LOW, VIXLevel.LOW, VIXLevel.NORMAL]:
            return True, f"VIX {vix:.2f} - Safe to sell premium"
        elif level == VIXLevel.ELEVATED:
            return True, f"VIX {vix:.2f} - Caution: Reduce position size"
        else:
            return False, f"VIX {vix:.2f} - AVOID selling premium"
    
    def get_position_multiplier(self, vix: float = None) -> float:
        """Get position size multiplier based on VIX"""
        
        if vix is None:
            vix = self.get_india_vix()
        
        if vix is None:
            return 1.0
        
        level = self.get_vix_level(vix)
        
        multipliers = {
            VIXLevel.VERY_LOW: 1.5,   # Aggressive
            VIXLevel.LOW: 1.2,        # Normal+
            VIXLevel.NORMAL: 1.0,     # Normal
            VIXLevel.ELEVATED: 0.5,   # Half size
            VIXLevel.HIGH: 0.25,      # Quarter size
            VIXLevel.EXTREME: 0.0,    # No trading
        }
        
        return multipliers.get(level, 1.0)
    
    def get_analysis(self) -> dict:
        """Get complete VIX analysis"""
        
        vix = self.get_india_vix()
        
        if vix is None:
            return {
                'vix': None,
                'level': 'UNKNOWN',
                'safe_to_trade': True,
                'message': 'VIX unavailable',
                'position_multiplier': 1.0,
            }
        
        level = self.get_vix_level(vix)
        safe, msg = self.is_safe_to_trade(vix)
        mult = self.get_position_multiplier(vix)
        
        return {
            'vix': vix,
            'level': level.value,
            'safe_to_trade': safe,
            'message': msg,
            'position_multiplier': mult,
        }


# Singleton
_analyzer = None


def get_analyzer() -> VIXAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = VIXAnalyzer()
    return _analyzer


def get_india_vix() -> Optional[float]:
    """Get India VIX"""
    return get_analyzer().get_india_vix()


def is_vix_safe() -> Tuple[bool, str]:
    """Check if VIX is safe for trading"""
    return get_analyzer().is_safe_to_trade()


def get_vix_analysis() -> dict:
    """Get complete VIX analysis"""
    return get_analyzer().get_analysis()


if __name__ == "__main__":
    print("="*50)
    print("       INDIA VIX ANALYZER")
    print("="*50)
    
    analysis = get_vix_analysis()
    
    print(f"\nVIX: {analysis['vix']}")
    print(f"Level: {analysis['level']}")
    print(f"Safe to trade: {analysis['safe_to_trade']}")
    print(f"Message: {analysis['message']}")
    print(f"Position multiplier: {analysis['position_multiplier']}x")
