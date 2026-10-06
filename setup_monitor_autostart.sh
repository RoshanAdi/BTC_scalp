#!/bin/bash
# Setup autostart for log monitoring on Raspberry Pi
# Run this script once to configure automatic log terminal on boot

set -e

AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/btc-scalp-monitor.desktop"
SCRIPT_PATH="/home/roshan/BTC_scalp/monitor_logs.sh"

echo "=============================================="
echo "BTC Scalp Bot - Log Monitor Autostart Setup"
echo "=============================================="

# Create autostart directory if it doesn't exist
mkdir -p "$AUTOSTART_DIR"
echo "✓ Autostart directory ready"

# Make monitor script executable
chmod +x "$SCRIPT_PATH"
echo "✓ Monitor script is executable"

# Create desktop entry for autostart
cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=BTC Scalp Bot Monitor
Comment=Auto-open terminal with bot logs
Exec=$SCRIPT_PATH
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
EOF

echo "✓ Desktop entry created at $DESKTOP_FILE"

echo ""
echo "=============================================="
echo "Setup Complete!"
echo "=============================================="
echo ""
echo "A terminal window will automatically open on boot"
echo "showing live bot logs."
echo ""
echo "To test now, run:"
echo "  bash $SCRIPT_PATH"
echo ""
echo "To disable autostart, delete:"
echo "  $DESKTOP_FILE"
echo ""
