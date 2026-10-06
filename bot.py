#!/usr/bin/env python3
"""
Bitcoin Scalp Trading Bot
Runs at candle close intervals to execute scalp trades on Binance Futures
"""

import time
import logging
import sys
import os
import signal
import atexit
from datetime import datetime
from pathlib import Path

# Get the directory where bot.py is located (for absolute paths)
BOT_DIR = Path(__file__).parent.resolve()

from config import (
    BINANCE_API_KEY, BINANCE_API_SECRET, SYMBOL, TIMEFRAME,
    RSI_PERIOD, RSI_THRESHOLD, RSI_RESET_LEVEL, PROFIT_TARGET, LEVERAGE, LOG_FILE, LOG_LEVEL,
    TRADE_COOLDOWN_HOURS, MACD_FILTER_ENABLED, MACD_TIMEFRAME, DEMO_MODE,
    ENTRY_BUFFER, SINGLE_TRADE_SIZE, MAX_POSITION_SIZE, CANDLE_CLOSE_DELAY,
    TELEGRAM_ENABLED, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)
from logger import setup_logging
from binance_api import BinanceAPI
from strategy import StrategyAnalyzer
from trade_manager import TradeManager
from telegram_notifier import TelegramNotifier
from websocket_manager import CandleWebSocket, MACDWebSocket

# Setup logging with absolute path
logger = setup_logging(str(BOT_DIR / LOG_FILE), LOG_LEVEL)

# PID file for preventing multiple instances
PID_FILE = BOT_DIR / "bot.pid"
# Global objects
binance_client = None
trade_manager = None
telegram = None  # Telegram notifier instance
last_entry_time = None  # Track last entry time for cooldown
macd_klines = None  # Store MACD klines for filtering
next_check_time = None  # Track when to run next check based on candle close
next_candle_close_ms = None  # Absolute timestamp of next candle close for precise scheduling
shutdown_requested = False  # Flag for graceful shutdown
sync_counter = 0  # Counter for periodic syncs
pending_entry_order = None  # Track pending entry limit order {'order_id': int, 'bullish_high': float}
rsi_reset_required = False  # Flag: after trade fills, require RSI to close above RSI_RESET_LEVEL before new entries

# WebSocket for exact candle close data
candle_ws = None  # Main timeframe WebSocket
macd_ws = None    # MACD timeframe WebSocket (if enabled)


def create_pid_file():
    """Create PID file to prevent multiple instances"""
    if PID_FILE.exists():
        # Check if the process is still running
        try:
            old_pid = int(PID_FILE.read_text().strip())
            # Check if process exists
            os.kill(old_pid, 0)
            logger.error(f"❌ Bot is already running with PID {old_pid}")
            logger.error(f"If this is incorrect, delete {PID_FILE} and restart")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            # Process not running, safe to continue
            logger.warning(f"⚠ Stale PID file found, removing...")
            PID_FILE.unlink()
    
    # Write current PID
    PID_FILE.write_text(str(os.getpid()))
    logger.info(f"✓ PID file created: {PID_FILE} (PID: {os.getpid()})")


def remove_pid_file():
    """Remove PID file on exit"""
    try:
        if PID_FILE.exists():
            PID_FILE.unlink()
            logger.info("✓ PID file removed")
    except Exception as e:
        logger.warning(f"Could not remove PID file: {e}")


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global shutdown_requested
    sig_name = signal.Signals(signum).name
    logger.info(f"\n⏹ Received {sig_name}, initiating graceful shutdown...")
    shutdown_requested = True


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    signal.signal(signal.SIGTERM, signal_handler)  # systemd stop
    signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
    signal.signal(signal.SIGHUP, signal_handler)   # Terminal closed
    logger.info("✓ Signal handlers configured")


def get_state_file_path():
    """Get absolute path to trade state file"""
    return str(BOT_DIR / "trade_state.json")


def wait_for_candle_completion():
    """Wait a bit after candle close to ensure Binance has processed the complete candle"""
    wait_time = 1.0  # Wait 1 second after candle close for data to settle
    logger.debug(f"Waiting {wait_time}s for candle data to be processed...")
    time.sleep(wait_time)


def validate_klines_freshness(klines):
    """Validate that klines are fresh by finding the most recently closed candle"""
    if not klines or len(klines) == 0:
        return False, "No klines data"
    
    try:
        if len(klines) < 2:
            return False, "Not enough klines"
        
        # Get Binance server time
        server_time_ms = binance_client.get_server_time()
        if not server_time_ms:
            return False, "Could not get server time"
        
        server_time_sec = server_time_ms / 1000
        
        # Find the most recently closed candle (close_time <= server_time)
        just_closed_time = None
        for i in range(len(klines) - 1, -1, -1):
            candle_close_time = float(klines[i][6]) / 1000  # Close time in seconds
            if candle_close_time <= server_time_sec:
                just_closed_time = candle_close_time
                break
        
        if just_closed_time is None:
            return False, "No closed candle found in data"
        
        # Check if the just-closed candle is recent
        timeframe_map = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '1h': 3600,
            '4h': 14400,
            '1d': 86400,
        }
        interval_sec = timeframe_map.get(TIMEFRAME, 300)
        
        time_since_close = server_time_sec - just_closed_time
        
        # Fresh if closed within the last interval + some buffer
        if time_since_close < interval_sec * 1.5:
            logger.debug(f"Klines are fresh (closed {time_since_close:.1f}s ago)")
            return True, f"Fresh data (closed {time_since_close:.1f}s ago)"
        else:
            return False, f"Stale data (closed {time_since_close:.1f}s ago, expected < {interval_sec * 1.5}s)"
            
    except Exception as e:
        logger.warning(f"Could not validate klines freshness: {e}")
        return True, "Could not validate (proceeding anyway)"


def get_time_until_candle_close():
    """Calculate seconds until next candle close on Binance time
    
    Returns:
        tuple: (seconds_until_close, next_close_timestamp_ms) for precise scheduling
    """
    try:
        # Get Binance server time
        server_time_ms = binance_client.get_server_time()
        if not server_time_ms:
            logger.warning("Could not get server time, using local time")
            from datetime import datetime
            server_time_ms = int(datetime.now().timestamp() * 1000)
        
        # Convert to milliseconds for precision
        server_time_sec = server_time_ms / 1000
        
        # TIMEFRAME conversion to seconds
        timeframe_map = {
            '1m': 60,
            '5m': 300,
            '15m': 900,
            '1h': 3600,
            '4h': 14400,
            '1d': 86400,
        }
        
        interval_seconds = timeframe_map.get(TIMEFRAME, 300)  # Default 5m
        interval_ms = interval_seconds * 1000
        
        # Calculate next candle close time (aligned to interval boundaries)
        # Candles are aligned to Unix epoch (e.g., 5m candles close at :00, :05, :10...)
        current_candle_start_ms = (server_time_ms // interval_ms) * interval_ms
        next_candle_close_ms = current_candle_start_ms + interval_ms
        
        seconds_until_close = (next_candle_close_ms - server_time_ms) / 1000
        
        # Log for diagnostics
        from datetime import datetime as dt
        next_close_dt = dt.fromtimestamp(next_candle_close_ms / 1000)
        logger.debug(f"Next candle close at {next_close_dt} ({seconds_until_close:.1f}s from now)")
        
        return seconds_until_close, next_candle_close_ms
    except Exception as e:
        logger.error(f"Error calculating candle close time: {e}")
        return 300, None  # Default to 5 minutes


def get_current_position_size():
    """Get current position size from Binance and calculate how many trades are open"""
    try:
        position = binance_client.get_position_info(SYMBOL)
        if position:
            position_amt = abs(float(position['positionAmt']))
            return position_amt
        return 0.0
    except Exception as e:
        logger.error(f"Error getting position size: {e}")
        return 0.0


def can_open_new_trade():
    """Check if we can open a new trade based on current position size vs max allowed"""
    current_position = get_current_position_size()
    max_trades = int(MAX_POSITION_SIZE / SINGLE_TRADE_SIZE)
    current_trades = int(current_position / SINGLE_TRADE_SIZE) if SINGLE_TRADE_SIZE > 0 else 0
    
    can_open = current_position + SINGLE_TRADE_SIZE <= MAX_POSITION_SIZE
    
    logger.info(f"Position check: {current_position:.4f}/{MAX_POSITION_SIZE:.4f} BTC ({current_trades}/{max_trades} trades)")
    
    return can_open, current_trades, max_trades


def sync_positions_with_binance():
    """Synchronize local trade state with actual Binance positions"""
    global rsi_reset_required
    try:
        logger.info("\n" + "=" * 60)
        logger.info("Synchronizing positions with Binance...")
        logger.info("=" * 60)
        
        # Try to get actual positions from Binance for our specific symbol
        positions = binance_client.get_all_positions(symbol=SYMBOL)
        
        if positions is None:
            logger.warning("⚠ Failed to fetch positions from Binance")
            logger.warning("⚠ Position sync unavailable - check API credentials and network")
            # Send Telegram notification for sync failure
            if telegram:
                telegram.notify_sync_failure("Failed to fetch positions - check API credentials, IP whitelist, or network")
            logger.info("=" * 60 + "\n")
            return
        
        # Get recent orders to find entry details (more reliable than trades)
        recent_orders = binance_client.get_all_orders(SYMBOL, limit=100)
        if recent_orders is None:
            logger.warning("⚠ Could not fetch order history, using position data only")
            recent_orders = []
        
        # Track which trades are valid (exist on Binance)
        valid_trade_ids = []
        
        if not positions or len(positions) == 0:
            logger.info(f"✓ No open positions on Binance for {SYMBOL}")
            # Check if local state has trades that shouldn't exist
            if trade_manager.get_trade_count() > 0:
                logger.warning(f"⚠ Local state has {trade_manager.get_trade_count()} open trades but Binance has none")
                logger.warning("⚠ Cleaning up ghost trades...")
                # Remove all trades since Binance has no positions
                trade_manager.cleanup_ghost_trades(valid_trade_ids)
                trade_manager.save_state(get_state_file_path(), rsi_reset_required)
            logger.info("=" * 60 + "\n")
            return
        
        # Sync each position from Binance
        synced_count = 0
        new_position_count = 0  # Track newly discovered positions (not previously tracked)
        for position in positions:
            position_amt = float(position['positionAmt'])
            if position_amt != 0:
                trade_id, is_new = trade_manager.sync_with_binance_position(position, recent_orders)
                if trade_id:
                    valid_trade_ids.append(trade_id)
                    synced_count += 1
                    if is_new:
                        new_position_count += 1
                    entry_price = float(position['entryPrice'])
                    unrealized_pnl = float(position.get('unRealizedProfit', 0))
                    logger.info(f"  Position: {position_amt:.4f} {SYMBOL} @ ${entry_price:.2f}")
                    logger.info(f"  Unrealized PnL: ${unrealized_pnl:.2f}")
        
        # Clean up ghost trades that don't exist on Binance
        ghost_count = trade_manager.cleanup_ghost_trades(valid_trade_ids)
        
        if synced_count > 0:
            logger.info(f"✓ Synced {synced_count} position(s) from Binance")
            if ghost_count > 0:
                logger.info(f"✓ Removed {ghost_count} ghost trade(s)")
            
            # Only set rsi_reset_required = True for NEWLY discovered positions
            # (positions that weren't being tracked before, e.g., opened externally or after crash)
            # Don't touch rsi_reset_required for already-tracked positions
            if new_position_count > 0:
                rsi_reset_required = True
                logger.info(f"🔒 RSI reset required: {new_position_count} NEW position(s) discovered, must wait for RSI > {RSI_RESET_LEVEL}")
            else:
                # All positions were already tracked - preserve existing RSI reset state
                if rsi_reset_required:
                    logger.info(f"🔒 RSI reset still required: waiting for RSI > {RSI_RESET_LEVEL}")
                else:
                    logger.info(f"✓ RSI already reset: ready for new entries when RSI < {RSI_THRESHOLD}")
            
            # Save the synced state (preserves existing rsi_reset_required value unless new positions found)
            trade_manager.save_state(get_state_file_path(), rsi_reset_required)
        else:
            logger.info(f"✓ No positions to sync for {SYMBOL}")
        
        logger.info("=" * 60 + "\n")
        
    except Exception as e:
        logger.error(f"❌ Error syncing positions: {e}", exc_info=True)
        logger.warning("⚠ Bot will continue but may not recover properly from crashes")
        # Send Telegram notification for sync error
        if telegram:
            telegram.notify_sync_failure(str(e))


def initialize():
    """Initialize the trading bot"""
    global binance_client, trade_manager, rsi_reset_required, telegram, candle_ws, macd_ws
    
    logger.info("=" * 60)
    logger.info("Initializing Trading Bot")
    logger.info("=" * 60)
    
    # Initialize Telegram notifier first (so we can send error messages)
    telegram = TelegramNotifier(
        bot_token=TELEGRAM_BOT_TOKEN,
        chat_id=TELEGRAM_CHAT_ID,
        enabled=TELEGRAM_ENABLED
    )
    logger.info(f"✓ Telegram notifier initialized (enabled: {TELEGRAM_ENABLED})")
    
    # Validate API credentials
    if BINANCE_API_KEY == "your_api_key_here" or BINANCE_API_SECRET == "your_api_secret_here":
        logger.error("❌ API credentials not configured in config.py")
        logger.error("Please set BINANCE_API_KEY and BINANCE_API_SECRET")
        sys.exit(1)
    
    # Initialize Binance client
    try:
        binance_client = BinanceAPI(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=DEMO_MODE)
        mode_text = "Demo (Testnet)" if DEMO_MODE else "Live Trading"
        logger.info(f"✓ Connected to Binance {mode_text}")
        logger.warning(f"⚠ Running in {mode_text} mode")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Binance: {e}")
        sys.exit(1)
    
    # Initialize trade manager
    max_trades = int(MAX_POSITION_SIZE / SINGLE_TRADE_SIZE)
    trade_manager = TradeManager(max_trades=max_trades)
    load_result = trade_manager.load_state(get_state_file_path())
    if load_result.get("success"):
        rsi_reset_required = load_result.get("rsi_reset_required", False)
        logger.info(f"✓ Loaded RSI reset state: {rsi_reset_required}")
    logger.info(f"✓ Trade Manager initialized")
    logger.info(f"  Single trade size: {SINGLE_TRADE_SIZE} BTC")
    logger.info(f"  Max position size: {MAX_POSITION_SIZE} BTC")
    logger.info(f"  Max trades allowed: {max_trades}")
    
    # Sync positions with Binance (critical for crash recovery)
    sync_positions_with_binance()
    
    # Set leverage
    if not binance_client.set_leverage(SYMBOL, LEVERAGE):
        logger.warning(f"Could not set leverage to {LEVERAGE}x")
    
    logger.info("=" * 60)
    logger.info("Bot initialized successfully!")
    logger.info("=" * 60)
    
    # Send Telegram notification for bot startup
    telegram.notify_bot_started(
        symbol=SYMBOL,
        timeframe=TIMEFRAME,
        single_trade_size=SINGLE_TRADE_SIZE,
        max_position_size=MAX_POSITION_SIZE,
        leverage=LEVERAGE,
        demo_mode=DEMO_MODE
    )
    
    # Initialize WebSocket for exact candle close data
    try:
        candle_ws = CandleWebSocket(
            api_key=BINANCE_API_KEY,
            api_secret=BINANCE_API_SECRET,
            symbol=SYMBOL,
            timeframe=TIMEFRAME,
            testnet=DEMO_MODE
        )
        if candle_ws.start():
            logger.info(f"✓ WebSocket started for {SYMBOL} {TIMEFRAME}")
        else:
            logger.warning("⚠ WebSocket failed to start, will use REST API fallback")
            candle_ws = None
        
        # Start MACD WebSocket if enabled
        if MACD_FILTER_ENABLED:
            macd_ws = MACDWebSocket(
                api_key=BINANCE_API_KEY,
                api_secret=BINANCE_API_SECRET,
                symbol=SYMBOL,
                timeframe=MACD_TIMEFRAME,
                testnet=DEMO_MODE
            )
            if macd_ws.start():
                logger.info(f"✓ MACD WebSocket started for {SYMBOL} {MACD_TIMEFRAME}")
            else:
                logger.warning("⚠ MACD WebSocket failed to start, will use REST API")
                macd_ws = None
    except Exception as e:
        logger.warning(f"⚠ WebSocket initialization failed: {e}")
        logger.warning("⚠ Will use REST API fallback (slight price drift possible)")
        candle_ws = None
        macd_ws = None


def check_entry_signals():
    """Check for entry signals - place limit order when bullish candle closes below RSI"""
    global last_entry_time, macd_klines, pending_entry_order
    try:
        from datetime import datetime as dt
        import time as time_module
        
        check_start_time = time_module.time()
        
        # Get Binance server time for logging and timing diagnostics
        server_time_ms = binance_client.get_server_time()
        local_time = dt.now()
        
        if server_time_ms:
            binance_time = dt.fromtimestamp(server_time_ms / 1000)
            time_diff_ms = int(local_time.timestamp() * 1000) - server_time_ms
            logger.info(f"\n{'='*60}")
            logger.info(f"Checking signals at {local_time}")
            logger.info(f"Binance server time: {binance_time}")
            logger.info(f"Local vs Binance offset: {time_diff_ms}ms")
        else:
            logger.info(f"\n{'='*60}")
            logger.info(f"Checking signals at {local_time}")
        logger.info(f"{'='*60}")
        
        # If there's already a pending entry order, don't place another one
        if pending_entry_order is not None:
            logger.info(f"ℹ Pending entry order already exists (Order ID: {pending_entry_order['order_id']}) - waiting for fill or cancellation")
            return
        
        # Check if RSI reset is required (after a trade filled)
        if rsi_reset_required:
            logger.info(f"⚠ RSI reset required: Waiting for RSI to close above {RSI_RESET_LEVEL} before placing new orders")
            return
        
        # Check if we can open more trades based on actual Binance position size
        can_open, current_trades, max_trades = can_open_new_trade()
        if not can_open:
            logger.info(f"⚠ Max position size reached ({current_trades}/{max_trades} trades). Skipping entry check.")
            return
        
        # Check cooldown period
        current_time = dt.now()
        if last_entry_time is not None:
            hours_since_last_entry = (current_time - last_entry_time).total_seconds() / 3600
            if hours_since_last_entry < TRADE_COOLDOWN_HOURS:
                logger.info(f"⏳ Cooldown active: {hours_since_last_entry:.2f}h / {TRADE_COOLDOWN_HOURS}h")
                return
        
        # Fetch klines
        wait_for_candle_completion()  # Wait for data to settle
        
        klines = binance_client.get_klines(SYMBOL, TIMEFRAME, limit=100)
        if not klines:
            logger.error("Failed to fetch klines")
            return
        
        # Validate klines are fresh
        is_fresh, freshness_msg = validate_klines_freshness(klines)
        logger.info(f"Klines freshness check: {freshness_msg}")
        if not is_fresh:
            logger.warning(f"⚠ Klines may be stale, proceeding cautiously")
        
        # Try to get exact close price from WebSocket
        ws_candle = None
        if candle_ws and candle_ws.is_connected():
            ws_candle = candle_ws.get_last_closed_candle()
            if ws_candle and candle_ws.is_candle_fresh():
                logger.info(f"✓ Using WebSocket data for exact candle close")
            elif ws_candle:
                logger.debug(f"WebSocket candle available but not fresh")
        
        # Fetch MACD klines if filter enabled
        macd_positive = True
        if MACD_FILTER_ENABLED:
            macd_klines = binance_client.get_klines(SYMBOL, MACD_TIMEFRAME, limit=100)
            if macd_klines:
                # Validate MACD klines freshness too
                is_fresh_macd, _ = validate_klines_freshness(macd_klines)
                if not is_fresh_macd:
                    logger.warning(f"⚠ MACD klines may be stale, using anyway")
                
                # Use last MACD candle (just-closed)
                if len(macd_klines) < 2:
                    logger.warning("Not enough MACD klines")
                    return
                macd_just_closed_idx = -1
                
                # Calculate MACD on higher timeframe (use all klines, last is just-closed)
                import pandas as pd
                macd_data = pd.DataFrame(macd_klines, columns=[
                    'open_time', 'open', 'high', 'low', 'close', 'volume',
                    'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                    'taker_buy_quote', 'ignore'
                ])
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    macd_data[col] = macd_data[col].astype(float)
                macd_result = StrategyAnalyzer.calculate_macd(macd_data)
                macd_data['macd'] = macd_result['macd']
                latest_macd = macd_data['macd'].iloc[-1]  # Now the last one is the just-closed candle
                macd_positive = latest_macd > 0 if not pd.isna(latest_macd) else False
                logger.info(f"MACD value (just-closed candle): {latest_macd:.6f} (Positive: {macd_positive})")
        
        # Find the candle that JUST closed
        if len(klines) < 2:
            logger.warning("Not enough klines data")
            return
        
        # Get candle data - prefer WebSocket for exact close price
        ws_candle_usable = ws_candle and candle_ws and candle_ws.is_candle_fresh()
        if ws_candle_usable:
            # Use WebSocket data for OHLC (exact finalized values)
            last_open = ws_candle['open']
            last_high = ws_candle['high']
            last_close = ws_candle['close']
            last_close_time = ws_candle['close_time']
            last_open_time = ws_candle['open_time']
            logger.info(f"📊 WebSocket candle: O=${last_open:.2f} H=${last_high:.2f} C=${last_close:.2f}")
        else:
            # Fallback to REST API data
            just_closed_idx = -1
            just_closed = klines[just_closed_idx]
            last_open = float(just_closed[1])
            last_high = float(just_closed[2])
            last_close = float(just_closed[4])
            last_close_time = int(just_closed[6])
            last_open_time = int(just_closed[0])
            if candle_ws:
                logger.warning(f"⚠ WebSocket data not available, using REST API (may have slight drift)")
        
        # Log which candle we're analyzing for debugging
        from datetime import datetime as dt
        candle_open_dt = dt.fromtimestamp(last_open_time / 1000)
        candle_close_dt = dt.fromtimestamp(last_close_time / 1000)
        logger.info(f"Analyzing just-closed candle: {candle_open_dt} to {candle_close_dt}")

        
        # Check if bullish
        is_bullish = last_close > last_open
        
        # Calculate RSI
        # If we have WebSocket data, update the last candle's close in klines for accurate RSI
        import pandas as pd
        if ws_candle and candle_ws and candle_ws.is_candle_fresh():
            # Replace the last candle's close with exact WebSocket close
            klines[-1] = list(klines[-1])  # Make mutable
            klines[-1][4] = str(last_close)  # Update close price
        
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        rsi = StrategyAnalyzer.calculate_rsi(df, period=RSI_PERIOD)
        just_closed_rsi = rsi.iloc[-1]  # RSI of the last (just-closed) candle
        
        logger.info(f"Just-closed candle: Bullish={is_bullish}, RSI({RSI_PERIOD})={just_closed_rsi:.2f}, High=${last_high:.2f}, Open=${last_open:.2f}, Close=${last_close:.2f}")
        
        # Strategy: At every candle close, check if RSI < threshold AND candle is bullish
        # If yes -> place STOP-LIMIT order above the bullish candle's high
        # At next candle close -> check if filled, if not cancel
        if is_bullish and just_closed_rsi < RSI_THRESHOLD and macd_positive:
            logger.info(f"✓ BULLISH CANDLE DETECTED with RSI {just_closed_rsi:.2f} < {RSI_THRESHOLD}")
            
            # Check current price to see if opportunity still valid
            current_market_price = binance_client.get_current_price(SYMBOL)
            if not current_market_price:
                logger.warning("Could not get current price, skipping entry")
                return
            
            # Calculate stop-limit prices:
            # Stop price (trigger): When price reaches this, the limit order is activated
            # Limit price (execution): The actual order price
            stop_price = round(last_high + ENTRY_BUFFER, 2)
            limit_price = round(last_high + ENTRY_BUFFER + 0.5, 2)  # Slightly higher for better fill
            
            # Check if price already passed our entry level
            if current_market_price >= stop_price:
                logger.info(f"⚠ Price already at ${current_market_price:.2f}, above stop ${stop_price:.2f} - opportunity missed")
                return
            
            logger.info(f"📝 Placing STOP-LIMIT BUY order:")
            logger.info(f"   Current Price: ${current_market_price:.2f}")
            logger.info(f"   Stop Price (trigger): ${stop_price:.2f}")
            logger.info(f"   Limit Price (execution): ${limit_price:.2f}")
            logger.info(f"   (Bullish high: ${last_high:.2f} + buffer ${ENTRY_BUFFER})")
            
            # Use configured single trade size
            quantity = SINGLE_TRADE_SIZE
            logger.info(f"   Quantity: {quantity} BTC")
            
            # Place STOP-LIMIT buy order
            order = binance_client.place_order(
                symbol=SYMBOL,
                side='BUY',
                order_type='STOP_LIMIT',
                quantity=quantity,
                price=limit_price,
                stop_price=stop_price
            )
            
            # Handle both regular orderId and algoId (for conditional/STOP orders)
            # For STOP orders, check algoId FIRST because it takes priority
            order_id = None
            is_algo_order = False
            if order:
                if 'algoId' in order:
                    # STOP orders return algoId - these are algo/conditional orders
                    order_id = order['algoId']
                    is_algo_order = True
                elif 'orderId' in order:
                    # Regular limit orders return orderId only
                    order_id = order['orderId']
                    is_algo_order = False
            
            if order_id:
                # Log timing for diagnostics
                order_place_time = dt.now()
                elapsed_since_check_start = time_module.time() - check_start_time
                logger.info(f"✓ STOP-LIMIT BUY order placed: {order_id} (algo={is_algo_order})")
                logger.info(f"⏱ Order placed at {order_place_time} (elapsed: {elapsed_since_check_start:.2f}s since check started)")
                
                # Store pending order info (including RSI for notification later)
                pending_entry_order = {
                    'order_id': order_id,
                    'is_algo': is_algo_order,
                    'bullish_high': last_high,
                    'stop_price': stop_price,
                    'limit_price': limit_price,
                    'quantity': quantity,
                    'placed_time': current_time,
                    'rsi': just_closed_rsi  # Store RSI for notification when trade fills
                }
                logger.info(f"⏳ Order will trigger when price reaches ${stop_price:.2f}, executes at ${limit_price:.2f}")
                logger.info(f"   (Will cancel at next candle close if not filled)")
            else:
                logger.error(f"Failed to place STOP-LIMIT buy order. Response: {order}")
        elif is_bullish and just_closed_rsi >= RSI_THRESHOLD:
            logger.info(f"ℹ Bullish candle but RSI {just_closed_rsi:.2f} >= {RSI_THRESHOLD}")
        elif just_closed_rsi < RSI_THRESHOLD and not is_bullish:
            logger.info(f"ℹ RSI {just_closed_rsi:.2f} < {RSI_THRESHOLD} but just-closed candle not bullish (open ${last_open:.2f}, close ${last_close:.2f})")
        elif not is_bullish:
            logger.info(f"ℹ Just-closed candle not bullish (open ${last_open:.2f}, close ${last_close:.2f})")
    
    except Exception as e:
        logger.error(f"❌ Error in check_entry_signals: {e}", exc_info=True)


def check_pending_entry_orders():
    """Check if pending entry limit order was filled or needs to be cancelled"""
    global pending_entry_order, last_entry_time, rsi_reset_required
    try:
        from datetime import datetime as dt
        
        if pending_entry_order is None:
            return  # No pending order
        
        order_id = pending_entry_order['order_id']
        is_algo = pending_entry_order.get('is_algo', False)
        stop_price = pending_entry_order['stop_price']
        limit_price = pending_entry_order['limit_price']
        quantity = pending_entry_order['quantity']
        
        logger.info(f"🔍 Checking pending entry order {order_id} (algo={is_algo})...")
        
        # Check if order is still open based on order type
        order_is_open = False
        algo_status = None
        
        if is_algo:
            # Check algo orders for conditional/STOP orders
            open_algo_orders = binance_client.get_open_algo_orders(SYMBOL)
            if open_algo_orders is None:
                logger.warning("Could not fetch open algo orders")
                return
            
            for order in open_algo_orders:
                # Match by algoId or orderId (fallback returns orderId)
                if order.get('algoId') == order_id or order.get('orderId') == order_id:
                    order_is_open = True
                    algo_status = order.get('algoStatus') or order.get('status')
                    break
        else:
            # Check regular orders
            open_orders = binance_client.get_open_orders(SYMBOL)
            if open_orders is None:
                logger.warning("Could not fetch open orders")
                return
            
            open_order_ids = {order['orderId'] for order in open_orders}
            order_is_open = order_id in open_order_ids
        
        if not order_is_open:
            # Order is no longer open - it was either filled, cancelled, or expired
            logger.info(f"✓ Entry order {order_id} is no longer in open orders list")
            
            # IMPORTANT: Try to cancel anyway in case of race condition or stale data
            # This is a safety measure - cancelling a non-existent order is harmless
            logger.info(f"🔄 Attempting cancel (safety check) for order {order_id}...")
            try:
                binance_client.cancel_order(SYMBOL, order_id, is_algo=is_algo)
                logger.debug(f"Cancel attempt completed for {order_id}")
            except Exception as cancel_err:
                logger.debug(f"Cancel attempt result: {cancel_err} (this is normal if order was already gone)")
            
            # Check if we have a new position (order was filled)
            position = binance_client.get_position_info(SYMBOL)
            if position:
                position_amt = float(position['positionAmt'])
                if position_amt > 0:  # We have a long position
                    entry_price = float(position['entryPrice'])  # Use actual entry from Binance
                    logger.info(f"✓ ENTRY ORDER FILLED! Position opened at ${entry_price:.2f}")
                    
                    # Calculate take profit price (round to tick size 0.10 for BTCUSDT)
                    raw_take_profit = entry_price * (1 + PROFIT_TARGET)
                    take_profit_price = round(raw_take_profit / 0.10) * 0.10  # Round to nearest 0.10
                    logger.info(f"📝 Setting take profit LIMIT SELL at: ${take_profit_price:.2f} ({PROFIT_TARGET*100:.2f}% profit)")
                    
                    # Record in trade manager first (before placing sell order)
                    trade_id = trade_manager.open_trade(
                        entry_price=entry_price,
                        quantity=quantity,
                        position_type='LONG'
                    )
                    
                    # Send Telegram notification immediately for trade entry
                    if telegram and trade_id:
                        telegram.notify_trade_entry(
                            entry_price=entry_price,
                            quantity=quantity,
                            take_profit_price=take_profit_price,
                            rsi=pending_entry_order.get('rsi', 0) if pending_entry_order else 0,
                            position_type='LONG'
                        )
                    
                    # Require RSI reset before allowing new entries
                    rsi_reset_required = True
                    logger.info(f"🔒 RSI reset required: Must wait for candle to close above RSI {RSI_RESET_LEVEL} before new entries")
                    last_entry_time = dt.now()  # Update last entry time for cooldown
                    
                    # Place limit sell order at take profit price
                    sell_order = binance_client.place_order(
                        symbol=SYMBOL,
                        side='SELL',
                        order_type='LIMIT',
                        quantity=quantity,
                        price=take_profit_price
                    )
                    
                    if sell_order and 'orderId' in sell_order:
                        logger.info(f"✓ Take profit LIMIT SELL order placed: {sell_order['orderId']}")
                        
                        # Store the sell order ID in the trade for tracking
                        if trade_id and trade_id in trade_manager.open_trades:
                            trade_manager.open_trades[trade_id]['sell_order_id'] = sell_order['orderId']
                            trade_manager.open_trades[trade_id]['take_profit_price'] = take_profit_price
                        
                        logger.info(f"✓ Trade opened: {trade_id}")
                    else:
                        logger.error("Failed to place take profit LIMIT SELL order")
                        logger.warning("Position opened without take profit - manual intervention needed")
                        # Still store the take profit price for manual reference
                        if trade_id and trade_id in trade_manager.open_trades:
                            trade_manager.open_trades[trade_id]['take_profit_price'] = take_profit_price
                    
                    # Clear pending order
                    pending_entry_order = None
                    return
            
            # Order not filled, was cancelled or expired
            logger.warning(f"⚠ Entry order {order_id} was not filled (cancelled/expired)")
            pending_entry_order = None
        else:
            # Order is still open - cancel it (didn't fill by next candle close)
            logger.info(f"⏰ Entry order {order_id} did NOT fill by next candle close - cancelling...")
            cancelled = binance_client.cancel_order(SYMBOL, order_id, is_algo=is_algo)
            if cancelled:
                logger.info(f"✓ Entry order {order_id} cancelled successfully")
                logger.info(f"ℹ Will wait for next bullish candle (with RSI < {RSI_THRESHOLD}) to place new order")
            else:
                logger.warning(f"⚠ Could not cancel entry order {order_id} - may have filled simultaneously")
                # Double-check position in case it filled while we tried to cancel
                position = binance_client.get_position_info(SYMBOL)
                if position and float(position['positionAmt']) > 0:
                    logger.warning(f"⚠ Position detected! Order may have filled - will handle in next cycle")
            
            # Clear pending order
            pending_entry_order = None
    
    except Exception as e:
        logger.error(f"❌ Error in check_pending_entry_orders: {e}", exc_info=True)


def check_rsi_reset():
    """Check if RSI has closed above reset level to allow new entries"""
    global rsi_reset_required
    try:
        # Only check if reset is currently required
        if not rsi_reset_required:
            return
        
        logger.info(f"\nChecking RSI reset status...")
        
        # Fetch klines to check current RSI
        klines = binance_client.get_klines(SYMBOL, TIMEFRAME, limit=100)
        if not klines:
            logger.warning("Could not fetch klines for RSI reset check")
            return
        
        # Use last candle (just-closed)
        if len(klines) < 2:
            logger.warning("Not enough klines for RSI reset check")
            return
        
        # Try to get exact close from WebSocket
        ws_candle = None
        if candle_ws and candle_ws.is_connected() and candle_ws.is_candle_fresh():
            ws_candle = candle_ws.get_last_closed_candle()
            if ws_candle:
                # Update the last candle's close with exact WebSocket data
                klines[-1] = list(klines[-1])
                klines[-1][4] = str(ws_candle['close'])
        
        # Calculate RSI using all klines
        import pandas as pd
        df = pd.DataFrame(klines, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        
        rsi = StrategyAnalyzer.calculate_rsi(df, period=RSI_PERIOD)
        just_closed_rsi = rsi.iloc[-1]  # RSI of the last (just-closed) candle
        
        logger.info(f"Just-closed candle RSI({RSI_PERIOD}): {just_closed_rsi:.2f} (Reset threshold: {RSI_RESET_LEVEL})")
        
        # Check if RSI closed above reset level
        if just_closed_rsi >= RSI_RESET_LEVEL:
            logger.info(f"✓ RSI RESET COMPLETE: RSI {just_closed_rsi:.2f} >= {RSI_RESET_LEVEL}")
            logger.info(f"🔓 New entry signals are now allowed")
            rsi_reset_required = False
        else:
            logger.info(f"⏳ Still waiting for RSI reset ({just_closed_rsi:.2f} < {RSI_RESET_LEVEL})")
    
    except Exception as e:
        logger.error(f"❌ Error in check_rsi_reset: {e}", exc_info=True)


def check_exit_signals():
    """Check if take profit limit orders have been filled"""
    try:
        from datetime import datetime as dt
        
        # Get Binance server time for logging
        server_time_ms = binance_client.get_server_time()
        if server_time_ms:
            binance_time = dt.fromtimestamp(server_time_ms / 1000)
            logger.info(f"Checking exit signals at {dt.now()} (Binance: {binance_time})")
        else:
            logger.info(f"Checking exit signals at {dt.now()}")
        
        open_trades = trade_manager.get_open_trades()
        if not open_trades:
            logger.debug("No open trades to check for exits")
            return
        
        # Get current price for logging
        current_price = binance_client.get_current_price(SYMBOL)
        if current_price:
            logger.info(f"Current {SYMBOL} price: ${current_price:.2f}")
        
        # Get all open orders to check status
        open_orders = binance_client.get_open_orders(SYMBOL)
        open_order_ids = set()
        if open_orders:
            open_order_ids = {order['orderId'] for order in open_orders}
        
        for trade_id, trade in list(open_trades.items()):
            entry_price = trade['entry_price']
            take_profit_price = trade.get('take_profit_price', entry_price * (1 + PROFIT_TARGET))
            sell_order_id = trade.get('sell_order_id')
            trade_quantity = trade.get('quantity', SINGLE_TRADE_SIZE)
            
            logger.info(f"{trade_id}: Entry ${entry_price:.2f} | TP ${take_profit_price:.2f}")
            
            # Check if the take profit order was filled (not in open orders anymore)
            if sell_order_id and sell_order_id not in open_order_ids:
                # Order is no longer open - verify position was actually reduced
                logger.info(f"✓ Take profit order {sell_order_id} no longer in open orders")
                
                # Safety check: Verify position on Binance before closing trade
                current_position_size = get_current_position_size()
                expected_remaining = max(0, current_position_size)
                
                # Check if position reduced by approximately trade quantity
                # (position should be less than what we had tracked)
                local_tracked_qty = sum(t.get('quantity', 0) for t in open_trades.values())
                
                if current_position_size < local_tracked_qty - (trade_quantity * 0.5):
                    # Position actually reduced - order was filled
                    logger.info(f"✓ Position confirmed reduced: {current_position_size:.4f} BTC (was tracking {local_tracked_qty:.4f})")
                    
                    # Close the trade in our records
                    closed_trade = trade_manager.close_trade(trade_id, take_profit_price)
                    if closed_trade:
                        logger.info(f"✓ Trade closed: PnL={closed_trade['pnl']:.4f} ({closed_trade['pnl_percent']:.4f}%)")
                        
                        # Send Telegram notification for trade closed
                        if telegram:
                            telegram.notify_trade_closed(
                                entry_price=entry_price,
                                exit_price=take_profit_price,
                                quantity=trade_quantity,
                                pnl=closed_trade['pnl'],
                                pnl_percent=closed_trade['pnl_percent']
                            )
                elif current_position_size == 0 and local_tracked_qty > 0:
                    # Position fully closed
                    logger.info(f"✓ Position fully closed on Binance")
                    closed_trade = trade_manager.close_trade(trade_id, take_profit_price)
                    if closed_trade:
                        logger.info(f"✓ Trade closed: PnL={closed_trade['pnl']:.4f} ({closed_trade['pnl_percent']:.4f}%)")
                        
                        # Send Telegram notification for trade closed
                        if telegram:
                            telegram.notify_trade_closed(
                                entry_price=entry_price,
                                exit_price=take_profit_price,
                                quantity=trade_quantity,
                                pnl=closed_trade['pnl'],
                                pnl_percent=closed_trade['pnl_percent']
                            )
                else:
                    # Order might have been cancelled, not filled - position still same
                    logger.warning(f"⚠ Take profit order {sell_order_id} gone but position unchanged ({current_position_size:.4f} BTC)")
                    logger.warning(f"⚠ Order may have been cancelled - manual check required!")
                    
                    # Send Telegram alert
                    if telegram:
                        telegram.notify_error(
                            "Take Profit Order Issue",
                            f"TP order {sell_order_id} disappeared but position still {current_position_size:.4f} BTC. Manual check needed!"
                        )
            else:
                # Still waiting for take profit
                if current_price:
                    current_profit_pct = ((current_price - entry_price) / entry_price) * 100
                    target_profit_pct = PROFIT_TARGET * 100
                    distance_to_tp = ((take_profit_price - current_price) / current_price) * 100
                    logger.debug(f"{trade_id}: Current profit {current_profit_pct:.4f}% | Distance to TP: {distance_to_tp:.4f}%")
    
    except Exception as e:
        logger.error(f"❌ Error in check_exit_signals: {e}", exc_info=True)


def report_status():
    """Log status report"""
    try:
        # Get actual position size from Binance
        current_position = get_current_position_size()
        max_trades = int(MAX_POSITION_SIZE / SINGLE_TRADE_SIZE)
        current_trades = int(current_position / SINGLE_TRADE_SIZE) if SINGLE_TRADE_SIZE > 0 else 0
        
        logger.info(f"\n📊 Status Report at {datetime.now()}")
        logger.info(f"Position: {current_position:.4f}/{MAX_POSITION_SIZE:.4f} BTC ({current_trades}/{max_trades} trades)")
        logger.info(f"RSI reset required: {rsi_reset_required}")
        logger.info(f"Closed trades (session): {len(trade_manager.closed_trades)}")
        
        if trade_manager.closed_trades:
            total_pnl = sum(t['pnl'] for t in trade_manager.closed_trades)
            avg_pnl_percent = sum(t['pnl_percent'] for t in trade_manager.closed_trades) / len(trade_manager.closed_trades)
            logger.info(f"Total PnL: ${total_pnl:.4f} (Avg: {avg_pnl_percent:.4f}%)")
    except Exception as e:
        logger.error(f"Error in report_status: {e}")


def scheduled_job():
    """Main scheduled job - runs every 5 minutes"""
    global sync_counter
    try:
        # Periodic sync every 12 cycles (~1 hour for 5min timeframe)
        sync_counter += 1
        if sync_counter >= 12:
            logger.info("⏰ Periodic sync triggered")
            # Resync time offset
            binance_client.sync_time_offset()
            # Resync positions
            sync_positions_with_binance()
            sync_counter = 0
        
        check_pending_entry_orders()  # Check pending entry orders first
        check_rsi_reset()  # Check if RSI has reset to allow new entries
        check_exit_signals()  # Check existing trades
        check_entry_signals()  # Then check for new entry signals
        report_status()
        trade_manager.save_state(get_state_file_path(), rsi_reset_required)  # Save state with RSI reset flag
    except Exception as e:
        logger.error(f"❌ Error in scheduled job: {e}", exc_info=True)


def schedule_tasks():
    """Schedule tasks to run at each candle close"""
    global next_check_time, next_candle_close_ms
    
    # Calculate initial time until next candle close
    seconds_until_close, next_close_ms = get_time_until_candle_close()
    # Add delay to ensure candle data has propagated from Binance
    total_wait = seconds_until_close + CANDLE_CLOSE_DELAY
    
    # Store absolute candle close timestamp for precise scheduling
    next_candle_close_ms = next_close_ms
    
    from datetime import datetime as dt
    next_check_dt = dt.fromtimestamp((next_close_ms / 1000) + CANDLE_CLOSE_DELAY) if next_close_ms else None
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Candle-Close Based Scheduling Activated")
    logger.info(f"Timeframe: {TIMEFRAME}")
    logger.info(f"Next check in {total_wait:.1f} seconds (includes {CANDLE_CLOSE_DELAY}s delay for data propagation)")
    if next_check_dt:
        logger.info(f"Scheduled for: {next_check_dt}")
    logger.info(f"{'='*60}")
    logger.info("Press Ctrl+C to stop the bot\n")
    
    # First run will be at next candle close + delay (use absolute time)
    next_check_time = time.time() + total_wait


def run_scheduler():
    """Run the scheduler with dynamic candle-close timing"""
    global next_check_time, shutdown_requested
    
    while not shutdown_requested:
        current_time = time.time()
        
        # Check if it's time to run the scheduled job
        if current_time >= next_check_time:
            from datetime import datetime as dt
            job_start_time = time.time()
            logger.info(f"⏱ Job triggered at {dt.now()} (scheduled for {dt.fromtimestamp(next_check_time)})")
            
            scheduled_job()
            
            job_duration = time.time() - job_start_time
            logger.info(f"⏱ Job completed in {job_duration:.2f} seconds")
            
            # IMPORTANT: Get fresh candle close time AFTER job completes
            # This ensures we always align to the NEXT candle close, not a relative offset
            seconds_until_close, next_close_ms = get_time_until_candle_close()
            
            # Use absolute candle close time + delay for next check
            # This prevents drift from job execution time
            if next_close_ms:
                next_check_time = (next_close_ms / 1000) + CANDLE_CLOSE_DELAY
                next_check_dt = dt.fromtimestamp(next_check_time)
                logger.info(f"📅 Next check scheduled for {next_check_dt} ({seconds_until_close:.1f}s until candle close + {CANDLE_CLOSE_DELAY}s delay)")
            else:
                # Fallback to relative timing if we couldn't get absolute time
                next_check_time = time.time() + seconds_until_close + CANDLE_CLOSE_DELAY
                logger.warning(f"⚠ Using relative scheduling (fallback): next check in {seconds_until_close + CANDLE_CLOSE_DELAY:.1f}s")
        
        # Sleep for a short time to avoid busy waiting
        time.sleep(0.5)
    
    logger.info("Scheduler stopped due to shutdown request")


def cleanup():
    """Cleanup function called on exit"""
    global candle_ws, macd_ws
    logger.info("Performing cleanup...")
    
    # Stop WebSocket connections
    if candle_ws:
        try:
            candle_ws.stop()
            logger.info("✓ Candle WebSocket stopped")
        except Exception as e:
            logger.warning(f"Error stopping candle WebSocket: {e}")
    
    if macd_ws:
        try:
            macd_ws.stop()
            logger.info("✓ MACD WebSocket stopped")
        except Exception as e:
            logger.warning(f"Error stopping MACD WebSocket: {e}")
    
    if trade_manager:
        trade_manager.save_state(get_state_file_path(), rsi_reset_required)
        logger.info("✓ Trade state saved")
    remove_pid_file()
    logger.info("✓ Cleanup complete")


def main():
    """Main entry point"""
    try:
        # Change to bot directory for relative imports
        os.chdir(BOT_DIR)
        
        # Create PID file (prevents multiple instances)
        create_pid_file()
        
        # Register cleanup on exit
        atexit.register(cleanup)
        
        # Setup signal handlers for graceful shutdown
        setup_signal_handlers()
        
        # Initialize and run
        initialize()
        schedule_tasks()
        
        # Run the custom scheduler
        run_scheduler()
        
        # If we get here, shutdown was requested
        logger.info("\n⏹ Bot stopped gracefully")
    
    except KeyboardInterrupt:
        logger.info("\n⏹ Bot stopped by user")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        # Cleanup is handled by atexit, but ensure it runs
        pass


if __name__ == "__main__":
    main()
