#!/bin/bash
# Deploy BTC Scalp Bot to Raspberry Pi
# Usage: bash deploy_to_pi.sh [raspberry_pi_ip_or_hostname]

set -e

PI_HOST="${1:-raspberryPi}"
PI_USER="roshan"
PI_DIR="/home/roshan/BTC_scalp"
LOCAL_DIR="/home/roshan/BTC_scalp"

echo "=============================================="
echo "BTC Scalp Bot - Raspberry Pi Deployment"
echo "=============================================="
echo "Target: $PI_USER@$PI_HOST:$PI_DIR"
echo ""

# Files to deploy
FILES=(
    "bot.py"
    "config.py"
    "binance_api.py"
    "strategy.py"
    "logger.py"
    "trade_manager.py"
    "btc-scalp-bot.service"
    "install_service.sh"
    "monitor_logs.sh"
    "setup_monitor_autostart.sh"
    "requirements.txt"
)

echo "Step 1: Stopping old bot on Raspberry Pi..."
ssh $PI_USER@$PI_HOST "sudo systemctl stop btc-scalp-bot 2>/dev/null || pkill -f 'python.*bot.py' || true"
echo "✓ Old bot stopped"
echo ""

echo "Step 2: Backing up old version on Raspberry Pi..."
ssh $PI_USER@$PI_HOST "cd $PI_DIR && cp -r . ../BTC_scalp_backup_\$(date +%Y%m%d_%H%M%S) 2>/dev/null || true"
echo "✓ Backup created"
echo ""

echo "Step 3: Copying updated files..."
for file in "${FILES[@]}"; do
    if [ -f "$LOCAL_DIR/$file" ]; then
        echo "  → $file"
        scp -q "$LOCAL_DIR/$file" "$PI_USER@$PI_HOST:$PI_DIR/"
    fi
done
echo "✓ Files copied"
echo ""

echo "Step 4: Setting file permissions..."
ssh $PI_USER@$PI_HOST << 'EOF'
cd /home/roshan/BTC_scalp
chmod +x install_service.sh
chmod +x monitor_logs.sh
chmod +x setup_monitor_autostart.sh
EOF
echo "✓ Permissions set"
echo ""

echo "Step 5: Installing systemd service..."
ssh $PI_USER@$PI_HOST "cd $PI_DIR && sudo bash install_service.sh"
echo "✓ Service installed"
echo ""

echo "Step 6: Setting up log monitor autostart..."
ssh $PI_USER@$PI_HOST "cd $PI_DIR && bash setup_monitor_autostart.sh"
echo "✓ Monitor configured"
echo ""

echo "Step 7: Starting bot service..."
ssh $PI_USER@$PI_HOST "sudo systemctl start btc-scalp-bot"
echo "✓ Service started"
echo ""

echo "=============================================="
echo "Deployment Complete!"
echo "=============================================="
echo ""
echo "Check status:"
echo "  ssh $PI_USER@$PI_HOST 'sudo systemctl status btc-scalp-bot'"
echo ""
echo "View logs:"
echo "  ssh $PI_USER@$PI_HOST 'tail -f $PI_DIR/bot.log'"
echo ""
echo "Stop bot:"
echo "  ssh $PI_USER@$PI_HOST 'sudo systemctl stop btc-scalp-bot'"
echo ""
echo "Restart bot:"
echo "  ssh $PI_USER@$PI_HOST 'sudo systemctl restart btc-scalp-bot'"
echo ""
