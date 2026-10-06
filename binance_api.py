from binance.client import Client
from binance.exceptions import BinanceAPIException
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)


class BinanceAPI:
    """Handles Binance API interactions for futures trading"""
    
    def __init__(self, api_key: str, api_secret: str, testnet: bool = False):
        """
        Initialize Binance client
        
        Args:
            api_key: Binance API key
            api_secret: Binance API secret
            testnet: If True, use testnet (recommended for testing)
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet
        
        # Initialize client
        self.client = Client(
            api_key=api_key,
            api_secret=api_secret,
            testnet=testnet
        )
        
        # Sync with Binance server time to avoid timestamp errors
        try:
            server_time = self.client.get_server_time()
            import time
            time_offset = server_time['serverTime'] - int(time.time() * 1000)
            self.client.timestamp_offset = time_offset
            logger.info(f"Time offset synced: {time_offset}ms")
        except Exception as e:
            logger.warning(f"Could not sync time offset: {e}")
        
        # For futures testnet, we need to explicitly override the FUTURES_URL
        if testnet:
            self.client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'
            logger.info("Connected to Binance Futures Testnet")
            logger.info(f"Futures API URL: {self.client.FUTURES_URL}")
        else:
            logger.info("Connected to Binance Futures Mainnet")
            logger.info(f"Futures API URL: {self.client.FUTURES_URL}")
    
    def sync_time_offset(self) -> bool:
        """Sync time offset with Binance server"""
        try:
            import time
            server_time = self.client.get_server_time()
            time_offset = server_time['serverTime'] - int(time.time() * 1000)
            self.client.timestamp_offset = time_offset
            logger.debug(f"Time offset resynced: {time_offset}ms")
            return True
        except Exception as e:
            logger.warning(f"Could not resync time offset: {e}")
            return False
    
    def get_klines(self, symbol: str, interval: str, limit: int = 100) -> Optional[List]:
        """
        Get klines (candlesticks) data
        
        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Time interval (e.g., '5m', '1h')
            limit: Number of candles to fetch
        
        Returns:
            List of klines or None if error
        """
        try:
            klines = self.client.futures_klines(
                symbol=symbol,
                interval=interval,
                limit=limit
            )
            logger.debug(f"Fetched {len(klines)} klines for {symbol}")
            return klines
        except BinanceAPIException as e:
            logger.error(f"Binance API error: {e}")
            return None
        except Exception as e:
            logger.error(f"Error fetching klines: {e}")
            return None
    
    def get_server_time(self) -> Optional[int]:
        """Get Binance server time in milliseconds"""
        try:
            server_time = self.client.futures_time()
            if isinstance(server_time, dict) and 'serverTime' in server_time:
                return server_time['serverTime']
            return None
        except Exception as e:
            logger.error(f"Error fetching server time: {e}")
            return None
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol"""
        try:
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            price = float(ticker['price'])
            logger.debug(f"Current price for {symbol}: {price}")
            return price
        except Exception as e:
            logger.error(f"Error fetching current price: {e}")
            return None
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """Set leverage for a symbol"""
        try:
            self.client.futures_change_leverage(
                symbol=symbol,
                leverage=leverage
            )
            logger.info(f"Set leverage to {leverage}x for {symbol}")
            return True
        except BinanceAPIException as e:
            logger.error(f"Error setting leverage: {e}")
            return False
    
    def place_order(self, symbol: str, side: str, order_type: str, 
                   quantity: float, price: Optional[float] = None,
                   stop_price: Optional[float] = None,
                   price_protect: bool = True) -> Optional[dict]:
        """
        Place a futures order
        
        Args:
            symbol: Trading pair
            side: 'BUY' or 'SELL'
            order_type: 'LIMIT', 'MARKET', or 'STOP_LIMIT'
            quantity: Order quantity
            price: Price (required for LIMIT and STOP_LIMIT orders)
            stop_price: Stop price (required for STOP_LIMIT orders)
            price_protect: Enable price protection for market orders (reduces slippage)
        
        Returns:
            Order response or None if error
        """
        try:
            if order_type == 'MARKET':
                # Format quantity to proper precision for BTCUSDT (3 decimal places)
                formatted_quantity = f"{quantity:.3f}"
                order = self.client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type='MARKET',
                    quantity=formatted_quantity,
                    priceProtect=price_protect
                )
            elif order_type == 'LIMIT':
                if price is None:
                    logger.error("Price required for LIMIT orders")
                    return None
                # Format price and quantity to proper precision for BTCUSDT
                # Price tick size: 0.10 (1 decimal place)
                # Quantity step size: 0.001 (3 decimal places)
                formatted_price = f"{price:.1f}"
                formatted_quantity = f"{quantity:.3f}"
                order = self.client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type='LIMIT',
                    timeInForce='GTC',
                    quantity=formatted_quantity,
                    price=formatted_price
                )
            elif order_type == 'STOP_LIMIT':
                if price is None or stop_price is None:
                    logger.error("Both price and stop_price required for STOP_LIMIT orders")
                    return None
                # Format price, stop_price and quantity to proper precision for BTCUSDT
                formatted_price = f"{price:.1f}"
                formatted_stop_price = f"{stop_price:.1f}"
                formatted_quantity = f"{quantity:.3f}"
                # For Binance Futures STOP orders (buy when price breaks UP)
                # Use STOP order type with limit price
                order = self.client.futures_create_order(
                    symbol=symbol,
                    side=side,
                    type='STOP',  # STOP order for futures
                    timeInForce='GTC',
                    quantity=formatted_quantity,
                    price=formatted_price,  # Limit price (execution price)
                    stopPrice=formatted_stop_price  # Trigger price
                )
            else:
                logger.error(f"Unknown order type: {order_type}")
                return None
            
            logger.info(f"Order placed: {side} {quantity} {symbol} at {price}")
            logger.debug(f"Order response: {order}")
            return order
        except BinanceAPIException as e:
            logger.error(f"Binance API error placing order: {e}")
            return None
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            return None
    
    def cancel_order(self, symbol: str, order_id: int, is_algo: bool = False) -> bool:
        """Cancel an open order
        
        Args:
            symbol: Trading pair
            order_id: The order ID (orderId for regular orders, algoId for conditional orders)
            is_algo: If True, treat as algorithmic/conditional order (STOP orders)
        """
        try:
            if is_algo:
                self.client.futures_cancel_algo_order(symbol=symbol, algoId=order_id)
                logger.info(f"Cancelled algo order {order_id}")
            else:
                self.client.futures_cancel_order(symbol=symbol, orderId=order_id)
                logger.info(f"Cancelled order {order_id}")
            return True
        except Exception as e:
            logger.error(f"Error cancelling order: {e}")
            return False
    
    def get_open_orders(self, symbol: str) -> Optional[List[dict]]:
        """Get all open orders for a symbol"""
        try:
            orders = self.client.futures_get_open_orders(symbol=symbol)
            logger.debug(f"Found {len(orders)} open orders for {symbol}")
            return orders
        except Exception as e:
            logger.error(f"Error fetching open orders: {e}")
            return None
    
    def get_open_algo_orders(self, symbol: str) -> Optional[List[dict]]:
        """Get all open algorithmic/conditional orders for a symbol (STOP orders)
        
        Note: Some versions of the Binance library don't support algo orders.
        This method will try multiple approaches and return None if unavailable.
        """
        try:
            # Try the official algo orders endpoint first
            if hasattr(self.client, 'futures_get_open_algo_orders'):
                orders = self.client.futures_get_open_algo_orders(symbol=symbol)
                logger.debug(f"Found {len(orders)} open algo orders for {symbol}")
                return orders
            
            # Fallback: Check regular open orders for STOP orders
            # STOP orders may appear in regular orders depending on Binance version
            regular_orders = self.get_open_orders(symbol)
            if regular_orders:
                stop_orders = [o for o in regular_orders if o.get('type') in ['STOP', 'STOP_MARKET', 'TAKE_PROFIT', 'TAKE_PROFIT_MARKET']]
                logger.debug(f"Found {len(stop_orders)} STOP orders in regular orders for {symbol}")
                return stop_orders
            
            return []
        except Exception as e:
            logger.error(f"Error fetching open algo orders: {e}")
            # Return empty list instead of None to avoid breaking the caller
            return []
    
    def get_algo_order_status(self, symbol: str, algo_id: int) -> Optional[dict]:
        """Get status of a specific algo order"""
        try:
            # First try the open algo orders
            open_algo = self.get_open_algo_orders(symbol)
            if open_algo:
                for order in open_algo:
                    if order.get('algoId') == algo_id or order.get('orderId') == algo_id:
                        return order
            
            # Check regular open orders (STOP orders may be here)
            regular_orders = self.get_open_orders(symbol)
            if regular_orders:
                for order in regular_orders:
                    if order.get('orderId') == algo_id:
                        return order
            
            # Order not found in open orders - check history
            try:
                if hasattr(self.client, 'futures_get_algo_orders'):
                    history = self.client.futures_get_algo_orders(symbol=symbol)
                    for order in history:
                        if order.get('algoId') == algo_id:
                            return order
            except Exception:
                pass
            
            # Try checking all orders history
            try:
                all_orders = self.get_all_orders(symbol, limit=50)
                if all_orders:
                    for order in all_orders:
                        if order.get('orderId') == algo_id:
                            return order
            except Exception:
                pass
            
            return None
        except Exception as e:
            logger.error(f"Error fetching algo order status: {e}")
            return None
    
    def get_account_info(self) -> Optional[dict]:
        """Get account information"""
        try:
            if self.testnet:
                try:
                    balances = self.client.futures_account_balance()
                    return {"balances": balances}
                except Exception as e:
                    logger.warning(f"Testnet account balance endpoint unavailable: {e}")
                    try:
                        account = self.client.futures_account()
                        return account
                    except Exception as e2:
                        logger.warning(f"Testnet account endpoint unavailable: {e2}")
                        return {
                            "testnet": True,
                            "note": "Account info not available on testnet",
                        }
            return self.client.futures_account()
        except Exception as e:
            logger.error(f"Error fetching account info: {e}")
            return None
    
    def get_position_info(self, symbol: str) -> Optional[dict]:
        """Get position information for a symbol"""
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            if positions:
                return positions[0]
            return None
        except Exception as e:
            logger.error(f"Error fetching position info: {e}")
            return None
    
    def get_recent_trades(self, symbol: str, limit: int = 100) -> Optional[List[dict]]:
        """Get recent account trades for a symbol"""
        try:
            trades = self.client.futures_account_trades(symbol=symbol, limit=limit)
            logger.debug(f"Fetched {len(trades)} recent trades for {symbol}")
            return trades
        except Exception as e:
            logger.error(f"Error fetching recent trades: {e}")
            return None
    
    def get_all_orders(self, symbol: str, limit: int = 100) -> Optional[List[dict]]:
        """Get all orders for a symbol (more reliable than trades for entry tracking)"""
        try:
            orders = self.client.futures_get_all_orders(symbol=symbol, limit=limit)
            logger.debug(f"Fetched {len(orders)} orders for {symbol}")
            return orders
        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return None
    
    def get_all_positions(self, symbol: Optional[str] = None) -> Optional[List[dict]]:
        """Get all open positions, optionally filtered by symbol"""
        try:
            # Try to get position information
            if symbol:
                positions = self.client.futures_position_information(symbol=symbol)
            else:
                positions = self.client.futures_position_information()
            
            # Filter only positions with non-zero quantity
            open_positions = [p for p in positions if float(p['positionAmt']) != 0]
            logger.info(f"Successfully fetched positions - {len(open_positions)} open position(s)")
            return open_positions
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return None

    
    def close_position(self, symbol: str) -> Optional[dict]:
        """Close an open position with a market order (emergency close only)"""
        try:
            # Get current position
            position = self.get_position_info(symbol)
            if not position:
                logger.warning(f"No position found for {symbol}")
                return None
            
            quantity = float(position['positionAmt'])
            if quantity == 0:
                logger.warning(f"No open position for {symbol}")
                return None
            
            # Close position with opposite order
            side = 'SELL' if quantity > 0 else 'BUY'
            order = self.place_order(
                symbol=symbol,
                side=side,
                order_type='MARKET',
                quantity=abs(quantity)
            )
            return order
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return None
