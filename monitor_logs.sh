#!/bin/bash
# Script to open terminal and monitor bot logs
# This will be added to autostart on Raspberry Pi

# Wait for bot to start
sleep 5

# Open terminal with log monitoring
# For Raspberry Pi with LXDE desktop
if command -v lxterminal &> /dev/null; then
    lxterminal --title="BTC Scalp Bot - Live Logs" -e "tail -f /home/roshan/BTC_scalp/trading_bot.log" &
# For other desktops
elif command -v gnome-terminal &> /dev/null; then
    gnome-terminal --title="BTC Scalp Bot - Live Logs" -- bash -c "tail -f /home/roshan/BTC_scalp/trading_bot.log"
elif command -v xterm &> /dev/null; then
    xterm -title "BTC Scalp Bot - Live Logs" -e "tail -f /home/roshan/BTC_scalp/trading_bot.log" &
else
    # Fallback - create notification
    notify-send "BTC Scalp Bot" "Bot is running. Use 'tail -f ~/BTC_scalp/trading_bot.log' to view logs"
fi
