#!/bin/bash
# =============================================================================
# SCANNER WATCHDOG - Auto Restart if Scanner Stopped
# =============================================================================
# This script checks every 5 minutes if scanner is running
# If not running during market hours, it restarts the scanner
# Also checks network connectivity to detect internet issues
# =============================================================================

PROJECT_DIR="/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping"
LOG_FILE="$PROJECT_DIR/logs/watchdog.log"
SCANNER_SCRIPT="$PROJECT_DIR/analysis/realtime_scanner.py"
NETWORK_MONITOR="$PROJECT_DIR/scripts/network_monitor.py"

# Get current time
HOUR=$(date +%H)
MINUTE=$(date +%M)
DAY=$(date +%u)  # 1=Monday, 7=Sunday

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
}

# Check network connectivity (using wget instead of ping - ping is often blocked)
check_network() {
    # Try wget to Google (more reliable than ping which can be blocked)
    if wget -q --spider --timeout=5 http://www.google.com 2>/dev/null; then
        return 0  # Network OK
    fi
    
    # Retry once with different host
    if wget -q --spider --timeout=5 http://www.bing.com 2>/dev/null; then
        return 0  # Network OK
    fi
    
    return 1  # Network DOWN
}

# Check if it's a trading day (Monday-Friday)
if [ "$DAY" -gt 5 ]; then
    exit 0  # Weekend, do nothing
fi

# Check if it's market hours (9:18 AM - 3:30 PM)
CURRENT_TIME=$((HOUR * 60 + MINUTE))
MARKET_START=$((9 * 60 + 18))   # 9:18 AM
MARKET_END=$((15 * 60 + 30))     # 3:30 PM

if [ "$CURRENT_TIME" -lt "$MARKET_START" ] || [ "$CURRENT_TIME" -gt "$MARKET_END" ]; then
    exit 0  # Outside market hours, do nothing
fi

# First check network connectivity
if ! check_network; then
    log "🌐 NETWORK DOWN - Cannot reach API"
    
    # Run network monitor to send alert (if not already alerting)
    if [ -f "$NETWORK_MONITOR" ]; then
        python3 "$NETWORK_MONITOR" --once 2>/dev/null
    fi
    
    # Send Telegram notification about network issue
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR/scripts')
try:
    from notifications import send_telegram_message
    send_telegram_message('🌐 <b>NETWORK DOWN</b>\n\nInternet connectivity lost at $(date \"+%H:%M:%S\")\n\n⚠️ <b>Data collection is NOT working!</b>\n\nPlease check your internet connection.')
except:
    pass
" 2>/dev/null
    
    exit 1  # Network is down, don't try to restart scanner
fi

# Check if scanner is running
if pgrep -f "realtime_scanner.py" > /dev/null; then
    # Scanner is running, all good
    exit 0
else
    # Scanner is NOT running - restart it!
    log "⚠️ Scanner not running - RESTARTING..."
    
    # Start scanner in background
    cd "$PROJECT_DIR/analysis"
    nohup python3 realtime_scanner.py --run >> "$PROJECT_DIR/logs/scanner.log" 2>&1 &
    
    log "✅ Scanner restarted (PID: $!)"
    
    # Send Telegram notification
    python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR/scripts')
from notifications import send_telegram_message
send_telegram_message('🔄 <b>SCANNER AUTO-RESTARTED</b>\n\nScanner was stopped (laptop sleep/close?)\nAuto-restarted at $(date \"+%H:%M:%S\")\n\n✅ Now scanning again!')
" 2>/dev/null
    
fi
