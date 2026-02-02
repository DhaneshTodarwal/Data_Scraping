"""
Notification System for Options Data Collection
Supports: Desktop Notifications + Telegram Alerts
"""
import os
import subprocess
import requests
from datetime import datetime, timezone, timedelta
import sys
from pathlib import Path

# Create IST timezone
IST = timezone(timedelta(hours=5, minutes=30))

# =============================================================================
# CONFIGURATION - UPDATE THESE VALUES
# =============================================================================

# Telegram Bot Configuration
# To get these:
# 1. Create bot: Message @BotFather on Telegram, send /newbot
# 2. Copy the token BotFather gives you
# 3. Get your chat ID: Message your bot, then visit:
#    https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
#    Look for "chat":{"id": YOUR_CHAT_ID}

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8435399514:AAExJBLy-Qouu7ousURDDDmZwHxHskNJHLg")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1700864260")

# =============================================================================
# DESKTOP NOTIFICATIONS (Linux)
# =============================================================================

def send_desktop_notification(title: str, message: str, urgency: str = "normal"):
    """
    Send desktop notification using notify-send (Linux)
    
    Args:
        title: Notification title
        message: Notification body
        urgency: low, normal, or critical
    """
    try:
        # For Linux with notify-send
        subprocess.run([
            "notify-send",
            "-u", urgency,
            "-t", "10000",  # 10 seconds
            "-i", "dialog-information",
            title,
            message
        ], check=False, env={
            **os.environ,
            "DISPLAY": ":0",
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{os.getuid()}/bus"
        })
        print(f"✅ Desktop notification sent: {title}")
        return True
    except Exception as e:
        print(f"⚠️ Desktop notification failed: {e}")
        return False


# =============================================================================
# TELEGRAM NOTIFICATIONS
# =============================================================================

def send_telegram_message(message: str) -> bool:
    """
    Send message via Telegram bot
    
    Args:
        message: Message text (supports HTML formatting)
        
    Returns:
        True if sent successfully
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured. Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID")
        return False
    
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, data=data, timeout=10)
        
        if response.status_code == 200:
            print("✅ Telegram message sent successfully")
            return True
        else:
            print(f"⚠️ Telegram API error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"⚠️ Telegram error: {e}")
        return False


# =============================================================================
# NOTIFICATION TEMPLATES
# =============================================================================

def notify_collection_started():
    """Notify when data collection starts"""
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    
    # Desktop notification
    send_desktop_notification(
        "📊 Options Data Collection Started",
        f"Collecting NIFTY & BANKNIFTY data...\n{now}",
        "normal"
    )
    
    # Telegram notification
    telegram_msg = f"""
🚀 <b>Options Data Collection Started</b>

📅 Date: {now}
📈 Indices: NIFTY, BANKNIFTY
⏳ Status: In Progress...
"""
    send_telegram_message(telegram_msg)


def notify_collection_success(nifty_data: dict, banknifty_data: dict):
    """Notify when data collection completes successfully"""
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    
    # Desktop notification
    desktop_msg = f"""
NIFTY: {nifty_data.get('strikes_count', 0)} strikes collected
BANKNIFTY: {banknifty_data.get('strikes_count', 0)} strikes collected
"""
    send_desktop_notification(
        "✅ Options Data Collection Complete!",
        desktop_msg,
        "normal"
    )
    
    # Telegram notification with detailed info
    telegram_msg = f"""
✅ <b>Options Data Collection Complete!</b>

📅 <b>Date:</b> {now}

📈 <b>NIFTY</b>
• Spot: ₹{nifty_data.get('spot_price', 'N/A')}
• ATM: {nifty_data.get('atm_strike', 'N/A')}
• Strikes: {nifty_data.get('strikes_count', 0)}
• Option Chain: {'✅' if nifty_data.get('option_chain_saved') else '❌'}

📈 <b>BANKNIFTY</b>
• Spot: ₹{banknifty_data.get('spot_price', 'N/A')}
• ATM: {banknifty_data.get('atm_strike', 'N/A')}
• Strikes: {banknifty_data.get('strikes_count', 0)}
• Option Chain: {'✅' if banknifty_data.get('option_chain_saved') else '❌'}

💾 Data saved to: options_data/
"""
    send_telegram_message(telegram_msg)


def notify_collection_failed(error: str):
    """Notify when data collection fails"""
    now = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")
    
    # Desktop notification (critical)
    send_desktop_notification(
        "❌ Options Data Collection FAILED!",
        f"Error: {error[:100]}",
        "critical"
    )
    
    # Telegram notification
    telegram_msg = f"""
❌ <b>Options Data Collection FAILED!</b>

📅 <b>Date:</b> {now}
⚠️ <b>Error:</b> {error}

Please check logs: logs/automation.log
"""
    send_telegram_message(telegram_msg)


def notify_market_summary(nifty_spot: float, banknifty_spot: float, nifty_pcr: float, banknifty_pcr: float):
    """Send daily market summary"""
    now = datetime.now(IST).strftime("%Y-%m-%d")
    
    # Determine market sentiment
    nifty_sentiment = "🟢 Bullish" if nifty_pcr < 1 else "🔴 Bearish" if nifty_pcr > 1.2 else "🟡 Neutral"
    banknifty_sentiment = "🟢 Bullish" if banknifty_pcr < 1 else "🔴 Bearish" if banknifty_pcr > 1.2 else "🟡 Neutral"
    
    telegram_msg = f"""
📊 <b>Daily Options Market Summary</b>
📅 {now}

<b>NIFTY</b>
• Spot: ₹{nifty_spot:,.2f}
• PCR: {nifty_pcr:.2f}
• Sentiment: {nifty_sentiment}

<b>BANKNIFTY</b>
• Spot: ₹{banknifty_spot:,.2f}
• PCR: {banknifty_pcr:.2f}
• Sentiment: {banknifty_sentiment}
"""
    send_telegram_message(telegram_msg)
    send_desktop_notification("📊 Daily Market Summary", f"NIFTY: ₹{nifty_spot:,.0f} | BN: ₹{banknifty_spot:,.0f}")


# =============================================================================
# TEST NOTIFICATIONS
# =============================================================================

if __name__ == "__main__":
    print("\n=== Testing Notification System ===\n")
    
    # Test desktop notification
    print("1. Testing Desktop Notification...")
    send_desktop_notification(
        "🧪 Test Notification",
        "Options Data Collection system is working!",
        "normal"
    )
    
    # Test Telegram (if configured)
    print("\n2. Testing Telegram Notification...")
    if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
        send_telegram_message("🧪 <b>Test Message</b>\n\nOptions Data Collection system is working!")
    else:
        print("⚠️ Telegram not configured.")
        print("   To enable Telegram alerts:")
        print("   1. Create a bot via @BotFather on Telegram")
        print("   2. Get your chat ID")
        print("   3. Set environment variables:")
        print("      export TELEGRAM_BOT_TOKEN='your_token'")
        print("      export TELEGRAM_CHAT_ID='your_chat_id'")
    
    print("\n✅ Notification system test complete!")
