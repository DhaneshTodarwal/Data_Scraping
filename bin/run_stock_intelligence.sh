#!/bin/bash
# =============================================================================
# Stock Options Intelligence - Daily Collection Script
# =============================================================================
# Runs all data collection and analysis scripts in sequence
# 
# Schedule with cron:
# 25 15 * * 1-5 /path/to/run_stock_intelligence.sh
#
# This runs at 3:25 PM on weekdays (Mon-Fri)
# =============================================================================

set -e

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PATH="$SCRIPT_DIR/venv/bin/activate"
LOG_DIR="$SCRIPT_DIR/logs"
DATE=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/daily_intelligence_$DATE.log"

# Create log directory
mkdir -p "$LOG_DIR"

# Logging function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

# Activate virtual environment
if [ -f "$VENV_PATH" ]; then
    source "$VENV_PATH"
    log "✅ Virtual environment activated"
else
    log "⚠️ Virtual environment not found, using system Python"
fi

log "=============================================="
log "STOCK OPTIONS INTELLIGENCE - DAILY RUN"
log "=============================================="

# Step 1: Collect Stock Options Data
log "📊 Step 1: Collecting stock options data..."
cd "$SCRIPT_DIR"
python scripts/stock_options_scraper.py 2>&1 | tee -a "$LOG_FILE"
log "✅ Stock options data collected"

# Wait between steps
sleep 5

# Step 2: Collect Gainers/Losers
log "📈 Step 2: Collecting gainers/losers..."
python analysis/gainers_losers_tracker.py 2>&1 | tee -a "$LOG_FILE"
log "✅ Gainers/losers data collected"

# Wait between steps
sleep 3

# Step 3: Detect OI Spurts
log "🔍 Step 3: Detecting OI spurts..."
python analysis/oi_spurt_detector.py 2>&1 | tee -a "$LOG_FILE"
log "✅ OI spurts analyzed"

# Wait between steps
sleep 3

# Step 4: Generate Predictions
log "🎯 Step 4: Generating next-day predictions..."
python analysis/next_day_predictor.py 2>&1 | tee -a "$LOG_FILE"
log "✅ Predictions generated"

# Wait between steps
sleep 3

# Step 5: Analyze Movement Reasons
log "🔍 Step 5: Analyzing movement reasons..."
python analysis/movement_analyzer.py 2>&1 | tee -a "$LOG_FILE"
log "✅ Movement analysis completed"

# Step 6: Generate Daily Report (if exists)
if [ -f "analysis/daily_report.py" ]; then
    log "📄 Step 6: Generating daily report..."
    python analysis/daily_report.py 2>&1 | tee -a "$LOG_FILE"
    log "✅ Daily report generated"
fi

log "=============================================="
log "DAILY INTELLIGENCE RUN COMPLETED"
log "=============================================="

# Summary
echo ""
echo "📁 Data saved to: $SCRIPT_DIR/data/daily_analysis/$DATE/"
echo "📁 Predictions saved to: $SCRIPT_DIR/data/predictions/$DATE/"
echo "📁 Log file: $LOG_FILE"
echo ""

# Optional: Send completion notification
# Uncomment the following line if you have telegram setup
# python -c "from scripts.notifications import TelegramNotifier; TelegramNotifier().send_message('✅ Daily Stock Intelligence collection completed for $DATE')"

exit 0
