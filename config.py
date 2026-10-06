# Trading Bot Configuration
BINANCE_API_KEY = "KTUaipxPd6elvinPLDFrP6r4j3Wwlwt8bR1iJPghJmqRp6LCvCO10Aw3Lqf8e5oD"
BINANCE_API_SECRET = "kUgIVMSZuZluCWNitTnmtnp21lkY8rYkK8qoiZOSqJfnjIxWTVNw58tcJJ399zRW"

# Deployment Mode
DEMO_MODE = False  # Set to True for Binance Testnet/Demo, False for Live Trading

# Trading Parameters
SYMBOL = "BTCUSDT"
TIMEFRAME = "5m"
RSI_PERIOD = 14  # RSI calculation period (default: 14)
RSI_THRESHOLD = 34  # Lower RSI level for entry signals
RSI_RESET_LEVEL = 52  # Upper RSI level - must close above this after a trade to allow new entries
PROFIT_TARGET = 0.011

# Position Sizing (replaces MAX_TRADES)
SINGLE_TRADE_SIZE = 0.007  # BTC quantity per trade entry (e.g., 0.002 BTC ~ $170 at $85k)
MAX_POSITION_SIZE = 0.014  # Maximum total position size allowed (e.g., 0.004 = 2 trades worth)
# Max trades calculated as: MAX_POSITION_SIZE / SINGLE_TRADE_SIZE = 2 trades

TRADE_COOLDOWN_HOURS = 0.01  # Minimum hours to wait between opening new trades
MACD_FILTER_ENABLED = False  # Enable/disable MACD trade filtration
MACD_TIMEFRAME = "8h"  # Timeframe for MACD filter (e.g., '1d' for daily, '4h' for 4-hour)
ENTRY_BUFFER = 4  # Dollars above bullish candle high for limit entry order
CANDLE_CLOSE_DELAY = 1  # Seconds to wait after candle close before checking signals (allows Binance data to propagate)

# Leverage for Futures (be careful with this)
LEVERAGE = 4

# Telegram Notifications
TELEGRAM_ENABLED = True
TELEGRAM_BOT_TOKEN = "8651991964:AAHptjX2874gnm3p5H62NEXORBnjUKmuyt4"
TELEGRAM_CHAT_ID = "1866988317"

# Logging
LOG_FILE = "trading_bot.log"
LOG_LEVEL = "INFO"
