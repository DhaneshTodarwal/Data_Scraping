"""
Telegram Bot with Commands
===========================
Enables interactive commands via Telegram:
- /positions - View open positions
- /history - View trade history
- /pnl - View P&L summary
- /close <trade_id> - Close a trade
- /help - Show commands
"""
import sys
import os
import time
import json
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta
import threading

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent))

IST = timezone(timedelta(hours=5, minutes=30))

# Load environment directly
import os

BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Try loading from .env file if not in environment
if not BOT_TOKEN:
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                if line.strip() and not line.startswith('#'):
                    key, _, value = line.strip().partition('=')
                    if key == 'TELEGRAM_BOT_TOKEN':
                        BOT_TOKEN = value.strip('"\'')
                    elif key == 'TELEGRAM_CHAT_ID':
                        CHAT_ID = value.strip('"\'')

try:
    from paper_trading_platform import get_platform, send_positions, send_history
    PAPER_TRADING_OK = True
except ImportError:
    PAPER_TRADING_OK = False


class TelegramBot:
    """Interactive Telegram bot with commands"""
    
    def __init__(self):
        self.token = BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"
        self.last_update_id = 0
        self.running = False
        
        # Load last update ID
        self.state_file = Path(__file__).parent / "bot_state.json"
        self._load_state()
    
    def _load_state(self):
        """Load bot state"""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    data = json.load(f)
                    self.last_update_id = data.get('last_update_id', 0)
            except:
                pass
    
    def _save_state(self):
        """Save bot state"""
        with open(self.state_file, 'w') as f:
            json.dump({'last_update_id': self.last_update_id}, f)
    
    def send_message(self, text: str, chat_id: str = None) -> bool:
        """Send message to Telegram"""
        try:
            url = f"{self.base_url}/sendMessage"
            data = {
                'chat_id': chat_id or CHAT_ID,
                'text': text,
                'parse_mode': 'HTML',
            }
            response = requests.post(url, data=data, timeout=10)
            return response.ok
        except Exception as e:
            print(f"Send error: {e}")
            return False
    
    def get_updates(self) -> list:
        """Get new messages"""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {
                'offset': self.last_update_id + 1,
                'timeout': 5,
            }
            response = requests.get(url, params=params, timeout=10)
            if response.ok:
                return response.json().get('result', [])
        except:
            pass
        return []
    
    def handle_command(self, command: str, chat_id: str, args: list = None):
        """Handle a command"""
        
        if command == '/start' or command == '/help':
            msg = """
🤖 <b>Trading Bot Commands</b>

📊 <b>View Data:</b>
/positions - View open positions
/history - View trade history  
/pnl - View P&L summary
/stats - View portfolio stats

📝 <b>Actions:</b>
/close &lt;trade_id&gt; - Close a trade

ℹ️ <b>Info:</b>
/status - System status
/help - Show this help
"""
            self.send_message(msg, chat_id)
        
        elif command == '/positions':
            if PAPER_TRADING_OK:
                platform = get_platform()
                msg = platform.generate_positions_message()
                self.send_message(msg, chat_id)
            else:
                self.send_message("❌ Paper trading not available", chat_id)
        
        elif command == '/history':
            if PAPER_TRADING_OK:
                platform = get_platform()
                msg = platform.generate_history_message()
                self.send_message(msg, chat_id)
            else:
                self.send_message("❌ Paper trading not available", chat_id)
        
        elif command == '/pnl':
            if PAPER_TRADING_OK:
                platform = get_platform()
                stats = platform.stats
                
                emoji = "🟢" if stats.total_pnl >= 0 else "🔴"
                
                msg = f"""
💰 <b>P&L SUMMARY</b>

{emoji} <b>Total P&L:</b> ₹{stats.total_pnl:+,.0f}

📈 <b>Realized:</b> ₹{stats.realized_pnl:+,.0f}
📊 <b>Unrealized:</b> ₹{stats.unrealized_pnl:+,.0f}

✅ <b>Winners:</b> {stats.winning_trades}
❌ <b>Losers:</b> {stats.losing_trades}
📊 <b>Win Rate:</b> {stats.win_rate:.1f}%

🏆 <b>Best Trade:</b> ₹{stats.best_trade_pnl:+,.0f}
📉 <b>Worst Trade:</b> ₹{stats.worst_trade_pnl:+,.0f}
"""
                self.send_message(msg, chat_id)
            else:
                self.send_message("❌ Paper trading not available", chat_id)
        
        elif command == '/stats':
            if PAPER_TRADING_OK:
                platform = get_platform()
                stats = platform.stats
                
                msg = f"""
📊 <b>PORTFOLIO STATS</b>

💰 <b>Capital:</b> ₹{stats.total_capital:,.0f}
📈 <b>Available:</b> ₹{stats.available_capital:,.0f}
🔒 <b>Used Margin:</b> ₹{stats.used_margin:,.0f}

📋 <b>Total Trades:</b> {stats.total_trades}
📊 <b>Open Positions:</b> {len(platform.open_trades)}
"""
                self.send_message(msg, chat_id)
            else:
                self.send_message("❌ Paper trading not available", chat_id)
        
        elif command == '/close':
            if not args:
                self.send_message("❌ Usage: /close <trade_id>", chat_id)
            else:
                trade_id = args[0]
                if PAPER_TRADING_OK:
                    platform = get_platform()
                    trade = platform.close_trade(trade_id, "Manual via Telegram")
                    if trade:
                        emoji = "🟢" if trade.pnl_amount >= 0 else "🔴"
                        self.send_message(
                            f"✅ <b>Trade Closed!</b>\n\n"
                            f"ID: {trade.trade_id}\n"
                            f"{emoji} P&L: ₹{trade.pnl_amount:+,.0f}",
                            chat_id
                        )
                    else:
                        self.send_message(f"❌ Trade {trade_id} not found", chat_id)
                else:
                    self.send_message("❌ Paper trading not available", chat_id)
        
        elif command == '/status':
            now = datetime.now(IST)
            msg = f"""
🤖 <b>SYSTEM STATUS</b>

⏰ <b>Time:</b> {now.strftime('%H:%M:%S')}
📅 <b>Date:</b> {now.strftime('%Y-%m-%d')}

✅ Paper Trading: {'OK' if PAPER_TRADING_OK else 'Not Available'}
✅ Bot: Running

💡 Send /help for commands
"""
            self.send_message(msg, chat_id)
        
        else:
            self.send_message(f"❓ Unknown command: {command}\nSend /help for available commands", chat_id)
    
    def process_updates(self):
        """Process incoming updates"""
        updates = self.get_updates()
        
        for update in updates:
            self.last_update_id = update['update_id']
            
            if 'message' in update:
                message = update['message']
                chat_id = str(message['chat']['id'])
                text = message.get('text', '')
                
                # Parse command
                if text.startswith('/'):
                    parts = text.split()
                    command = parts[0].lower()
                    args = parts[1:] if len(parts) > 1 else []
                    
                    print(f"📥 Command: {command} from {chat_id}")
                    self.handle_command(command, chat_id, args)
        
        self._save_state()
    
    def run(self, poll_interval: int = 2):
        """Run bot in polling mode"""
        print("🤖 Telegram bot started!")
        print("Send /help to the bot for commands")
        
        self.running = True
        
        while self.running:
            try:
                self.process_updates()
                time.sleep(poll_interval)
            except KeyboardInterrupt:
                print("\n⏹ Bot stopped")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(5)
    
    def stop(self):
        """Stop the bot"""
        self.running = False


# Quick access
bot = None


def get_bot() -> TelegramBot:
    global bot
    if bot is None:
        bot = TelegramBot()
    return bot


def run_bot():
    """Run the bot"""
    get_bot().run()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true', help='Run bot')
    parser.add_argument('--test', action='store_true', help='Send test message')
    
    args = parser.parse_args()
    
    if args.run:
        run_bot()
    elif args.test:
        bot = TelegramBot()
        bot.send_message("🤖 Bot is online! Send /help for commands")
        print("✅ Test message sent")
    else:
        print("Telegram Bot")
        print("  --run   Start the bot")
        print("  --test  Send test message")
