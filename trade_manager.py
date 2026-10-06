import json
from datetime import datetime
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


class TradeManager:
    """Manages open positions and trade history"""
    
    def __init__(self, max_trades: int = 3):
        self.max_trades = max_trades
        self.open_trades: Dict[str, dict] = {}  # trade_id: trade_data
        self.closed_trades: List[dict] = []
        self.trade_counter = 0
    
    def can_open_trade(self) -> bool:
        """Check if we can open a new trade"""
        return len(self.open_trades) < self.max_trades
    
    def open_trade(self, entry_price: float, quantity: float, 
                   position_type: str = "LONG") -> Optional[str]:
        """
        Open a new trade
        Returns trade_id if successful, None otherwise
        """
        if not self.can_open_trade():
            logger.warning(f"Max trades ({self.max_trades}) reached, cannot open new trade")
            return None
        
        self.trade_counter += 1
        trade_id = f"TRADE_{self.trade_counter}"
        
        self.open_trades[trade_id] = {
            "trade_id": trade_id,
            "entry_price": entry_price,
            "quantity": quantity,
            "position_type": position_type,
            "entry_time": datetime.now().isoformat(),
            "status": "OPEN"
        }
        
        logger.info(f"Opened trade {trade_id}: {position_type} @ {entry_price} qty={quantity}")
        return trade_id
    
    def close_trade(self, trade_id: str, exit_price: float) -> Optional[dict]:
        """
        Close a trade and calculate P&L
        Returns trade data if successful, None otherwise
        """
        if trade_id not in self.open_trades:
            logger.error(f"Trade {trade_id} not found in open trades")
            return None
        
        trade = self.open_trades[trade_id]
        entry_price = trade["entry_price"]
        quantity = trade["quantity"]
        
        if trade["position_type"] == "LONG":
            pnl = (exit_price - entry_price) * quantity
            pnl_percent = ((exit_price - entry_price) / entry_price) * 100
        else:
            pnl = (entry_price - exit_price) * quantity
            pnl_percent = ((entry_price - exit_price) / entry_price) * 100
        
        trade["exit_price"] = exit_price
        trade["exit_time"] = datetime.now().isoformat()
        trade["pnl"] = pnl
        trade["pnl_percent"] = pnl_percent
        trade["status"] = "CLOSED"
        
        self.closed_trades.append(trade)
        del self.open_trades[trade_id]
        
        logger.info(f"Closed trade {trade_id}: PnL={pnl:.2f} ({pnl_percent:.4f}%)")
        return trade
    
    def get_open_trades(self) -> Dict[str, dict]:
        """Get all open trades"""
        return self.open_trades.copy()
    
    def get_trade_count(self) -> int:
        """Get number of open trades"""
        return len(self.open_trades)
    
    def save_state(self, filepath: str, rsi_reset_required: bool = False) -> None:
        """Save trade state to JSON file"""
        state = {
            "open_trades": self.open_trades,
            "closed_trades": self.closed_trades,
            "trade_counter": self.trade_counter,
            "rsi_reset_required": rsi_reset_required,
            "saved_at": datetime.now().isoformat()
        }
        try:
            with open(filepath, 'w') as f:
                json.dump(state, f, indent=2)
            logger.info(f"Trade state saved to {filepath}")
        except Exception as e:
            logger.error(f"Failed to save trade state: {e}")
    
    def load_state(self, filepath: str) -> dict:
        """Load trade state from JSON file
        
        Returns:
            dict with 'success' (bool) and 'rsi_reset_required' (bool)
        """
        try:
            with open(filepath, 'r') as f:
                state = json.load(f)
            self.open_trades = state.get("open_trades", {})
            self.closed_trades = state.get("closed_trades", [])
            self.trade_counter = state.get("trade_counter", 0)
            rsi_reset_required = state.get("rsi_reset_required", False)
            logger.info(f"Trade state loaded from {filepath}")
            logger.info(f"RSI reset required: {rsi_reset_required}")
            return {"success": True, "rsi_reset_required": rsi_reset_required}
        except FileNotFoundError:
            logger.info(f"No previous trade state found at {filepath}")
            return {"success": False, "rsi_reset_required": False}
        except Exception as e:
            logger.error(f"Failed to load trade state: {e}")
            return {"success": False, "rsi_reset_required": False}
    
    def sync_with_binance_position(self, position: dict, recent_orders: List[dict] = None) -> tuple:
        """Sync local state with an actual Binance position
        
        Args:
            position: Position data from Binance
            recent_orders: Recent orders to find entry time and details
            
        Returns:
            Tuple of (trade_id, is_new_sync) where is_new_sync is True if this is a newly discovered position
        """
        try:
            quantity = float(position['positionAmt'])
            entry_price = float(position['entryPrice'])
            
            # Determine position type
            position_type = "LONG" if quantity > 0 else "SHORT"
            quantity = abs(quantity)
            
            # Check if we already have this position tracked
            for trade_id, trade in self.open_trades.items():
                if (abs(trade['quantity'] - quantity) < 0.0001 and 
                    trade['position_type'] == position_type):
                    logger.info(f"Position already tracked as {trade_id}")
                    # Update entry price if it differs (Binance has the truth)
                    if abs(trade['entry_price'] - entry_price) > 0.01:
                        logger.warning(f"Updating entry price: {trade['entry_price']:.2f} -> {entry_price:.2f}")
                        trade['entry_price'] = entry_price
                    return (trade_id, False)  # Existing position, not new
            
            # Create new trade for untracked position
            self.trade_counter += 1
            trade_id = f"TRADE_{self.trade_counter}_SYNCED"
            
            # Try to find entry time from recent orders
            entry_time = datetime.now().isoformat()
            if recent_orders:
                for order in reversed(recent_orders):  # Most recent first
                    # Look for filled BUY orders for LONG positions
                    if (order.get('status') == 'FILLED' and 
                        order.get('side') == 'BUY' and 
                        position_type == 'LONG'):
                        entry_time = datetime.fromtimestamp(int(order['updateTime'])/1000).isoformat()
                        break
                    # Look for filled SELL orders for SHORT positions
                    elif (order.get('status') == 'FILLED' and 
                          order.get('side') == 'SELL' and 
                          position_type == 'SHORT'):
                        entry_time = datetime.fromtimestamp(int(order['updateTime'])/1000).isoformat()
                        break
            
            self.open_trades[trade_id] = {
                "trade_id": trade_id,
                "entry_price": entry_price,
                "quantity": quantity,
                "position_type": position_type,
                "entry_time": entry_time,
                "status": "OPEN",
                "synced": True  # Mark as synced from Binance
            }
            
            logger.info(f"✓ Synced position from Binance: {trade_id} - {position_type} @ {entry_price} qty={quantity}")
            return (trade_id, True)  # Newly discovered position
            
        except Exception as e:
            logger.error(f"Error syncing position: {e}")
            return (None, False)
    
    def clear_all_trades(self) -> None:
        """Clear all open trades (use with caution)"""
        self.open_trades.clear()
        logger.warning("All open trades cleared")
    
    def cleanup_ghost_trades(self, valid_trade_ids: List[str]) -> int:
        """Remove trades that don't exist on Binance
        
        Args:
            valid_trade_ids: List of trade IDs that actually exist on Binance
            
        Returns:
            Number of ghost trades removed
        """
        ghost_trades = []
        for trade_id in list(self.open_trades.keys()):
            if trade_id not in valid_trade_ids:
                ghost_trades.append(trade_id)
        
        for trade_id in ghost_trades:
            logger.warning(f"⚠ Removing ghost trade {trade_id} - not found on Binance")
            del self.open_trades[trade_id]
        
        if ghost_trades:
            logger.info(f"✓ Cleaned up {len(ghost_trades)} ghost trade(s): {', '.join(ghost_trades)}")
        
        return len(ghost_trades)
