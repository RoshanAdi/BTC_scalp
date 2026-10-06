#!/usr/bin/env python3
"""
WebSocket Manager for capturing exact candle close data from Binance
"""

import logging
import threading
import time
from typing import Optional, Dict, Callable
from binance import ThreadedWebsocketManager

logger = logging.getLogger(__name__)


class CandleWebSocket:
    """
    Manages WebSocket connection to capture exact candle close prices.
    Stores the last closed candle data with finalized OHLCV values.
    """
    
    def __init__(self, api_key: str, api_secret: str, symbol: str, timeframe: str, testnet: bool = False):
        """
        Initialize WebSocket manager
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            symbol: Trading pair (e.g., 'BTCUSDT')
            timeframe: Candle interval (e.g., '5m')
            testnet: If True, use testnet
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.symbol = symbol.lower()  # WebSocket requires lowercase
        self.timeframe = timeframe
        self.testnet = testnet
        
        self.twm: Optional[ThreadedWebsocketManager] = None
        self.socket_name: Optional[str] = None
        self.running = False
        
        # Store the last closed candle (finalized data)
        self.last_closed_candle: Optional[Dict] = None
        self.candle_lock = threading.Lock()
        
        # Callback for when candle closes
        self.on_candle_close: Optional[Callable] = None
        
        # Connection state
        self.connected = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        self.messages_received = 0  # Count messages for debugging
    
    def _handle_socket_message(self, msg: dict):
        """Handle incoming WebSocket messages"""
        try:
            self.messages_received += 1
            
            # Log first few messages to debug format
            if self.messages_received <= 3:
                logger.debug(f"WebSocket msg #{self.messages_received}: {msg}")
            
            # Log periodically
            if self.messages_received % 100 == 0:
                logger.debug(f"WebSocket messages received: {self.messages_received}")
            
            if msg.get('e') == 'error':
                logger.error(f"WebSocket error: {msg}")
                return
            
            # Check if this is a kline message
            # Handle both 'kline' and 'continuous_kline' (futures perpetual contracts)
            event_type = msg.get('e')
            if event_type not in ('kline', 'continuous_kline'):
                if self.messages_received <= 3:
                    logger.debug(f"Non-kline message: event_type={event_type}")
                return
            
            kline = msg.get('k', {})
            
            # Check if candle is closed (x = True means candle is final)
            is_closed = kline.get('x', False)
            
            # Log when candle is about to close
            if is_closed:
                # This is the finalized candle data!
                # Symbol is in different places for kline vs continuous_kline
                symbol = kline.get('s') or msg.get('ps') or self.symbol.upper()
                
                candle_data = {
                    'open_time': kline['t'],      # Open time (ms)
                    'open': float(kline['o']),     # Open price
                    'high': float(kline['h']),     # High price
                    'low': float(kline['l']),      # Low price
                    'close': float(kline['c']),    # Close price (EXACT)
                    'volume': float(kline['v']),   # Volume
                    'close_time': kline['T'],      # Close time (ms)
                    'quote_volume': float(kline['q']),
                    'trades': kline['n'],
                    'interval': kline['i'],
                    'symbol': symbol,
                    'is_final': True
                }
                
                with self.candle_lock:
                    self.last_closed_candle = candle_data
                
                logger.info(f"📊 Candle CLOSED via WebSocket: {self.symbol.upper()} {self.timeframe}")
                logger.info(f"   O: ${candle_data['open']:.2f} | H: ${candle_data['high']:.2f} | L: ${candle_data['low']:.2f} | C: ${candle_data['close']:.2f}")
                
                # Call the callback if set
                if self.on_candle_close:
                    try:
                        self.on_candle_close(candle_data)
                    except Exception as e:
                        logger.error(f"Error in candle close callback: {e}")
            
        except Exception as e:
            logger.error(f"Error handling WebSocket message: {e}", exc_info=True)
    
    def start(self) -> bool:
        """Start the WebSocket connection"""
        try:
            logger.info(f"Starting WebSocket for {self.symbol.upper()} {self.timeframe}...")
            
            # Create ThreadedWebsocketManager
            self.twm = ThreadedWebsocketManager(
                api_key=self.api_key,
                api_secret=self.api_secret,
                testnet=self.testnet
            )
            
            # Start the manager
            self.twm.start()
            
            # Give it a moment to initialize
            time.sleep(1)
            
            # Subscribe to kline stream for futures
            stream_name = f"{self.symbol}@kline_{self.timeframe}"
            self.socket_name = self.twm.start_kline_futures_socket(
                callback=self._handle_socket_message,
                symbol=self.symbol.upper(),
                interval=self.timeframe
            )
            
            self.running = True
            self.connected = True
            self.reconnect_attempts = 0
            
            logger.info(f"✓ WebSocket connected: {stream_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to start WebSocket: {e}", exc_info=True)
            self.running = False
            self.connected = False
            return False
    
    def stop(self):
        """Stop the WebSocket connection"""
        try:
            self.running = False
            self.connected = False
            
            if self.twm:
                self.twm.stop()
                self.twm = None
            
            logger.info("✓ WebSocket stopped")
            
        except Exception as e:
            logger.error(f"Error stopping WebSocket: {e}")
    
    def get_messages_received(self) -> int:
        """Get count of messages received for debugging"""
        return self.messages_received
    
    def get_last_closed_candle(self) -> Optional[Dict]:
        """
        Get the last closed candle data (thread-safe)
        
        Returns:
            Dict with candle data or None if no candle received yet
        """
        with self.candle_lock:
            if self.last_closed_candle:
                return self.last_closed_candle.copy()
            return None
    
    def is_candle_fresh(self, max_age_ms: int = 310000) -> bool:
        """
        Check if the last closed candle is fresh (not too old)
        
        Args:
            max_age_ms: Maximum age in milliseconds (default ~5min + buffer)
        
        Returns:
            True if candle is fresh, False otherwise
        """
        with self.candle_lock:
            if not self.last_closed_candle:
                return False
            
            candle_close_time = self.last_closed_candle['close_time']
            current_time = int(time.time() * 1000)
            age = current_time - candle_close_time
            
            return age < max_age_ms
    
    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self.connected and self.running


# MACD WebSocket for higher timeframe
class MACDWebSocket(CandleWebSocket):
    """WebSocket for MACD timeframe candles"""
    
    def __init__(self, api_key: str, api_secret: str, symbol: str, timeframe: str, testnet: bool = False):
        super().__init__(api_key, api_secret, symbol, timeframe, testnet)
        self.macd_candles: list = []  # Store recent candles for MACD calculation
        self.max_candles = 100  # Keep last 100 candles
    
    def _handle_socket_message(self, msg: dict):
        """Handle incoming WebSocket messages and store for MACD"""
        try:
            if msg.get('e') == 'error':
                logger.error(f"MACD WebSocket error: {msg}")
                return
            
            # Handle both 'kline' and 'continuous_kline' (futures perpetual contracts)
            event_type = msg.get('e')
            if event_type not in ('kline', 'continuous_kline'):
                return
            
            kline = msg.get('k', {})
            is_closed = kline.get('x', False)
            
            if is_closed:
                # Symbol is in different places for kline vs continuous_kline
                symbol = kline.get('s') or msg.get('ps') or self.symbol.upper()
                
                candle_data = {
                    'open_time': kline['t'],
                    'open': float(kline['o']),
                    'high': float(kline['h']),
                    'low': float(kline['l']),
                    'close': float(kline['c']),
                    'volume': float(kline['v']),
                    'close_time': kline['T'],
                    'quote_volume': float(kline['q']),
                    'trades': kline['n'],
                    'interval': kline['i'],
                    'symbol': symbol,
                    'is_final': True
                }
                
                with self.candle_lock:
                    self.last_closed_candle = candle_data
                    self.macd_candles.append(candle_data)
                    # Keep only last N candles
                    if len(self.macd_candles) > self.max_candles:
                        self.macd_candles = self.macd_candles[-self.max_candles:]
                
                logger.debug(f"📊 MACD Candle CLOSED: {self.symbol.upper()} {self.timeframe} C: ${candle_data['close']:.2f}")
                
                if self.on_candle_close:
                    try:
                        self.on_candle_close(candle_data)
                    except Exception as e:
                        logger.error(f"Error in MACD candle close callback: {e}")
            
        except Exception as e:
            logger.error(f"Error handling MACD WebSocket message: {e}", exc_info=True)
    
    def get_macd_candles(self) -> list:
        """Get stored MACD candles for calculation"""
        with self.candle_lock:
            return self.macd_candles.copy()
