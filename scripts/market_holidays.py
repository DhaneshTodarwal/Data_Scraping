#!/usr/bin/env python3
"""
NSE Market Holidays Utility
==========================
Defines trading holidays for NSE/BSE and checks if a given date is a non-trading day.
Sends Telegram holiday alerts once per day to avoid spamming the user.
"""

import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("MarketHolidays")

# Indian Standard Time (IST)
IST = timezone(timedelta(hours=5, minutes=30))

# NSE/BSE trading holidays for 2026
NSE_HOLIDAYS_2026 = {
    "2026-01-26": "Republic Day",
    "2026-03-03": "Holi",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas"
}

# Weekend holidays in 2026 (usually closed, listed for completeness)
NSE_WEEKEND_HOLIDAYS_2026 = {
    "2026-02-15": "Mahashivratri",
    "2026-03-21": "Id-Ul-Fitr (Ramzan Id)",
    "2026-08-15": "Independence Day",
    "2026-11-08": "Diwali – Laxmi Pujan (Muhurat Trading only)"
}


def get_market_status(dt: Optional[datetime] = None) -> Tuple[bool, str]:
    """
    Checks if a given datetime is a market holiday or weekend.
    
    Returns:
        Tuple[bool, str]: (is_holiday, reason_name)
    """
    if dt is None:
        dt = datetime.now(IST)
        
    date_str = dt.strftime("%Y-%m-%d")
    weekday = dt.weekday()  # Mon=0, Tue=1, ..., Sat=5, Sun=6
    
    # 1. Check if it's in the scheduled holiday list
    if date_str in NSE_HOLIDAYS_2026:
        return True, NSE_HOLIDAYS_2026[date_str]
        
    # 2. Check if it's a weekend (Sat/Sun)
    # Special exception for Muhurat trading on Sunday, November 8, 2026 (typically 1 hour session)
    if date_str == "2026-11-08":
        return False, "Muhurat Trading"
        
    if weekday >= 5:
        day_name = dt.strftime("%A")
        weekend_holiday = NSE_WEEKEND_HOLIDAYS_2026.get(date_str)
        if weekend_holiday:
            return True, f"{day_name} ({weekend_holiday})"
        return True, f"Weekend ({day_name})"
        
    return False, "Trading Day"


def send_holiday_greeting_once(alert_engine, log_dir: Path, dt: Optional[datetime] = None) -> bool:
    """
    Sends a holiday greeting to Telegram if today is a holiday and it hasn't been sent yet.
    
    Returns:
        bool: True if greeting was sent, False otherwise.
    """
    if dt is None:
        dt = datetime.now(IST)
        
    is_holiday, reason = get_market_status(dt)
    if not is_holiday:
        return False
        
    today_str = dt.strftime("%Y%m%d")
    sentinel_file = log_dir / f"holiday_sent_{today_str}.txt"
    
    if sentinel_file.exists():
        logger.info(f"Holiday alert for {reason} already sent today.")
        return False
        
    # Send the message
    msg = (
        f"📅 <b>NSE/BSE Market Holiday</b>\n\n"
        f"Today is <b>{reason}</b>. The stock market is closed.\n\n"
        f"✨ <i>Enjoy your day!</i> ✨"
    )
    
    success = False
    if hasattr(alert_engine, "send_message"):
        success = alert_engine.send_message(msg)
    elif callable(alert_engine):
        success = alert_engine(msg)
        
    if success:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            with open(sentinel_file, "w") as f:
                f.write(f"Sent holiday alert for {reason} at {datetime.now(IST).isoformat()}\n")
            logger.info(f"Sent holiday alert for {reason} and created sentinel file.")
        except Exception as e:
            logger.error(f"Failed to create sentinel file: {e}")
            
    return success
