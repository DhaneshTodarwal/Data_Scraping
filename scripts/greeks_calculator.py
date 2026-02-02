"""
Greeks Calculator
=================
Calculate option Greeks (Delta, Gamma, Theta, Vega, Rho) using Black-Scholes model.

Input: OHLCV data + estimated IV
Output: Greeks for each strike

Created: 2026-01-17
"""

import json
import math
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List
from scipy.stats import norm

# Setup Logging
BASE_DIR = Path(__file__).parent.parent
LOG_DIR = BASE_DIR / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / f"greeks_{datetime.now().strftime('%Y%m%d')}.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("GreeksCalculator")

# Constants
RISK_FREE_RATE = 0.065  # 6.5% (approximate India risk-free rate)
TRADING_DAYS_PER_YEAR = 252


class BlackScholesCalculator:
    """Calculate option Greeks using Black-Scholes model."""
    
    @staticmethod
    def calculate_d1_d2(spot: float, strike: float, time_to_expiry: float, 
                        volatility: float, risk_free_rate: float = RISK_FREE_RATE):
        """Calculate d1 and d2 for Black-Scholes formula."""
        if time_to_expiry <= 0:
            return 0, 0
        
        d1 = (math.log(spot / strike) + (risk_free_rate + 0.5 * volatility ** 2) * time_to_expiry) / (volatility * math.sqrt(time_to_expiry))
        d2 = d1 - volatility * math.sqrt(time_to_expiry)
        
        return d1, d2
    
    @staticmethod
    def calculate_call_price(spot: float, strike: float, time_to_expiry: float,
                              volatility: float, risk_free_rate: float = RISK_FREE_RATE):
        """Calculate theoretical call option price."""
        if time_to_expiry <= 0:
            return max(spot - strike, 0)
        
        d1, d2 = BlackScholesCalculator.calculate_d1_d2(spot, strike, time_to_expiry, volatility, risk_free_rate)
        
        call_price = spot * norm.cdf(d1) - strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
        return call_price
    
    @staticmethod
    def calculate_put_price(spot: float, strike: float, time_to_expiry: float,
                             volatility: float, risk_free_rate: float = RISK_FREE_RATE):
        """Calculate theoretical put option price."""
        if time_to_expiry <= 0:
            return max(strike - spot, 0)
        
        d1, d2 = BlackScholesCalculator.calculate_d1_d2(spot, strike, time_to_expiry, volatility, risk_free_rate)
        
        put_price = strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2) - spot * norm.cdf(-d1)
        return put_price
    
    @staticmethod
    def calculate_call_delta(spot: float, strike: float, time_to_expiry: float,
                              volatility: float, risk_free_rate: float = RISK_FREE_RATE):
        """Calculate call option delta."""
        if time_to_expiry <= 0:
            return 1.0 if spot > strike else 0.0
        
        d1, _ = BlackScholesCalculator.calculate_d1_d2(spot, strike, time_to_expiry, volatility, risk_free_rate)
        return norm.cdf(d1)
    
    @staticmethod
    def calculate_put_delta(spot: float, strike: float, time_to_expiry: float,
                             volatility: float, risk_free_rate: float = RISK_FREE_RATE):
        """Calculate put option delta."""
        if time_to_expiry <= 0:
            return -1.0 if spot < strike else 0.0
        
        d1, _ = BlackScholesCalculator.calculate_d1_d2(spot, strike, time_to_expiry, volatility, risk_free_rate)
        return norm.cdf(d1) - 1
    
    @staticmethod
    def calculate_gamma(spot: float, strike: float, time_to_expiry: float,
                        volatility: float, risk_free_rate: float = RISK_FREE_RATE):
        """Calculate gamma (same for call and put)."""
        if time_to_expiry <= 0:
            return 0.0
        
        d1, _ = BlackScholesCalculator.calculate_d1_d2(spot, strike, time_to_expiry, volatility, risk_free_rate)
        return norm.pdf(d1) / (spot * volatility * math.sqrt(time_to_expiry))
    
    @staticmethod
    def calculate_vega(spot: float, strike: float, time_to_expiry: float,
                       volatility: float, risk_free_rate: float = RISK_FREE_RATE):
        """Calculate vega (same for call and put)."""
        if time_to_expiry <= 0:
            return 0.0
        
        d1, _ = BlackScholesCalculator.calculate_d1_d2(spot, strike, time_to_expiry, volatility, risk_free_rate)
        return spot * norm.pdf(d1) * math.sqrt(time_to_expiry) / 100  # Divided by 100 for 1% change
    
    @staticmethod
    def calculate_call_theta(spot: float, strike: float, time_to_expiry: float,
                              volatility: float, risk_free_rate: float = RISK_FREE_RATE):
        """Calculate call option theta."""
        if time_to_expiry <= 0:
            return 0.0
        
        d1, d2 = BlackScholesCalculator.calculate_d1_d2(spot, strike, time_to_expiry, volatility, risk_free_rate)
        
        term1 = -(spot * norm.pdf(d1) * volatility) / (2 * math.sqrt(time_to_expiry))
        term2 = risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(d2)
        
        return (term1 - term2) / 365  # Per day
    
    @staticmethod
    def calculate_put_theta(spot: float, strike: float, time_to_expiry: float,
                             volatility: float, risk_free_rate: float = RISK_FREE_RATE):
        """Calculate put option theta."""
        if time_to_expiry <= 0:
            return 0.0
        
        d1, d2 = BlackScholesCalculator.calculate_d1_d2(spot, strike, time_to_expiry, volatility, risk_free_rate)
        
        term1 = -(spot * norm.pdf(d1) * volatility) / (2 * math.sqrt(time_to_expiry))
        term2 = risk_free_rate * strike * math.exp(-risk_free_rate * time_to_expiry) * norm.cdf(-d2)
        
        return (term1 + term2) / 365  # Per day
    
    @staticmethod
    def calculate_all_greeks(spot: float, strike: float, time_to_expiry: float,
                              volatility: float, option_type: str = 'CE',
                              risk_free_rate: float = RISK_FREE_RATE) -> Dict:
        """Calculate all Greeks for an option."""
        is_call = option_type.upper() == 'CE'
        
        if is_call:
            delta = BlackScholesCalculator.calculate_call_delta(spot, strike, time_to_expiry, volatility, risk_free_rate)
            theta = BlackScholesCalculator.calculate_call_theta(spot, strike, time_to_expiry, volatility, risk_free_rate)
            price = BlackScholesCalculator.calculate_call_price(spot, strike, time_to_expiry, volatility, risk_free_rate)
        else:
            delta = BlackScholesCalculator.calculate_put_delta(spot, strike, time_to_expiry, volatility, risk_free_rate)
            theta = BlackScholesCalculator.calculate_put_theta(spot, strike, time_to_expiry, volatility, risk_free_rate)
            price = BlackScholesCalculator.calculate_put_price(spot, strike, time_to_expiry, volatility, risk_free_rate)
        
        gamma = BlackScholesCalculator.calculate_gamma(spot, strike, time_to_expiry, volatility, risk_free_rate)
        vega = BlackScholesCalculator.calculate_vega(spot, strike, time_to_expiry, volatility, risk_free_rate)
        
        return {
            'theoretical_price': round(price, 2),
            'delta': round(delta, 4),
            'gamma': round(gamma, 6),
            'theta': round(theta, 2),
            'vega': round(vega, 2)
        }


def calculate_historical_volatility(ohlcv_data: List, period: int = 20) -> float:
    """
    Calculate historical volatility from OHLCV data.
    
    Args:
        ohlcv_data: List of [timestamp, open, high, low, close, volume]
        period: Number of periods for calculation
        
    Returns:
        Annualized volatility (as decimal, e.g., 0.18 for 18%)
    """
    if len(ohlcv_data) < period:
        return 0.20  # Default 20% if not enough data
    
    # Extract close prices
    closes = [float(candle[4]) for candle in ohlcv_data[-period:]]
    
    # Calculate log returns
    returns = [math.log(closes[i] / closes[i-1]) for i in range(1, len(closes))]
    
    # Calculate standard deviation
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / (len(returns) - 1)
    std_dev = math.sqrt(variance)
    
    # Annualize (assuming 375 minutes per trading day, 252 trading days)
    annualized_vol = std_dev * math.sqrt(375 * TRADING_DAYS_PER_YEAR)
    
    return round(annualized_vol, 4)


def estimate_implied_volatility_from_hv(historical_vol: float) -> float:
    """
    Estimate IV from historical volatility.
    Typically IV = HV * 1.1 to 1.3 (IV is usually higher due to uncertainty premium)
    """
    return round(historical_vol * 1.2, 4)  # 20% premium over HV


def get_days_to_expiry(expiry_str: str) -> int:
    """
    Calculate days to expiry from expiry string.
    
    Args:
        expiry_str: Format like '20-Jan-2026' or '2026-01-20'
    """
    try:
        # Try multiple formats
        for fmt in ['%d-%b-%Y', '%Y-%m-%d', '%d%b%Y']:
            try:
                expiry_date = datetime.strptime(expiry_str, fmt).date()
                today = datetime.now().date()
                days = (expiry_date - today).days
                return max(days, 1)  # At least 1 day
            except ValueError:
                continue
        
        logger.warning(f"Could not parse expiry: {expiry_str}, using default 7 days")
        return 7
        
    except Exception as e:
        logger.error(f"Error parsing expiry: {e}")
        return 7


def main():
    """Example usage."""
    logger.info("Greeks Calculator - Example")
    
    # Example calculation
    spot = 25700
    strike = 25700  # ATM
    iv = 0.18  # 18% implied volatility
    days_to_expiry = 4
    time_to_expiry = days_to_expiry / 365
    
    # Calculate call Greeks
    ce_greeks = BlackScholesCalculator.calculate_all_greeks(
        spot=spot,
        strike=strike,
        time_to_expiry=time_to_expiry,
        volatility=iv,
        option_type='CE'
    )
    
    # Calculate put Greeks
    pe_greeks = BlackScholesCalculator.calculate_all_greeks(
        spot=spot,
        strike=strike,
        time_to_expiry=time_to_expiry,
        volatility=iv,
        option_type='PE'
    )
    
    logger.info(f"\nSpot: {spot}, Strike: {strike}, IV: {iv*100}%, Days: {days_to_expiry}")
    logger.info(f"\nCall Greeks: {json.dumps(ce_greeks, indent=2)}")
    logger.info(f"\nPut Greeks: {json.dumps(pe_greeks, indent=2)}")


if __name__ == "__main__":
    main()
