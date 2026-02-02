#!/bin/bash
# =============================================================================
# AUTO-START SETUP FOR REAL-TIME SCANNER
# =============================================================================
# This script sets up automatic daily start of the trading scanner
# Scanner will start at 9:18 AM every weekday (Mon-Fri)
# =============================================================================

PROJECT_DIR="/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping"
PYTHON_PATH="/usr/bin/python3"
LOG_DIR="$PROJECT_DIR/logs"
LOG_FILE="$LOG_DIR/scanner.log"

echo "=============================================="
echo "   AUTO-START SETUP FOR TRADING SCANNER"
echo "=============================================="

# Create logs directory
mkdir -p "$LOG_DIR"

echo ""
echo "📋 This will set up:"
echo ""
echo "   🕘 9:18 AM - Start Real-Time Scanner"
echo "   📊 Runs until 3:25 PM automatically"
echo "   📱 All alerts sent to Telegram"
echo "   📝 Logs saved to: $LOG_DIR/"
echo ""
echo "   Days: Monday to Friday"
echo ""

# Create the scanner start script
cat > "$PROJECT_DIR/start_scanner.sh" << 'EOF'
#!/bin/bash
# Scanner Start Script
cd "/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping/analysis"
export PYTHONPATH="/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping:$PYTHONPATH"
/usr/bin/python3 realtime_scanner.py --run --interval 60 --confidence 60 --probability 55
EOF

chmod +x "$PROJECT_DIR/start_scanner.sh"

echo "✅ Created start_scanner.sh"

# Remove any existing scanner cron jobs
crontab -l 2>/dev/null | grep -v "realtime_scanner\|start_scanner" > /tmp/crontab_temp

# Add new cron job
echo "# Real-Time Trading Scanner - Auto Start at 9:18 AM Mon-Fri" >> /tmp/crontab_temp
echo "18 9 * * 1-5 $PROJECT_DIR/start_scanner.sh >> $LOG_FILE 2>&1" >> /tmp/crontab_temp

# Install new crontab
crontab /tmp/crontab_temp
rm /tmp/crontab_temp

echo "✅ Cron job installed"
echo ""

# Show current cron jobs
echo "📋 Current scheduled jobs:"
echo "--------------------------------------------"
crontab -l | grep -E "scanner|trading|Trading"
echo "--------------------------------------------"
echo ""

echo "✅ AUTO-START SETUP COMPLETE!"
echo ""
echo "📌 WHAT HAPPENS NOW:"
echo "   • Scanner will auto-start at 9:18 AM every weekday"
echo "   • Scans every 60 seconds during market hours"
echo "   • Alerts sent to Telegram when conditions are met"
echo "   • Auto-stops after market close (3:25 PM)"
echo ""
echo "📂 Logs saved to: $LOG_FILE"
echo ""
echo "🧪 TO TEST NOW:"
echo "   python3 $PROJECT_DIR/analysis/realtime_scanner.py --once"
echo ""
echo "🛑 TO DISABLE AUTO-START:"
echo "   crontab -e  (delete the scanner line)"
echo ""
