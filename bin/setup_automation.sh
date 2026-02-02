#!/bin/bash
# =============================================================================
# AUTOMATION SETUP SCRIPT
# =============================================================================
# This script sets up cron jobs for automated trading alerts
# 
# What it does:
# - Runs signal scanner at specific times during market hours
# - Sends daily summary after market close
# - Does NOT affect your existing data collection
# =============================================================================

PROJECT_DIR="/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping"
PYTHON_PATH="/usr/bin/python3"
LOG_FILE="$PROJECT_DIR/logs/automation.log"

echo "=============================================="
echo "     TRADING AUTOMATION SETUP"
echo "=============================================="

# Create logs directory if not exists
mkdir -p "$PROJECT_DIR/logs"

# Check if cron service is running
if ! pgrep cron > /dev/null; then
    echo "⚠ Cron service not running. Starting..."
    sudo service cron start
fi

echo ""
echo "📋 The following schedules will be added:"
echo ""
echo "  🔍 09:45 - Scan for Straddle/Strangle signals"
echo "  🔍 10:15 - Scan for Straddle signals"
echo "  📊 15:35 - Send daily summary"
echo ""
echo "⚠ This will NOT affect your existing data collection!"
echo ""

read -p "Do you want to install these schedules? (y/n): " confirm

if [ "$confirm" != "y" ]; then
    echo "❌ Cancelled"
    exit 0
fi

# Create the cron entries
CRON_ENTRIES="
# Trading Automation - Signal Scanner (does not affect data collection)
# Scan at 09:45 for Straddle + Strangle signals
45 9 * * 1-5 cd \"$PROJECT_DIR/analysis\" && $PYTHON_PATH live_signal_scanner.py --once >> \"$LOG_FILE\" 2>&1

# Scan at 10:15 for Straddle signals
15 10 * * 1-5 cd \"$PROJECT_DIR/analysis\" && $PYTHON_PATH live_signal_scanner.py --once >> \"$LOG_FILE\" 2>&1

# Daily summary at 15:35
35 15 * * 1-5 cd \"$PROJECT_DIR/analysis\" && $PYTHON_PATH -c \"from alerts import send_daily_summary; send_daily_summary({'total_trades': 0, 'winners': 0, 'total_pnl': 0, 'win_rate': 0})\" >> \"$LOG_FILE\" 2>&1
"

# Add to crontab (preserving existing entries)
(crontab -l 2>/dev/null | grep -v "live_signal_scanner\|Trading Automation"; echo "$CRON_ENTRIES") | crontab -

echo ""
echo "✅ Automation schedules installed!"
echo ""
echo "📋 Current cron jobs:"
crontab -l | grep -A1 "Trading Automation\|live_signal"
echo ""
echo "📂 Logs will be saved to: $LOG_FILE"
echo ""
echo "🧪 To test manually:"
echo "   python3 analysis/live_signal_scanner.py --test"
echo ""
echo "🛑 To remove automation:"
echo "   crontab -e  (and delete the Trading Automation lines)"
