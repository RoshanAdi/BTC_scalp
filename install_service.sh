#!/bin/bash
# Installation script for BTC Scalp Bot systemd service
# Run with: sudo bash install_service.sh

set -e

SERVICE_NAME="btc-scalp-bot"
SERVICE_FILE="btc-scalp-bot.service"
BOT_DIR="/home/roshan/BTC_scalp"
USER="roshan"

echo "=============================================="
echo "BTC Scalp Bot Service Installer"
echo "=============================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (use sudo)"
    exit 1
fi

# Check if service file exists
if [ ! -f "$BOT_DIR/$SERVICE_FILE" ]; then
    echo "❌ Service file not found: $BOT_DIR/$SERVICE_FILE"
    exit 1
fi

# Check if bot.py exists
if [ ! -f "$BOT_DIR/bot.py" ]; then
    echo "❌ bot.py not found in $BOT_DIR"
    exit 1
fi

# Check if venv exists
if [ ! -f "$BOT_DIR/venv/bin/python" ]; then
    echo "❌ Python venv not found at $BOT_DIR/venv"
    exit 1
fi

echo "✓ All files found"

# Copy service file to systemd
echo "Installing service file..."
cp "$BOT_DIR/$SERVICE_FILE" /etc/systemd/system/$SERVICE_FILE
chmod 644 /etc/systemd/system/$SERVICE_FILE
echo "✓ Service file installed to /etc/systemd/system/$SERVICE_FILE"

# Create log files with correct permissions
echo "Setting up log files..."
touch "$BOT_DIR/bot_stdout.log" "$BOT_DIR/bot_stderr.log"
chown $USER:$USER "$BOT_DIR/bot_stdout.log" "$BOT_DIR/bot_stderr.log"
chmod 644 "$BOT_DIR/bot_stdout.log" "$BOT_DIR/bot_stderr.log"
echo "✓ Log files created"

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload
echo "✓ Systemd reloaded"

# Enable service
echo "Enabling service to start on boot..."
systemctl enable $SERVICE_NAME
echo "✓ Service enabled"

echo ""
echo "=============================================="
echo "Installation Complete!"
echo "=============================================="
echo ""
echo "Available commands:"
echo "  Start bot:    sudo systemctl start $SERVICE_NAME"
echo "  Stop bot:     sudo systemctl stop $SERVICE_NAME"
echo "  Restart bot:  sudo systemctl restart $SERVICE_NAME"
echo "  Status:       sudo systemctl status $SERVICE_NAME"
echo "  View logs:    sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "Log files:"
echo "  stdout: $BOT_DIR/bot_stdout.log"
echo "  stderr: $BOT_DIR/bot_stderr.log"
echo "  app:    $BOT_DIR/trading_bot.log"
echo ""
echo "To start the bot now, run:"
echo "  sudo systemctl start $SERVICE_NAME"
echo ""
