"""
Market calendar utility - checks for trading days and holidays
"""
from datetime import datetime, timedelta
from typing import List
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import IST

# NSE Holidays for 2026 (update annually)
# Source: NSE website
NSE_HOLIDAYS_2026 = [
    "2026-01-26",  # Republic Day
    "2026-03-10",  # Maha Shivaratri
    "2026-03-17",  # Holi
    "2026-04-02",  # Ram Navami
    "2026-04-03",  # Good Friday
    "2026-04-06",  # Mahavir Jayanti
    "2026-04-14",  # Dr. Ambedkar Jayanti
    "2026-05-01",  # Maharashtra Day
    "2026-05-25",  # Buddha Purnima
    "2026-07-07",  # Muharram
    "2026-08-15",  # Independence Day
    "2026-08-16",  # Parsi New Year
    "2026-09-15",  # Milad-un-Nabi
    "2026-10-02",  # Gandhi Jayanti
    "2026-10-21",  # Dussehra
    "2026-11-09",  # Diwali (Laxmi Puja)
    "2026-11-10",  # Diwali (Balipratipada)
    "2026-11-30",  # Guru Nanak Jayanti
    "2026-12-25",  # Christmas
]

def is_trading_day(date: datetime = None) -> bool:
    """
    Check if the given date is a trading day (not weekend, not holiday)
    
    Args:
        date: Date to check (defaults to today)
        
    Returns:
        True if trading day, False otherwise
    """
    if date is None:
        date = datetime.now(IST)
    
    # Check if weekend (Saturday=5, Sunday=6)
    if date.weekday() >= 5:
        return False
    
    # Check if holiday
    date_str = date.strftime("%Y-%m-%d")
    if date_str in NSE_HOLIDAYS_2026:
        return False
    
    return True

def get_next_trading_day(date: datetime = None) -> datetime:
    """
    Get the next trading day from the given date
    
    Args:
        date: Starting date (defaults to today)
        
    Returns:
        Next trading day
    """
    if date is None:
        date = datetime.now(IST)
    
    next_day = date + timedelta(days=1)
    while not is_trading_day(next_day):
        next_day += timedelta(days=1)
    
    return next_day

def get_previous_trading_day(date: datetime = None) -> datetime:
    """
    Get the previous trading day from the given date
    
    Args:
        date: Starting date (defaults to today)
        
    Returns:
        Previous trading day
    """
    if date is None:
        date = datetime.now(IST)
    
    prev_day = date - timedelta(days=1)
    while not is_trading_day(prev_day):
        prev_day -= timedelta(days=1)
    
    return prev_day

def get_trading_days_in_range(start_date: datetime, end_date: datetime) -> List[datetime]:
    """
    Get all trading days between start and end dates (inclusive)
    
    Args:
        start_date: Start date
        end_date: End date
        
    Returns:
        List of trading days
    """
    trading_days = []
    current = start_date
    
    while current <= end_date:
        if is_trading_day(current):
            trading_days.append(current)
        current += timedelta(days=1)
    
    return trading_days

def get_next_expiry(index: str, from_date: datetime = None) -> datetime:
    """
    Get the next expiry date for an index
    
    Args:
        index: "NIFTY" or "BANKNIFTY"
        from_date: Starting date (defaults to today)
        
    Returns:
        Next expiry date
    """
    if from_date is None:
        from_date = datetime.now(IST)
    
    # NIFTY: Weekly expiry on Tuesday
    # BANKNIFTY: Monthly expiry on last Tuesday
    
    current = from_date
    
    if index.upper() == "NIFTY":
        # Find next Tuesday
        days_until_tuesday = (1 - current.weekday()) % 7
        if days_until_tuesday == 0 and current.hour >= 15:
            days_until_tuesday = 7
        next_expiry = current + timedelta(days=days_until_tuesday)
    else:
        # Find last Tuesday of current/next month
        # Move to next month if we are past last Tuesday
        month = current.month
        year = current.year
        
        # Find last Tuesday of current month
        if month == 12:
            next_month = datetime(year + 1, 1, 1, tzinfo=IST)
        else:
            next_month = datetime(year, month + 1, 1, tzinfo=IST)
        
        last_day = next_month - timedelta(days=1)
        
        # Find last Tuesday
        days_since_tuesday = (last_day.weekday() - 1) % 7
        last_tuesday = last_day - timedelta(days=days_since_tuesday)
        
        if last_tuesday <= current:
            # Move to next month
            if month == 12:
                month = 1
                year += 1
            else:
                month += 1
            
            if month == 12:
                next_month = datetime(year + 1, 1, 1, tzinfo=IST)
            else:
                next_month = datetime(year, month + 1, 1, tzinfo=IST)
            
            last_day = next_month - timedelta(days=1)
            days_since_tuesday = (last_day.weekday() - 1) % 7
            last_tuesday = last_day - timedelta(days=days_since_tuesday)
        
        next_expiry = last_tuesday
    
    # Adjust for holidays
    while not is_trading_day(next_expiry):
        next_expiry = get_previous_trading_day(next_expiry)
    
    return next_expiry


if __name__ == "__main__":
    # Test the functions
    today = datetime.now(IST)
    print(f"Today: {today.strftime('%Y-%m-%d %A')}")
    print(f"Is trading day: {is_trading_day(today)}")
    print(f"Next NIFTY expiry: {get_next_expiry('NIFTY')}")
    print(f"Next BANKNIFTY expiry: {get_next_expiry('BANKNIFTY')}")
