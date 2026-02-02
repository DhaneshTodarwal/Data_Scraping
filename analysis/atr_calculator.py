"""
ATR-Based Strike Selection
============================
Uses Average True Range (ATR) for dynamic strike selection

Why ATR matters:
- ATR measures volatility
- High ATR = wider strikes needed
- Low ATR = narrower strikes OK

Default strikes: ATM ± 1x ATR
"""
import sys
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

IST = timezone(timedelta(hours=5, minutes=30))

try:
    from angelone_api import AngelOneAPI
    API_OK = True
except ImportError:
    API_OK = False


class ATRCalculator:
    """Calculate ATR and suggest optimal strikes"""
    
    # Default ATR values (if can't calculate)
    DEFAULT_ATR = {
        'NIFTY': 150,      # ~0.6% of spot
        'BANKNIFTY': 400,  # ~0.7% of spot
    }
    
    # Strike gap
    STRIKE_GAP = {
        'NIFTY': 50,
        'BANKNIFTY': 100,
    }
    
    def __init__(self):
        self.api = None
        self._logged_in = False
        self._cache = {}
        self._cache_time = {}
    
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
    
    def get_spot_and_range(self, symbol: str) -> Tuple[Optional[float], Optional[float], Optional[float]]:
        """Get spot, day high, day low"""
        if not self._ensure_login():
            return None, None, None
        
        token_map = {
            'NIFTY': ('NSE', 'Nifty 50', '99926000'),
            'BANKNIFTY': ('NSE', 'Nifty Bank', '99926009'),
        }
        
        info = token_map.get(symbol)
        if not info:
            return None, None, None
        
        try:
            ltp = self.api.get_ltp(*info)
            if ltp and ltp.get('data'):
                data = ltp['data']
                spot = float(data.get('ltp', 0))
                high = float(data.get('high', spot))
                low = float(data.get('low', spot))
                return spot, high, low
        except:
            pass
        
        return None, None, None
    
    def estimate_atr(self, symbol: str) -> float:
        """
        Estimate ATR from today's range
        
        Note: True ATR needs 14-day data. We use today's range as proxy.
        """
        spot, high, low = self.get_spot_and_range(symbol)
        
        if spot and high and low:
            # Today's range as ATR proxy
            day_range = high - low
            
            # Apply multiplier for typical ATR (range is usually less than ATR)
            estimated_atr = day_range * 1.2
            
            # Sanity check: ATR should be 0.3% - 1.5% of spot
            min_atr = spot * 0.003
            max_atr = spot * 0.015
            
            return max(min_atr, min(estimated_atr, max_atr))
        
        return self.DEFAULT_ATR.get(symbol, 150)
    
    def get_optimal_strikes(self, symbol: str, spot: float = None, 
                           multiplier: float = 1.0) -> dict:
        """
        Get optimal strikes based on ATR
        
        Args:
            symbol: NIFTY, BANKNIFTY
            spot: Current spot (fetched if not provided)
            multiplier: ATR multiplier (1.0 = 1x ATR)
        
        Returns:
            dict with:
            - atm: ATM strike
            - ce_sell: Call sell strike (ATM + ATR)
            - ce_buy: Call buy strike (ATM + ATR + gap)
            - pe_sell: Put sell strike (ATM - ATR)
            - pe_buy: Put buy strike (ATM - ATR - gap)
        """
        if spot is None:
            spot, _, _ = self.get_spot_and_range(symbol)
        
        if spot is None:
            return None
        
        gap = self.STRIKE_GAP.get(symbol, 50)
        atr = self.estimate_atr(symbol)
        distance = atr * multiplier
        
        # Round to nearest strike
        atm = int(round(spot / gap) * gap)
        ce_sell = atm + int(round(distance / gap) * gap)
        pe_sell = atm - int(round(distance / gap) * gap)
        
        # Ensure minimum distance of 1 gap
        ce_sell = max(ce_sell, atm + gap)
        pe_sell = min(pe_sell, atm - gap)
        
        # Buy strikes are 1 gap further
        ce_buy = ce_sell + gap
        pe_buy = pe_sell - gap
        
        return {
            'symbol': symbol,
            'spot': spot,
            'atm': atm,
            'atr': atr,
            'atr_pct': (atr / spot) * 100,
            'distance': distance,
            
            # Iron Condor strikes
            'ce_sell': ce_sell,
            'ce_buy': ce_buy,
            'pe_sell': pe_sell,
            'pe_buy': pe_buy,
            
            # Widths
            'call_spread_width': ce_buy - ce_sell,
            'put_spread_width': pe_sell - pe_buy,
            'total_width': (ce_sell - atm) + (atm - pe_sell),
        }
    
    def get_strike_analysis(self, symbol: str) -> dict:
        """Get complete strike analysis with recommendations"""
        
        strikes = self.get_optimal_strikes(symbol)
        
        if not strikes:
            return {
                'symbol': symbol,
                'available': False,
                'message': 'Unable to calculate strikes',
            }
        
        # Analyze
        atr_pct = strikes['atr_pct']
        
        if atr_pct < 0.5:
            vol_condition = 'LOW'
            recommendation = 'Narrow strikes OK, higher theta'
        elif atr_pct < 0.8:
            vol_condition = 'NORMAL'
            recommendation = 'Standard ATR-based strikes'
        else:
            vol_condition = 'HIGH'
            recommendation = 'Wider strikes for safety'
        
        return {
            'symbol': symbol,
            'available': True,
            'spot': strikes['spot'],
            'atm': strikes['atm'],
            'atr': strikes['atr'],
            'atr_pct': atr_pct,
            'volatility': vol_condition,
            'recommendation': recommendation,
            
            'ce_sell': strikes['ce_sell'],
            'ce_buy': strikes['ce_buy'],
            'pe_sell': strikes['pe_sell'],
            'pe_buy': strikes['pe_buy'],
            
            'iron_condor_width': strikes['total_width'],
        }


# Singleton
_calculator = None


def get_calculator() -> ATRCalculator:
    global _calculator
    if _calculator is None:
        _calculator = ATRCalculator()
    return _calculator


def get_atr(symbol: str) -> float:
    """Get estimated ATR"""
    return get_calculator().estimate_atr(symbol)


def get_optimal_strikes(symbol: str, spot: float = None) -> Optional[dict]:
    """Get optimal strikes based on ATR"""
    return get_calculator().get_optimal_strikes(symbol, spot)


def get_strike_analysis(symbol: str) -> dict:
    """Get strike analysis"""
    return get_calculator().get_strike_analysis(symbol)


if __name__ == "__main__":
    print("="*60)
    print("       ATR-BASED STRIKE SELECTION")
    print("="*60)
    
    for symbol in ['NIFTY', 'BANKNIFTY']:
        print(f"\n{symbol}:")
        
        analysis = get_strike_analysis(symbol)
        
        if analysis['available']:
            print(f"  Spot: ₹{analysis['spot']:,.2f}")
            print(f"  ATM: {analysis['atm']}")
            print(f"  ATR: {analysis['atr']:.0f} ({analysis['atr_pct']:.2f}%)")
            print(f"  Volatility: {analysis['volatility']}")
            print()
            print(f"  🔴 SELL CE: {analysis['ce_sell']}")
            print(f"  🟢 BUY CE:  {analysis['ce_buy']}")
            print(f"  🔴 SELL PE: {analysis['pe_sell']}")
            print(f"  🟢 BUY PE:  {analysis['pe_buy']}")
            print()
            print(f"  Iron Condor Width: {analysis['iron_condor_width']} points")
            print(f"  Recommendation: {analysis['recommendation']}")
        else:
            print(f"  {analysis['message']}")
