#!/bin/bash
# Daily Options Data Collection
# Runs at 3:35 PM

cd "/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping"
LOG_FILE="logs/collection_$(date +%Y%m%d).log"

mkdir -p logs

echo "======================================" >> "$LOG_FILE"
echo "Collection started: $(date)" >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

MAX_RETRIES=3
RETRY_COUNT=0
SUCCESS=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    python3 scripts/angelone_complete.py >> "$LOG_FILE" 2>&1
    if [ $? -eq 0 ]; then
        SUCCESS=true
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT+1))
    if [ $RETRY_COUNT -lt $MAX_RETRIES ]; then
        echo "⚠️ Collection attempt $RETRY_COUNT failed. Retrying in 60 seconds..." >> "$LOG_FILE"
        sleep 60
    fi
done

if [ "$SUCCESS" = false ]; then
    echo "❌ Collection failed after $MAX_RETRIES attempts: $(date)" >> "$LOG_FILE"
else
    echo "Collection completed: $(date)" >> "$LOG_FILE"
fi
