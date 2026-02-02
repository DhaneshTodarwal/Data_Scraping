"""
Event Calendar Filter
======================
Identifies high-risk trading days and filters trades accordingly

Events to avoid:
- RBI Policy days
- Budget day
- Monthly expiry (last Thursday)
- Major economic events
"""
import sys
from pathlib import Path
from datetime import datetime, date, timezone, timedelta
from typing import List, Tuple
from enum import Enum

IST = timezone(timedelta(hours=5, minutes=30))


class EventRisk(Enum):
    """Event risk levels"""
    NONE = "NONE"           # Normal day
    LOW = "LOW"             # Minor event
    MEDIUM = "MEDIUM"       # Important event
    HIGH = "HIGH"           # Major event - reduce size
    EXTREME = "EXTREME"     # Critical event - no trading


class EventCalendar:
    """Market event calendar for trading filters"""
    
    def __init__(self):
        # 2026 major events (manually maintained)
        self.major_events = {
            # RBI Monetary Policy dates
            '2026-02-05': ('RBI Policy', EventRisk.HIGH),
            '2026-04-08': ('RBI Policy', EventRisk.HIGH),
            '2026-06-04': ('RBI Policy', EventRisk.HIGH),
            '2026-08-05': ('RBI Policy', EventRisk.HIGH),
            '2026-10-07': ('RBI Policy', EventRisk.HIGH),
            '2026-12-02': ('RBI Policy', EventRisk.HIGH),
            
            # Budget
            '2026-02-01': ('Union Budget', EventRisk.EXTREME),
            
            # Major US events
            '2026-01-29': ('Fed Meeting', EventRisk.MEDIUM),
            '2026-03-18': ('Fed Meeting', EventRisk.MEDIUM),
            '2026-05-06': ('Fed Meeting', EventRisk.MEDIUM),
            '2026-06-17': ('Fed Meeting', EventRisk.MEDIUM),
            
            # US Elections, etc.
            '2026-11-03': ('US Elections', EventRisk.HIGH),
        }
        
        # Weekly expiry days
        self.expiry_days = {
            0: 'MIDCPNIFTY',  # Monday
            1: 'FINNIFTY',    # Tuesday
            2: 'BANKNIFTY',   # Wednesday
            3: 'NIFTY',       # Thursday
        }
    
    def is_expiry_day(self, check_date: date = None) -> Tuple[bool, str]:
        """Check if today is an expiry day"""
        if check_date is None:
            check_date = datetime.now(IST).date()
        
        weekday = check_date.weekday()
        
        if weekday in self.expiry_days:
            # Also check if it's monthly expiry (last week of month)
            next_week = check_date + timedelta(days=7)
            is_monthly = next_week.month != check_date.month
            
            symbol = self.expiry_days[weekday]
            expiry_type = "Monthly" if is_monthly else "Weekly"
            
            return True, f"{expiry_type} {symbol} expiry"
        
        return False, ""
    
    def get_event_risk(self, check_date: date = None) -> Tuple[EventRisk, str]:
        """Get event risk level for a date"""
        if check_date is None:
            check_date = datetime.now(IST).date()
        
        date_str = check_date.strftime('%Y-%m-%d')
        
        # Check major events
        if date_str in self.major_events:
            event_name, risk = self.major_events[date_str]
            return risk, event_name
        
        # Check expiry
        is_expiry, expiry_info = self.is_expiry_day(check_date)
        if is_expiry:
            if "Monthly" in expiry_info:
                return EventRisk.HIGH, expiry_info
            return EventRisk.MEDIUM, expiry_info
        
        return EventRisk.NONE, "Normal trading day"
    
    def should_trade(self, check_date: date = None) -> Tuple[bool, str]:
        """Check if we should trade today"""
        risk, event = self.get_event_risk(check_date)
        
        if risk == EventRisk.EXTREME:
            return False, f"❌ No trading - {event}"
        elif risk == EventRisk.HIGH:
            return True, f"⚠️ Caution - {event}. Reduce positions."
        elif risk == EventRisk.MEDIUM:
            return True, f"📅 {event}. Trade with awareness."
        else:
            return True, f"✅ {event}. Normal trading."
    
    def get_position_multiplier(self, check_date: date = None) -> float:
        """Get position multiplier based on event risk"""
        risk, _ = self.get_event_risk(check_date)
        
        multipliers = {
            EventRisk.NONE: 1.0,
            EventRisk.LOW: 1.0,
            EventRisk.MEDIUM: 0.7,
            EventRisk.HIGH: 0.5,
            EventRisk.EXTREME: 0.0,
        }
        
        return multipliers.get(risk, 1.0)
    
    def get_upcoming_events(self, days: int = 7) -> List[dict]:
        """Get upcoming events in next N days"""
        today = datetime.now(IST).date()
        events = []
        
        for i in range(days):
            check_date = today + timedelta(days=i)
            risk, event = self.get_event_risk(check_date)
            
            if risk != EventRisk.NONE:
                events.append({
                    'date': check_date.strftime('%Y-%m-%d'),
                    'day': check_date.strftime('%A'),
                    'event': event,
                    'risk': risk.value,
                })
        
        return events
    
    def get_today_analysis(self) -> dict:
        """Get complete analysis for today"""
        today = datetime.now(IST).date()
        risk, event = self.get_event_risk(today)
        should_trade, msg = self.should_trade(today)
        mult = self.get_position_multiplier(today)
        
        return {
            'date': today.strftime('%Y-%m-%d'),
            'day': today.strftime('%A'),
            'event': event,
            'risk': risk.value,
            'should_trade': should_trade,
            'message': msg,
            'position_multiplier': mult,
        }


# Singleton
_calendar = None


def get_calendar() -> EventCalendar:
    global _calendar
    if _calendar is None:
        _calendar = EventCalendar()
    return _calendar


def should_trade_today() -> Tuple[bool, str]:
    """Check if we should trade today"""
    return get_calendar().should_trade()


def get_event_analysis() -> dict:
    """Get today's event analysis"""
    return get_calendar().get_today_analysis()


def get_upcoming_events(days: int = 7) -> List[dict]:
    """Get upcoming events"""
    return get_calendar().get_upcoming_events(days)


if __name__ == "__main__":
    print("="*50)
    print("       EVENT CALENDAR")
    print("="*50)
    
    analysis = get_event_analysis()
    
    print(f"\nDate: {analysis['date']} ({analysis['day']})")
    print(f"Event: {analysis['event']}")
    print(f"Risk: {analysis['risk']}")
    print(f"Should trade: {analysis['should_trade']}")
    print(f"Message: {analysis['message']}")
    print(f"Position multiplier: {analysis['position_multiplier']}x")
    
    print("\n" + "="*50)
    print("UPCOMING EVENTS (Next 7 days)")
    print("="*50)
    
    for event in get_upcoming_events(7):
        print(f"  {event['date']} ({event['day'][:3]}): {event['event']} [{event['risk']}]")
