"""
Professional Exit Alerts System
================================
Handles all exit-related alerts:

1. Trailing Stop Loss Alerts (Dynamic)
2. Book Profit Alerts (Target reached)
3. Book Loss Alerts (SL hit)
4. Exit Reminders (approaching SL/Target)
5. Time-based Exit Reminders
6. Partial Profit Booking

This is the COMPLETE exit management system!
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta, time
from enum import Enum
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

try:
    from notifications import send_telegram_message, send_desktop_notification
    NOTIFICATIONS_AVAILABLE = True
except ImportError:
    NOTIFICATIONS_AVAILABLE = False

IST = timezone(timedelta(hours=5, minutes=30))


# =============================================================================
# ENUMS
# =============================================================================

class AlertType(Enum):
    TRAILING_SL = "Trailing SL"
    TARGET_HIT = "Target Hit"
    SL_HIT = "SL Hit"
    PARTIAL_PROFIT = "Partial Profit"
    EXIT_REMINDER = "Exit Reminder"
    TIME_EXIT = "Time Exit"
    SL_APPROACHING = "SL Approaching"
    TARGET_APPROACHING = "Target Approaching"


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class ActivePosition:
    """Track an active position"""
    position_id: str
    symbol: str
    strategy: str
    entry_time: datetime
    
    # Entry details
    entry_premium: float
    current_premium: float
    quantity: int
    lot_size: int
    
    # SL/Target
    initial_sl: float
    current_sl: float
    target: float
    
    # Trail settings
    trailing_enabled: bool = True
    trail_trigger_pct: float = 20  # Start trailing at 20% profit
    trail_step_pct: float = 10     # Move SL by 10% each step
    trail_count: int = 0
    
    # Status
    pnl: float = 0.0
    pnl_pct: float = 0.0
    status: str = "ACTIVE"


# =============================================================================
# PROFESSIONAL ALERT TEMPLATES
# =============================================================================

class ProExitAlerts:
    """Professional exit alert generator"""
    
    @staticmethod
    def send_alert(msg: str) -> bool:
        """Send alert to Telegram"""
        if NOTIFICATIONS_AVAILABLE:
            return send_telegram_message(msg)
        print(msg)
        return False
    
    # =========================================================================
    # TRAILING SL ALERTS
    # =========================================================================
    
    @staticmethod
    def trailing_sl_update(position: ActivePosition, old_sl: float, 
                            new_sl: float, reason: str = "Profit increased") -> str:
        """
        Professional trailing SL update alert
        """
        profit_locked = (position.entry_premium - new_sl) * position.quantity
        current_profit = (position.entry_premium - position.current_premium) * position.quantity
        
        msg = f"""
🔄 <b>TRAILING STOP LOSS UPDATE</b>

📈 <b>{position.symbol}</b> | {position.strategy}
⏰ {datetime.now(IST).strftime('%H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>✅ STOP LOSS MOVED UP!</b>

• Previous SL: ₹{old_sl:.2f}
• <b>NEW SL: ₹{new_sl:.2f}</b>
• SL Moved By: ₹{new_sl - old_sl:.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 CURRENT STATUS:</b>
• Entry Premium: ₹{position.entry_premium:.2f}
• Current Premium: ₹{position.current_premium:.2f}
• Current P&L: <b>₹{current_profit:,.0f}</b>

<b>🔒 PROFIT LOCKED:</b>
• Minimum Profit: ₹{profit_locked:,.0f}
• Trail Count: #{position.trail_count + 1}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📌 WHAT THIS MEANS:</b>
• If price reverses to ₹{new_sl:.2f}, exit with ₹{profit_locked:,.0f} profit
• System will trail again if profit increases
• Your downside is now protected!

💡 <b>ACTION:</b> Update SL in your broker to ₹{new_sl:.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return msg
    
    # =========================================================================
    # TARGET HIT ALERTS
    # =========================================================================
    
    @staticmethod
    def target_hit(position: ActivePosition, 
                   partial: bool = False, pct: int = 100) -> str:
        """
        Book full profit alert
        """
        final_pnl = (position.entry_premium - position.current_premium) * position.quantity
        roi = ((position.entry_premium - position.current_premium) / position.entry_premium) * 100
        
        if partial:
            title = f"🎯 BOOK {pct}% PROFIT"
            action = f"Exit {pct}% of position"
            qty = int(position.quantity * pct / 100)
        else:
            title = "🎯 TARGET HIT - BOOK FULL PROFIT"
            action = "Exit full position NOW"
            qty = position.quantity
        
        duration = datetime.now(IST) - position.entry_time
        hours = duration.seconds // 3600
        mins = (duration.seconds % 3600) // 60
        
        msg = f"""
{title}

📈 <b>{position.symbol}</b> | {position.strategy}
⏰ {datetime.now(IST).strftime('%H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🎉 CONGRATULATIONS!</b>
Target reached - Time to book profits!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 TRADE SUMMARY:</b>
• Entry: ₹{position.entry_premium:.2f}
• Exit: ₹{position.current_premium:.2f}
• <b>Profit: ₹{final_pnl:,.0f}</b>
• ROI: {roi:.1f}%
• Duration: {hours}h {mins}m

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🔴 ACTION REQUIRED:</b>
<b>{action}</b>

<b>Exit Order:</b>
• Symbol: {position.symbol}
• Qty: {qty}
• Price: ₹{position.current_premium:.2f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ <i>Execute immediately to lock profits!</i>
💰 <i>This is a winning trade!</i>
"""
        return msg
    
    # =========================================================================
    # STOP LOSS HIT ALERTS
    # =========================================================================
    
    @staticmethod
    def sl_hit(position: ActivePosition) -> str:
        """
        Book loss alert - SL hit
        """
        final_pnl = (position.entry_premium - position.current_premium) * position.quantity
        loss_pct = ((position.current_premium - position.entry_premium) / position.entry_premium) * 100
        
        duration = datetime.now(IST) - position.entry_time
        hours = duration.seconds // 3600
        mins = (duration.seconds % 3600) // 60
        
        msg = f"""
🛑 <b>STOP LOSS HIT - EXIT NOW</b>

📈 <b>{position.symbol}</b> | {position.strategy}
⏰ {datetime.now(IST).strftime('%H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>⚠️ STOP LOSS TRIGGERED</b>
Exit immediately to limit losses!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 TRADE SUMMARY:</b>
• Entry: ₹{position.entry_premium:.2f}
• SL Level: ₹{position.current_sl:.2f}
• Current: ₹{position.current_premium:.2f}
• <b>Loss: ₹{abs(final_pnl):,.0f}</b>
• Loss %: {loss_pct:.1f}%
• Duration: {hours}h {mins}m

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🔴 ACTION REQUIRED:</b>
<b>EXIT FULL POSITION NOW</b>

<b>Exit Order:</b>
• Symbol: {position.symbol}
• Qty: {position.quantity}
• Market Order

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📝 NOTES:</b>
• SL hit is normal in trading
• Risk was pre-defined
• Loss is within planned limit

💡 <i>Exit now, analyze later</i>
📊 <i>Review this trade tonight</i>
"""
        return msg
    
    # =========================================================================
    # EXIT REMINDERS (APPROACHING SL/TARGET)
    # =========================================================================
    
    @staticmethod
    def approaching_target(position: ActivePosition, distance_pct: float) -> str:
        """
        Alert when approaching target
        """
        current_profit = (position.entry_premium - position.current_premium) * position.quantity
        
        msg = f"""
🎯 <b>APPROACHING TARGET</b>

📈 <b>{position.symbol}</b> | {position.strategy}
⏰ {datetime.now(IST).strftime('%H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>Almost there! {distance_pct:.0f}% away from target</b>

• Current Premium: ₹{position.current_premium:.2f}
• Target Premium: ₹{position.target:.2f}
• Distance: ₹{position.current_premium - position.target:.2f}
• Current Profit: ₹{current_profit:,.0f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💡 SUGGESTED OPTIONS:</b>

1️⃣ <b>HOLD</b> - Wait for full target
   • Risk: Market may reverse
   • Reward: Full target profit

2️⃣ <b>PARTIAL EXIT</b> - Book 50% now
   • Lock some profit
   • Let rest run for target

3️⃣ <b>TRAIL SL</b> - Move SL higher
   • Protect current profits
   • Stay in trade

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔔 <i>Monitor closely - decision required soon</i>
"""
        return msg
    
    @staticmethod
    def approaching_sl(position: ActivePosition, distance_pct: float) -> str:
        """
        Warning when approaching SL
        """
        potential_loss = (position.current_sl - position.entry_premium) * position.quantity
        
        msg = f"""
⚠️ <b>WARNING: APPROACHING STOP LOSS</b>

📈 <b>{position.symbol}</b> | {position.strategy}
⏰ {datetime.now(IST).strftime('%H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>🚨 Only {distance_pct:.0f}% away from SL!</b>

• Current Premium: ₹{position.current_premium:.2f}
• Stop Loss: ₹{position.current_sl:.2f}
• Distance: ₹{position.current_sl - position.current_premium:.2f}
• Potential Loss: ₹{abs(potential_loss):,.0f}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💡 OPTIONS:</b>

1️⃣ <b>HOLD</b> - Wait for recovery
   • SL is your max planned loss
   • May recover

2️⃣ <b>EXIT NOW</b> - Smaller loss
   • Current loss < SL loss
   • Preserve capital

3️⃣ <b>ADJUST SL</b> - Widen SL
   • Only if analysis supports
   • Increases risk

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️ <i>Stay calm - stick to your plan</i>
📊 <i>SL is there for a reason</i>
"""
        return msg
    
    # =========================================================================
    # TIME-BASED EXIT REMINDERS
    # =========================================================================
    
    @staticmethod
    def time_exit_reminder(position: ActivePosition, minutes_left: int) -> str:
        """
        Time-based exit reminder
        """
        current_pnl = (position.entry_premium - position.current_premium) * position.quantity
        pnl_emoji = "🟢" if current_pnl >= 0 else "🔴"
        
        msg = f"""
⏰ <b>TIME EXIT REMINDER</b>

📈 <b>{position.symbol}</b> | {position.strategy}
⏰ {datetime.now(IST).strftime('%H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>⚠️ {minutes_left} MINUTES LEFT</b>
Exit before market close!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 CURRENT STATUS:</b>
• Current Premium: ₹{position.current_premium:.2f}
• {pnl_emoji} P&L: ₹{current_pnl:,.0f}

<b>🎯 Suggested Exit:</b>
• Price: ₹{position.current_premium:.2f}
• Qty: {position.quantity}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>⚠️ INTRADAY RULE:</b>
• Must exit before 3:25 PM
• Broker may square off at market

<b>🔴 ACTION: EXIT NOW</b>

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
        return msg
    
    # =========================================================================
    # PARTIAL PROFIT BOOKING
    # =========================================================================
    
    @staticmethod
    def partial_profit_suggestion(position: ActivePosition, 
                                   profit_pct: float) -> str:
        """
        Suggest partial profit booking
        """
        current_profit = (position.entry_premium - position.current_premium) * position.quantity
        half_qty = position.quantity // 2
        half_profit = current_profit // 2
        
        msg = f"""
💰 <b>PARTIAL PROFIT OPPORTUNITY</b>

📈 <b>{position.symbol}</b> | {position.strategy}
⏰ {datetime.now(IST).strftime('%H:%M:%S')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>✅ {profit_pct:.0f}% Profit Reached!</b>
Consider booking partial profits.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>📊 CURRENT STATUS:</b>
• Current Premium: ₹{position.current_premium:.2f}
• Total Profit: ₹{current_profit:,.0f}
• Profit %: {profit_pct:.1f}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>💡 PARTIAL EXIT SUGGESTION:</b>

<b>Exit 50%:</b>
• Qty: {half_qty}
• Profit: ₹{half_profit:,.0f}
• Remaining rides for target

<b>Benefits:</b>
• Lock ₹{half_profit:,.0f} guaranteed
• Remaining 50% can run risk-free
• No regret if reverses

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

<b>After Partial Exit:</b>
• Move SL to entry (cost basis)
• Rest of position = FREE TRADE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 <i>Decision is yours - both options are valid</i>
"""
        return msg


# =============================================================================
# POSITION TRACKER (for real-time monitoring)
# =============================================================================

class PositionTracker:
    """Track active positions and send alerts"""
    
    def __init__(self):
        self.positions: Dict[str, ActivePosition] = {}
        self.alerts = ProExitAlerts()
    
    def add_position(self, position: ActivePosition):
        """Add new position to tracking"""
        self.positions[position.position_id] = position
        print(f"✅ Tracking: {position.symbol} {position.strategy}")
    
    def update_premium(self, position_id: str, current_premium: float):
        """Update current premium and check for alerts"""
        if position_id not in self.positions:
            return
        
        pos = self.positions[position_id]
        pos.current_premium = current_premium
        
        # Calculate P&L
        pos.pnl = (pos.entry_premium - current_premium) * pos.quantity
        pos.pnl_pct = ((pos.entry_premium - current_premium) / pos.entry_premium) * 100
        
        # Check for alerts
        self._check_alerts(pos)
    
    def _check_alerts(self, pos: ActivePosition):
        """Check if any alerts need to be sent"""
        
        # 1. Check if target hit
        if pos.current_premium <= pos.target:
            msg = self.alerts.target_hit(pos)
            self.alerts.send_alert(msg)
            pos.status = "TARGET_HIT"
            return
        
        # 2. Check if SL hit
        if pos.current_premium >= pos.current_sl:
            msg = self.alerts.sl_hit(pos)
            self.alerts.send_alert(msg)
            pos.status = "SL_HIT"
            return
        
        # 3. Check for trailing SL
        if pos.trailing_enabled and pos.pnl_pct >= pos.trail_trigger_pct:
            new_sl = self._calculate_trail_sl(pos)
            if new_sl < pos.current_sl:
                old_sl = pos.current_sl
                pos.current_sl = new_sl
                pos.trail_count += 1
                pos.trail_trigger_pct += pos.trail_step_pct  # Next trigger
                
                msg = self.alerts.trailing_sl_update(pos, old_sl, new_sl)
                self.alerts.send_alert(msg)
        
        # 4. Check approaching target (within 10%)
        target_distance = (pos.current_premium - pos.target) / (pos.entry_premium - pos.target)
        if target_distance < 0.2 and pos.pnl_pct > 30:
            msg = self.alerts.approaching_target(pos, target_distance * 100)
            # Only send once
        
        # 5. Check approaching SL (within 10%)
        sl_distance = (pos.current_sl - pos.current_premium) / (pos.current_sl - pos.entry_premium)
        if sl_distance < 0.2:
            msg = self.alerts.approaching_sl(pos, sl_distance * 100)
        
        # 6. Check partial profit opportunity (at 25%, 50%)
        if pos.pnl_pct >= 25 and pos.trail_count == 0:
            msg = self.alerts.partial_profit_suggestion(pos, pos.pnl_pct)
    
    def _calculate_trail_sl(self, pos: ActivePosition) -> float:
        """Calculate new trailing SL"""
        # Move SL based on profit locked
        profit_to_lock = pos.pnl_pct - 10  # Lock profit minus buffer
        new_sl_premium = pos.entry_premium * (1 - profit_to_lock / 100)
        return new_sl_premium
    
    def check_time_exit(self):
        """Check for time-based exit reminders"""
        now = datetime.now(IST)
        
        if now.time() >= time(15, 15):
            minutes_left = (60 - now.minute) + (15 - now.hour - 1) * 60
            if minutes_left <= 15:
                for pos in self.positions.values():
                    if pos.status == "ACTIVE":
                        msg = self.alerts.time_exit_reminder(pos, minutes_left)
                        self.alerts.send_alert(msg)


# =============================================================================
# TEST FUNCTION
# =============================================================================

def send_test_exit_alerts():
    """Send test exit alerts"""
    
    # Create test position
    pos = ActivePosition(
        position_id="TEST_001",
        symbol="NIFTY",
        strategy="Short Straddle",
        entry_time=datetime.now(IST) - timedelta(hours=2),
        entry_premium=250.0,
        current_premium=175.0,  # In profit
        quantity=75,
        lot_size=75,
        initial_sl=325.0,
        current_sl=300.0,
        target=125.0,
        trailing_enabled=True,
    )
    
    alerts = ProExitAlerts()
    
    print("Sending test alerts...")
    
    # 1. Trailing SL update
    msg = alerts.trailing_sl_update(pos, 300.0, 250.0)
    alerts.send_alert(msg)
    
    print("✅ Trailing SL alert sent!")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='Exit Alerts System')
    parser.add_argument('--test', action='store_true', help='Send test alerts')
    
    args = parser.parse_args()
    
    if args.test:
        send_test_exit_alerts()
    else:
        print("Exit Alerts System")
        print("Usage: --test to send test alerts")
