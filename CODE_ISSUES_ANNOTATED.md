# Annotated Problem Code: Where Sell Order Fails

## File: bot.py, Function: check_pending_entry_orders()
**Lines 615-745**

---

## SECTION 1: Order Status Check (Lines 615-661)

```python
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
        
        # ❌ ISSUE: Check if order is still open based on order type
        order_is_open = False
        algo_status = None
        
        if is_algo:
            # Check algo orders for conditional/STOP orders
            open_algo_orders = binance_client.get_open_algo_orders(SYMBOL)
            if open_algo_orders is None:
                # ❌ ISSUE #1: Returns None on API error or no algo orders
                logger.warning("Could not fetch open algo orders")
                return  # ❌ PROBLEM: Function exits without placing sell order!
            
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
                # ❌ ISSUE #2: Returns None on API error
                logger.warning("Could not fetch open orders")
                return  # ❌ PROBLEM: Function exits without placing sell order!
            
            open_order_ids = {order['orderId'] for order in open_orders}
            order_is_open = order_id in open_order_ids
```

**Problems Here**:
1. If `get_open_algo_orders()` returns `None` → early return, no sell order placed
2. If `get_open_orders()` returns `None` → early return, no sell order placed
3. No attempt to verify if order was filled through alternative method
4. Function assumes order is still pending if fetch fails

---

## SECTION 2: Position Fetch & Verification (Lines 662-710)

```python
        if not order_is_open:
            # Order is no longer open - it was either filled or cancelled
            logger.info(f"✓ Entry order {order_id} is no longer open!")
            
            # ❌ ISSUE #3: Check if we have a new position (order was filled)
            position = binance_client.get_position_info(SYMBOL)
            
            if position:  # ❌ THIS IS WHERE IT FAILS SILENTLY!
                # ❌ ISSUE #4: position is None - code below is COMPLETELY SKIPPED
                # - NO ERROR MESSAGE LOGGED
                # - NO ALTERNATIVE VERIFICATION ATTEMPTED
                # - NO SELL ORDER PLACED
                # - FUNCTION CONTINUES TO "Order not filled" SECTION
                
                position_amt = float(position['positionAmt'])
                
                # ❌ ISSUE #5: What if position_amt is 0 or negative?
                if position_amt > 0:  # ❌ THIS IS WHERE IT FAILS (2nd time)!
                    # If position_amt <= 0:
                    # - NO ERROR MESSAGE LOGGED
                    # - NO SELL ORDER PLACED
                    # - NO TRADE RECORDED
                    # - FUNCTION CONTINUES SILENTLY
                    
                    entry_price = float(position['entryPrice'])  # Use actual entry from Binance
                    logger.info(f"✓ ENTRY ORDER FILLED! Position opened at ${entry_price:.2f}")
                    
                    # Calculate take profit price
                    take_profit_price = round(entry_price * (1 + PROFIT_TARGET), 2)
                    logger.info(f"📝 Setting take profit LIMIT SELL at: ${take_profit_price:.2f} ({PROFIT_TARGET*100:.2f}% profit)")
                    
                    # Place limit sell order immediately at take profit price
                    sell_order = binance_client.place_order(
                        symbol=SYMBOL,
                        side='SELL',
                        order_type='LIMIT',
                        quantity=quantity,
                        price=take_profit_price
                    )
                    
                    # ❌ ISSUE #6: Minimal validation of sell_order response
                    if sell_order and 'orderId' in sell_order:
                        logger.info(f"✓ Take profit LIMIT SELL order placed: {sell_order['orderId']}")
                        
                        # ❌ ISSUE #7: What if sell_order is {}, None, or malformed?
                        # - NO LOGGING OF ACTUAL RESPONSE
                        # - NO DETAILED ERROR MESSAGE
                        
                        # Record in trade manager (use actual entry price from Binance)
                        trade_id = trade_manager.open_trade(
                            entry_price=entry_price,
                            quantity=quantity,
                            position_type='LONG'
                        )
                        
                        # ❌ ISSUE #8: What if trade_id is None?
                        # Store the sell order ID in the trade for tracking
                        if trade_id and trade_id in trade_manager.open_trades:
                            trade_manager.open_trades[trade_id]['sell_order_id'] = sell_order['orderId']
                            trade_manager.open_trades[trade_id]['take_profit_price'] = take_profit_price
                        
                        if trade_id:
                            logger.info(f"✓ Trade opened: {trade_id}")
                            last_entry_time = dt.now()  # Update last entry time for cooldown
                            
                            # Send Telegram notification for trade entry
                            if telegram:
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
                    else:
                        # ❌ ISSUE #9: Generic error without showing actual response
                        logger.error("Failed to place take profit LIMIT SELL order")
                        logger.warning("Position opened without take profit - manual intervention needed")
                        # ❌ BUG: Position is open on Binance but:
                        #    - No sell order placed
                        #    - No trade recorded locally
                        #    - No Telegram notification
                        #    - No manual alert sent
```

**Problems Here**:
1. **Line 659**: If `get_position_info()` returns `None` → entire sell order block skipped silently
2. **Line 664**: If `position_amt <= 0` → entire sell order block skipped silently
3. **Line 677**: If `sell_order` response is invalid → logged but trade not recorded
4. **Line 683**: If `trade_id` is None → sell order placed but not tracked
5. **No logging** of position_amt value
6. **No logging** of actual sell_order response when it fails
7. **No logging** of trade_id when it's None

---

## SECTION 3: Failed Order Handling (Lines 711-745)

```python
            # ❌ ISSUE #10: This section is reached if position is None OR position_amt <= 0
            # Order not filled, was cancelled or expired
            logger.warning(f"⚠ Entry order {order_id} was not filled")
            # ❌ PROBLEM: This message is MISLEADING!
            # The order WAS filled, but we couldn't verify it because:
            # 1. Position fetch failed (returned None), OR
            # 2. Position amount was 0 (timing issue)
            # The trade IS OPEN ON BINANCE but bot thinks order wasn't filled!
            
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
            
            # Clear pending order
            pending_entry_order = None
    
    except Exception as e:
        # ❌ ISSUE #11: Generic exception handler
        # If ANY exception occurs in the whole function, it's caught here
        # But exceptions above are already handled individually, so this shouldn't fire
        logger.error(f"❌ Error in check_pending_entry_orders: {e}", exc_info=True)
```

**Problems Here**:
1. **Line 717**: Misleading message when position fetch failed
2. If position fetch failed, bot thinks order wasn't filled and prepares to cancel
3. Next iteration will try to cancel an order that may have already filled

---

## Summary of Silent Failures

| Line | Condition | If False | Impact |
|------|-----------|----------|--------|
| 640 | `open_algo_orders is not None` | Returns None | No error log, no sell order |
| 648 | `open_orders is not None` | Returns None | No error log, no sell order |
| 659 | `position is not None` | Returns None | Entire block skipped silently |
| 664 | `position_amt > 0` | ≤ 0 | Entire block skipped, no log |
| 677 | `sell_order and 'orderId' in sell_order` | Fails | Generic error, no response logged |
| 683 | `trade_id is not None` | None | Trade created but not recorded |

---

## Data Flow Issue

```
Entry order fills on Binance ✓
│
├─→ Bot checks if order still open: NO ✓
│
├─→ Bot fetches position to verify: NULL/ERROR ❌
│   ├─→ If None: Entire logic block skipped
│   ├─→ If position_amt=0: Entire logic block skipped
│   └─→ No error message logged
│
└─→ Bot thinks order wasn't filled ❌
    └─→ Trade is OPEN on Binance
        but BOT DOESN'T KNOW
        No sell order
        No trade record
        No protection
```
