#!/bin/bash
# Telegram Bot Setup Script for Options Data Collection Alerts
# Run this script to configure Telegram notifications

echo "
╔═══════════════════════════════════════════════════════════════════════╗
║            TELEGRAM NOTIFICATION SETUP                                ║
╠═══════════════════════════════════════════════════════════════════════╣
║  Follow these steps to enable Telegram alerts:                        ║
║                                                                       ║
║  Step 1: Create a Telegram Bot                                        ║
║  ────────────────────────────────────────────────────────────────────║
║  1. Open Telegram and search for @BotFather                           ║
║  2. Send /newbot command                                              ║
║  3. Give your bot a name (e.g., 'Options Alert Bot')                  ║
║  4. Give it a username (e.g., 'MyOptionsAlertBot')                    ║
║  5. BotFather will give you a TOKEN - copy it!                        ║
║                                                                       ║
║  Step 2: Get Your Chat ID                                             ║
║  ────────────────────────────────────────────────────────────────────║
║  1. Message your new bot (say 'Hi')                                   ║
║  2. Open this URL in browser (replace YOUR_TOKEN):                    ║
║     https://api.telegram.org/botYOUR_TOKEN/getUpdates                 ║
║  3. Look for \"chat\":{\"id\": NUMBER} - that NUMBER is your Chat ID     ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
"

# Prompt for token
read -p "Enter your Telegram Bot Token: " TELEGRAM_BOT_TOKEN
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "❌ Token cannot be empty!"
    exit 1
fi

# Prompt for chat ID
read -p "Enter your Telegram Chat ID: " TELEGRAM_CHAT_ID
if [ -z "$TELEGRAM_CHAT_ID" ]; then
    echo "❌ Chat ID cannot be empty!"
    exit 1
fi

# Create .env file
ENV_FILE="/home/dhanesh-todarwal/Documents/Antigravity Projects/Data_Scraping/.env"

echo "# Telegram Configuration for Options Data Collection
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID=$TELEGRAM_CHAT_ID
" > "$ENV_FILE"

echo "✅ Saved to .env file"

# Add to bashrc for permanent use
echo "
# Options Data Collection - Telegram Alerts
export TELEGRAM_BOT_TOKEN='$TELEGRAM_BOT_TOKEN'
export TELEGRAM_CHAT_ID='$TELEGRAM_CHAT_ID'
" >> ~/.bashrc

echo "✅ Added to ~/.bashrc"

# Export for current session
export TELEGRAM_BOT_TOKEN="$TELEGRAM_BOT_TOKEN"
export TELEGRAM_CHAT_ID="$TELEGRAM_CHAT_ID"

# Test the notification
echo ""
echo "Testing Telegram notification..."
python3 -c "
import requests
BOT_TOKEN = '$TELEGRAM_BOT_TOKEN'
CHAT_ID = '$TELEGRAM_CHAT_ID'
msg = '🎉 <b>Telegram Alerts Configured!</b>\n\nOptions Data Collection notifications are now active.'
url = f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage'
resp = requests.post(url, data={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'HTML'})
if resp.status_code == 200:
    print('✅ Test message sent successfully!')
else:
    print(f'❌ Failed: {resp.text}')
"

echo ""
echo "╔═══════════════════════════════════════════════════════════════════════╗"
echo "║  SETUP COMPLETE! ✅                                                    ║"
echo "║                                                                        ║"
echo "║  You will now receive Telegram alerts when:                           ║"
echo "║  • Data collection starts (3:35 PM)                                   ║"
echo "║  • Data collection completes (with summary)                           ║"
echo "║  • Any errors occur                                                   ║"
echo "╚═══════════════════════════════════════════════════════════════════════╝"
