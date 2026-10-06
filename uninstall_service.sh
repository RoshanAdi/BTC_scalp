#!/bin/bash
# Uninstallation script for BTC Scalp Bot systemd service
# Run with: sudo bash uninstall_service.sh

set -e

SERVICE_NAME="btc-scalp-bot"
SERVICE_FILE="btc-scalp-bot.service"

echo "=============================================="
echo "BTC Scalp Bot Service Uninstaller"
echo "=============================================="

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "❌ Please run as root (use sudo)"
    exit 1
fi

# Stop the service if running
echo "Stopping service..."
systemctl stop $SERVICE_NAME 2>/dev/null || true
echo "✓ Service stopped"

# Disable the service
echo "Disabling service..."
systemctl disable $SERVICE_NAME 2>/dev/null || true
echo "✓ Service disabled"

# Remove service file
if [ -f "/etc/systemd/system/$SERVICE_FILE" ]; then
    echo "Removing service file..."
    rm /etc/systemd/system/$SERVICE_FILE
    echo "✓ Service file removed"
fi

# Reload systemd
echo "Reloading systemd..."
systemctl daemon-reload
echo "✓ Systemd reloaded"

echo ""
echo "=============================================="
echo "Uninstallation Complete!"
echo "=============================================="
echo ""
echo "Note: Log files and bot files were NOT removed."
echo ""
