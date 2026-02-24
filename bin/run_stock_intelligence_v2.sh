#!/bin/bash
# =============================================================================
# Stock Intelligence - Daily Automation Script
# =============================================================================
# Runs the stock intelligence collector daily
# 
# Schedule with cron:
# 25 15 * * 1-5 /path/to/run_stock_intelligence_v2.sh
#
# This runs at 3:25 PM on weekdays (Mon-Fri)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
DATE=$(date +%Y-%m-%d)
LOG_FILE="$LOG_DIR/stock_intelligence_$DATE.log"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "=============================================="
log "🚀 STOCK INTELLIGENCE COLLECTOR"
log "=============================================="

cd "$SCRIPT_DIR/../analysis"

# Run the unified collector
python3 stock_intelligence_collector.py 2>&1 | tee -a "$LOG_FILE"

log "=============================================="
log "✅ COLLECTION COMPLETED"
log "=============================================="

echo ""
echo "📁 Data saved to: stock_intelligence/$(date +%Y-%m-%d)/"
echo "📁 Log file: $LOG_FILE"

exit 0
