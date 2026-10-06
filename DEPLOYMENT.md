# Raspberry Pi Deployment Guide

## Overview
This guide covers deploying the updated BTC Scalp Bot to your Raspberry Pi.

## What's Changed
- **Entry Orders**: Now uses LIMIT orders at bullish_high + $6 (instead of market orders)
- **Strategy Fix**: RSI now correctly checked on the bullish candle
- **Time Sync**: Automatic Binance time synchronization to prevent timestamp errors
- **Log Rotation**: Keeps only ~1000 most recent logs (200KB × 5 files)
- **Auto Monitoring**: Terminal automatically opens with logs on Pi boot
- **Systemd Service**: Proper auto-start and graceful shutdown

## Deployment Methods

### Method 1: Automated Script (Recommended)

From your PC:
```bash
chmod +x /home/roshan/BTC_scalp/deploy_to_pi.sh
bash /home/roshan/BTC_scalp/deploy_to_pi.sh
```

This will:
1. Stop the old bot
2. Backup current version
3. Copy updated files
4. Install systemd service
5. Setup log monitoring
6. Start the new bot

### Method 2: Manual Deployment

#### Step 1: Stop Old Bot on Pi
```bash
ssh roshan@raspberryPi
sudo systemctl stop btc-scalp-bot 2>/dev/null || pkill -f 'python.*bot.py'
```

#### Step 2: Backup Current Version (Optional)
```bash
cd ~/BTC_scalp
cp -r . ../BTC_scalp_backup_$(date +%Y%m%d_%H%M%S)
```

#### Step 3: Copy Files from PC to Pi

From your PC, copy these updated files:
```bash
cd /home/roshan/BTC_scalp
scp bot.py config.py binance_api.py strategy.py logger.py \
    trade_manager.py btc-scalp-bot.service install_service.sh \
    monitor_logs.sh setup_monitor_autostart.sh requirements.txt \
    roshan@raspberryPi:~/BTC_scalp/
```

#### Step 4: Install on Raspberry Pi
```bash
ssh roshan@raspberryPi
cd ~/BTC_scalp

# Make scripts executable
chmod +x install_service.sh monitor_logs.sh setup_monitor_autostart.sh

# Install systemd service
sudo bash install_service.sh

# Setup log monitor autostart
bash setup_monitor_autostart.sh

# Start the bot
sudo systemctl start btc-scalp-bot
```

## Post-Deployment Verification

### Check Service Status
```bash
ssh roshan@raspberryPi 'sudo systemctl status btc-scalp-bot'
```

Expected output:
```
● btc-scalp-bot.service - BTC Scalping Bot
   Loaded: loaded (/etc/systemd/system/btc-scalp-bot.service; enabled)
   Active: active (running) since ...
```

### View Live Logs
```bash
ssh roshan@raspberryPi 'tail -f ~/BTC_scalp/bot.log'
```

Look for:
- `✓ Bot initialization complete`
- `Time offset synced with Binance server`
- `Waiting for 5-minute candle close...`

### Verify New Strategy
Watch for these log messages:
- `Bullish candle detected! RSI: XX.XX, High: $XXXXX.XX`
- `Placing limit entry order at $XXXXX.XX (bullish high + $6.00 buffer)`
- `Pending entry order: XXXXX at $XXXXX.XX`
- `Entry order filled! Position opened at $XXXXX.XX`

### Test Auto-Monitoring
On Raspberry Pi desktop:
1. Reboot: `sudo reboot`
2. After boot, a terminal should auto-open with live logs
3. If not, manually run: `bash ~/BTC_scalp/monitor_logs.sh`

## Service Management Commands

```bash
# Check status
sudo systemctl status btc-scalp-bot

# View logs
tail -f ~/BTC_scalp/bot.log

# Stop bot
sudo systemctl stop btc-scalp-bot

# Start bot
sudo systemctl start btc-scalp-bot

# Restart bot
sudo systemctl restart btc-scalp-bot

# Disable auto-start
sudo systemctl disable btc-scalp-bot

# Enable auto-start
sudo systemctl enable btc-scalp-bot

# View systemd logs
sudo journalctl -u btc-scalp-bot -f
```

## Troubleshooting

### Bot Won't Start
```bash
# Check systemd logs
sudo journalctl -u btc-scalp-bot -n 50

# Check bot logs
tail -n 100 ~/BTC_scalp/bot.log

# Check if PID file exists
ls -la ~/BTC_scalp/bot.pid

# Remove stale PID file
rm -f ~/BTC_scalp/bot.pid
```

### Timestamp Errors
The new version auto-syncs time with Binance. If issues persist:
```bash
# Check system time
timedatectl

# Manually sync (if needed)
sudo systemctl restart systemd-timesyncd
```

### Logs Not Appearing in Terminal
```bash
# Test monitor script
bash ~/BTC_scalp/monitor_logs.sh

# Check autostart entry
ls -la ~/.config/autostart/btc-scalp-monitor.desktop
```

### Old Orders Still Pending
```bash
# SSH to Pi
ssh roshan@raspberryPi

# Activate venv
source ~/BTC_scalp/venv/bin/activate

# Check open orders
python -c "
from binance_api import BinanceAPI
from config import API_KEY, API_SECRET
api = BinanceAPI(API_KEY, API_SECRET, testnet=True)  # Set testnet=False for mainnet
orders = api.get_open_orders('BTCUSDT')
for o in orders:
    print(f'{o[\"orderId\"]}: {o[\"type\"]} {o[\"side\"]} @ {o[\"price\"]}')
"
```

## Rollback to Previous Version

If needed, restore the backup:
```bash
ssh roshan@raspberryPi
sudo systemctl stop btc-scalp-bot
cd ~
rm -rf BTC_scalp
mv BTC_scalp_backup_YYYYMMDD_HHMMSS BTC_scalp
cd BTC_scalp
sudo systemctl start btc-scalp-bot
```

## Configuration Changes

The new version uses these config parameters:
- `ENTRY_BUFFER = 6` - Dollars above bullish high for limit entry
- `RSI_THRESHOLD = 34` - RSI level for bullish candle detection
- `PROFIT_TARGET = 0.011` - 1.1% profit target for exit

To adjust, edit `~/BTC_scalp/config.py` on Pi and restart:
```bash
sudo systemctl restart btc-scalp-bot
```

## Support

After deployment, monitor the first few trades carefully:
1. Verify bullish candle detection
2. Check limit order placement price
3. Confirm order fills and position opening
4. Verify profit target calculation
5. Check graceful shutdown (Ctrl+C or `systemctl stop`)
