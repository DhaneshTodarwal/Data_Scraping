#!/bin/bash
# Daily Options Data Collection
# Runs at 3:35 PM

cd "/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping"
LOG_FILE="logs/collection_$(date +%Y%m%d).log"

mkdir -p logs

echo "======================================" >> "$LOG_FILE"
echo "Collection started: $(date)" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

python3 scripts/angelone_complete.py >> "$LOG_FILE" 2>&1

echo "Collection completed: $(date)" >> "$LOG_FILE"

# Send notification (optional)
# python3 scripts/notifications.py "Data collection complete" >> "$LOG_FILE" 2>&1
