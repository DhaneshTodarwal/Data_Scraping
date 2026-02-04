#!/bin/bash
# =============================================================================
# DAILY GITHUB BACKUP SCRIPT
# =============================================================================
# Automatically commits and pushes daily data to GitHub
# Run this at end of day after data collection
# =============================================================================

PROJECT_DIR="/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping"
LOG_FILE="$PROJECT_DIR/logs/github_backup.log"

# Log function
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE"
    echo "$1"
}

cd "$PROJECT_DIR" || exit 1

log "📦 Starting GitHub Backup..."

# Check if there are changes
if git diff --quiet && git diff --cached --quiet; then
    log "ℹ️ No changes to commit"
    exit 0
fi

# Get today's date for commit message
TODAY=$(date '+%Y-%m-%d')
DAY_NAME=$(date '+%A')

# Add all changes
git add -A

# Create commit with descriptive message
COMMIT_MSG="📊 Daily Backup - $DAY_NAME $TODAY

Data collected:
- Index OHLCV data
- Options strike data
- Trading logs and reports"

git commit -m "$COMMIT_MSG"

if [ $? -eq 0 ]; then
    log "✅ Changes committed successfully"
    
    # Push to remote (if configured)
    if git remote | grep -q origin; then
        git push origin main 2>&1
        if [ $? -eq 0 ]; then
            log "✅ Pushed to GitHub successfully!"
            
            # Send Telegram notification
            python3 -c "
import sys
sys.path.insert(0, '$PROJECT_DIR/scripts')
try:
    from notifications import send_telegram_message
    send_telegram_message('☁️ <b>GitHub Backup Complete</b>\n\n📅 Date: $TODAY\n✅ Data safely backed up to GitHub!')
except:
    pass
" 2>/dev/null
        else
            log "⚠️ Push failed - check remote configuration"
        fi
    else
        log "⚠️ No remote 'origin' configured. Run: git remote add origin <your-repo-url>"
    fi
else
    log "❌ Commit failed"
    exit 1
fi

log "📦 Backup complete!"
