#!/usr/bin/env python3
"""
Telegram Notification Module for BTC Scalp Bot
Sends alerts for trade entries, sync failures, and bot restarts
"""

import requests
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Handles Telegram bot notifications"""
    
    def __init__(self, bot_token: str, chat_id: str = None, enabled: bool = True):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.enabled = enabled
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
        if not enabled:
            logger.info("Telegram notifications disabled")
        elif not chat_id:
            logger.warning("⚠ Telegram CHAT_ID not set. Send /start to your bot to get your chat ID")
            self._get_chat_id_from_updates()
    
    def _get_chat_id_from_updates(self):
        """Try to get chat_id from recent messages to the bot"""
        try:
            response = requests.get(f"{self.base_url}/getUpdates", timeout=10)
            if response.status_code == 200:
                data = response.json()
                if data.get("ok") and data.get("result"):
                    for update in data["result"]:
                        if "message" in update:
                            chat_id = update["message"]["chat"]["id"]
                            self.chat_id = str(chat_id)
                            logger.info(f"✓ Found Telegram chat_id: {self.chat_id}")
                            logger.info(f"⚠ Add this to config.py: TELEGRAM_CHAT_ID = \"{self.chat_id}\"")
                            return
                logger.warning("No messages found. Send /start to your bot first!")
        except Exception as e:
            logger.error(f"Error getting chat_id: {e}")
    
    def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Send a message via Telegram"""
        if not self.enabled:
            return False
        
        if not self.chat_id:
            # Try to get chat_id again
            self._get_chat_id_from_updates()
            if not self.chat_id:
                logger.warning("Cannot send Telegram message: chat_id not set")
                return False
        
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": parse_mode
            }
            response = requests.post(url, json=payload, timeout=10)
            
            if response.status_code == 200:
                logger.debug(f"Telegram message sent successfully")
                return True
            else:
                logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    def notify_bot_started(self, symbol: str, timeframe: str, single_trade_size: float, 
                          max_position_size: float, leverage: int, demo_mode: bool):
        """Send notification when bot starts"""
        mode = "🧪 DEMO" if demo_mode else "🔴 LIVE"
        max_trades = int(max_position_size / single_trade_size)
        
        message = f"""
🚀 <b>BTC Scalp Bot Started</b>

{mode} Trading Mode
━━━━━━━━━━━━━━━━━━━━━
📊 Symbol: <code>{symbol}</code>
⏱ Timeframe: <code>{timeframe}</code>
💰 Trade Size: <code>{single_trade_size} BTC</code>
📈 Max Position: <code>{max_position_size} BTC</code>
🎯 Max Trades: <code>{max_trades}</code>
⚡ Leverage: <code>{leverage}x</code>
━━━━━━━━━━━━━━━━━━━━━
🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message)
    
    def notify_trade_entry(self, entry_price: float, quantity: float, 
                          take_profit_price: float, rsi: float, position_type: str = "LONG"):
        """Send notification when a trade is entered"""
        profit_target_pct = ((take_profit_price - entry_price) / entry_price) * 100
        usd_value = entry_price * quantity
        
        message = f"""
🟢 <b>NEW TRADE OPENED</b>

📈 Position: <code>{position_type}</code>
━━━━━━━━━━━━━━━━━━━━━
💵 Entry Price: <code>${entry_price:,.2f}</code>
📊 Quantity: <code>{quantity} BTC</code>
💰 Value: <code>${usd_value:,.2f}</code>
🎯 Take Profit: <code>${take_profit_price:,.2f}</code>
📈 Target: <code>+{profit_target_pct:.2f}%</code>
📉 RSI at entry: <code>{rsi:.1f}</code>
━━━━━━━━━━━━━━━━━━━━━
🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message)
    
    def notify_trade_closed(self, entry_price: float, exit_price: float, 
                           quantity: float, pnl: float, pnl_percent: float):
        """Send notification when a trade is closed"""
        emoji = "💰" if pnl >= 0 else "📉"
        status = "PROFIT" if pnl >= 0 else "LOSS"
        
        message = f"""
{emoji} <b>TRADE CLOSED - {status}</b>

━━━━━━━━━━━━━━━━━━━━━
💵 Entry: <code>${entry_price:,.2f}</code>
💵 Exit: <code>${exit_price:,.2f}</code>
📊 Quantity: <code>{quantity} BTC</code>
{emoji} PnL: <code>${pnl:,.4f} ({pnl_percent:+.4f}%)</code>
━━━━━━━━━━━━━━━━━━━━━
🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message)
    
    def notify_sync_failure(self, error_message: str):
        """Send notification when position sync fails (likely IP change)"""
        message = f"""
⚠️ <b>SYNC FAILURE - ACTION REQUIRED</b>

🔴 Failed to sync positions with Binance!
━━━━━━━━━━━━━━━━━━━━━
❌ Error: <code>{error_message[:200]}</code>

⚠️ This may be due to:
• IP address changed
• API key issue
• Network problem

🔧 Please check and fix manually!
━━━━━━━━━━━━━━━━━━━━━
🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message)
    
    def notify_max_position_reached(self, current_position: float, max_position: float, 
                                    current_trades: int, max_trades: int):
        """Send notification when max position is reached"""
        message = f"""
📊 <b>MAX POSITION REACHED</b>

━━━━━━━━━━━━━━━━━━━━━
📈 Current: <code>{current_position:.4f} BTC</code>
📊 Maximum: <code>{max_position:.4f} BTC</code>
🎯 Trades: <code>{current_trades}/{max_trades}</code>

⏸ Bot will wait for exits before new entries
━━━━━━━━━━━━━━━━━━━━━
🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message)
    
    def notify_rsi_reset_required(self, current_rsi: float, reset_level: float):
        """Send notification when RSI reset is waiting"""
        message = f"""
⏳ <b>RSI RESET WAITING</b>

━━━━━━━━━━━━━━━━━━━━━
📉 Current RSI: <code>{current_rsi:.1f}</code>
🎯 Reset Level: <code>{reset_level}</code>

⏸ Waiting for RSI to close above {reset_level}
━━━━━━━━━━━━━━━━━━━━━
🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message)
    
    def notify_error(self, error_type: str, error_message: str):
        """Send notification for critical errors"""
        message = f"""
🔴 <b>BOT ERROR</b>

━━━━━━━━━━━━━━━━━━━━━
❌ Type: <code>{error_type}</code>
📝 Error: <code>{error_message[:300]}</code>
━━━━━━━━━━━━━━━━━━━━━
🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        return self.send_message(message)
