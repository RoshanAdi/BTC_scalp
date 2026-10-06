# Bitcoin Scalp Trading Bot

A Python-based scalp trading bot for Bitcoin (BTCUSDT) on Binance Futures, designed to run on Raspberry Pi with automatic startup on boot.

## Strategy

- **Timeframe**: 5 minutes
- **Entry Conditions**:
  - Previous candle is bullish (close > open) with RSI below threshold
  - Current candle's high passes the previous candle's high
  - Market order with `priceProtect` enabled to reduce slippage
- **Exit**: Limit order placed immediately at profit target price
- **Max Concurrent Trades**: 5 (configurable)
- **Stop Loss**: None (accumulating during market bottom)

## Features

- ✓ Automated candle-close based trading
- ✓ Trade state persistence (JSON)
- ✓ Position sync with Binance on restart
- ✓ Multiple concurrent trades management
- ✓ RSI-based signal detection with proper candle analysis
- ✓ MACD filter option (higher timeframe)
- ✓ Comprehensive logging
- ✓ Testnet/Mainnet support
- ✓ Detailed P&L tracking
- ✓ **Systemd service for Raspberry Pi auto-start**
- ✓ **Graceful shutdown handling**
- ✓ **PID file to prevent multiple instances**

## Project Structure

```
BTC_scalp/
├── config.py              # Configuration and credentials
├── binance_api.py         # Binance Futures API wrapper
├── strategy.py            # Trading strategy logic
├── trade_manager.py       # Trade state management
├── logger.py              # Logging setup
├── bot.py                 # Main bot script
├── backtest.py            # Backtesting script
├── setup.py               # Setup and validation script
├── requirements.txt       # Python dependencies
├── btc-scalp-bot.service  # Systemd service file
├── install_service.sh     # Service installation script
├── uninstall_service.sh   # Service removal script
├── trade_state.json       # Persistent trade state (auto-generated)
├── trading_bot.log        # Bot logs (auto-generated)
├── bot.pid                # PID file (auto-generated when running)
└── README.md              # This file
```

## Installation

### Prerequisites
- Python 3.8+
- Binance account with Futures enabled
- Binance API key and secret

### Setup Steps

1. **Clone and setup virtual environment**:
   ```bash
   cd /home/roshan/BTC_scalp
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure API credentials** in `config.py`:
   ```python
   BINANCE_API_KEY = "your_actual_api_key"
   BINANCE_API_SECRET = "your_actual_api_secret"
   DEMO_MODE = True  # Set to False for live trading
   ```

4. **Create API key** on Binance:
   - Go to https://www.binance.com/en/my/settings/api-management
   - Create new key with Futures trading enabled
   - Enable "Futures" permissions
   - DO NOT enable withdrawal

5. **Test setup**:
   ```bash
   python setup.py
   ```

## Usage

### Running Manually

```bash
# Activate virtual environment
source venv/bin/activate

# Run the bot
python bot.py
```

### Running on Raspberry Pi (Auto-Start on Boot)

1. **Install the systemd service**:
   ```bash
   sudo bash install_service.sh
   ```

2. **Start the bot**:
   ```bash
   sudo systemctl start btc-scalp-bot
   ```

3. **Check status**:
   ```bash
   sudo systemctl status btc-scalp-bot
   ```

4. **View logs**:
   ```bash
   sudo journalctl -u btc-scalp-bot -f
   # or
   tail -f trading_bot.log
   ```

5. **Stop the bot**:
   ```bash
   sudo systemctl stop btc-scalp-bot
   ```

6. **Disable auto-start**:
   ```bash
   sudo systemctl disable btc-scalp-bot
   ```

### Uninstall Service

```bash
sudo bash uninstall_service.sh
```

## Configuration

Edit `config.py` to customize:

```python
# Deployment Mode
DEMO_MODE = False            # True for Testnet, False for Live Trading

# Trading Parameters
SYMBOL = "BTCUSDT"           # Trading pair
TIMEFRAME = "5m"             # Candle timeframe
RSI_THRESHOLD = 34           # RSI entry threshold (on bullish candle)
PROFIT_TARGET = 0.011        # 1.1% profit target
MAX_TRADES = 5               # Max concurrent trades
TRADE_COOLDOWN_HOURS = 0.1   # Hours between new trades
LEVERAGE = 2                 # Trading leverage

# MACD Filter (optional)
MACD_FILTER_ENABLED = False  # Enable MACD confirmation
MACD_TIMEFRAME = "8h"        # Higher timeframe for MACD

# Logging
LOG_LEVEL = "INFO"           # INFO, DEBUG, WARNING, ERROR
```

## Order Execution

| Action | Order Type | Details |
|--------|------------|---------|
| Entry (BUY) | MARKET | With `priceProtect=True` to reduce slippage |
| Exit (SELL) | LIMIT | Placed immediately at target price after entry |

## Bot Output

The bot runs continuously, executing every 5 minutes:

```
2026-02-20 10:15:00 - Signal Analysis: {'current_rsi': 28.5, 'rsi_below_threshold': True, ...}
2026-02-20 10:15:01 - ✓ ENTRY SIGNAL DETECTED!
2026-02-20 10:15:02 - ✓ Buy order placed: 123456789
2026-02-20 10:15:03 - ✓ Trade opened: TRADE_1
2026-02-20 10:15:05 - Checking exit signals
2026-02-20 10:15:06 - TRADE_1: Current profit 0.3% (Target: 0.5%)
2026-02-20 10:20:01 - ✓ EXIT SIGNAL for TRADE_1
2026-02-20 10:20:02 - ✓ Sell order placed: 123456790
2026-02-20 10:20:03 - ✓ Trade closed: PnL=0.0050 (0.5000%)
```

## Monitoring

### View Live Logs
```bash
tail -f trading_bot.log
```

### Check Trade State
```bash
cat trade_state.json
```

### Monitor from another terminal
```bash
python -c "import json; print(json.load(open('trade_state.json')))"
```

## Important Notes

### ⚠️ Risk Management
- **NO STOP LOSS**: Current strategy has no stop loss
- If trade goes against you, it will hold until recovery
- This requires STRONG conviction and capital management
- Recommended: Use small position sizes during testing

### 🔒 API Security
- Never share API keys
- Use restricted API keys (IP whitelist, no withdrawals)
- Rotate keys periodically
- For production, consider environment variables instead of hardcoding

### 💻 Raspberry Pi Setup
- Requires stable internet connection
- CPU/memory usage is minimal
- **Recommended**: Use systemd service for auto-restart on boot
- Service auto-restarts on crash (after 30 seconds)
- PID file prevents multiple instances
- Graceful shutdown preserves trade state

### 📊 Backtesting
Run backtests before live trading:
```bash
python backtest.py
```

## Troubleshooting

### "Timestamp for this request is outside of the recvWindow"
**Problem**: Raspberry Pi system time is out of sync with Binance servers.

**Solution**:
```bash
# Sync time immediately
sudo timedatectl set-ntp true
sudo systemctl restart systemd-timesyncd

# Install NTP for automatic sync on boot
sudo apt install ntp -y
sudo systemctl enable ntp
sudo systemctl start ntp

# Restart the bot
sudo systemctl restart btc-scalp-bot
```

### "API credentials not configured"
- Edit `config.py` and add real API credentials

### "Failed to connect to Binance"
- Check internet connection
- Verify API key is valid
- Ensure Futures trading is enabled on API key
- Check if using wrong key for mainnet/testnet

### No signals detected
- Verify RSI calculation (should be 0-100)
- Check if current market conditions match criteria
- Review logs for candle pattern details

### Order placement fails
- Insufficient balance
- Leverage too high
- Order size too small (minimum 0.001 BTC on testnet)

## Files Description

| File | Purpose |
|------|---------|
| `bot.py` | Main trading loop - runs at candle close |
| `config.py` | Configuration, API credentials, trading parameters |
| `binance_api.py` | Binance Futures API wrapper with order management |
| `strategy.py` | Trading logic: RSI, candle pattern analysis |
| `trade_manager.py` | Track open/closed trades, P&L calculation |
| `logger.py` | Logging configuration |
| `backtest.py` | Backtesting framework |
| `setup.py` | Validation script to test setup |
| `btc-scalp-bot.service` | Systemd service definition |
| `install_service.sh` | Install systemd service |
| `uninstall_service.sh` | Remove systemd service |

## Future Improvements

- [ ] Add stop loss implementation
- [ ] Implement trailing stop for profits
- [ ] Add notifications (Telegram, email)
- [ ] Web dashboard for monitoring
- [ ] Multiple symbols support
- [ ] Database for historical trades

## Disclaimer

This bot is provided as-is for educational purposes. Use at your own risk:
- Past performance doesn't guarantee future results
- Trading carries risk of financial loss
- Start with small amounts on testnet
- Always understand what your bot is doing
- Maintain proper risk management

## Support

Check logs in `trading_bot.log` for errors and debugging information.

---

**Good luck with your trading! 🚀**
