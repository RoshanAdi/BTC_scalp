# Code Line References: Exact Problem Locations

## Problem Location Map

### 🔴 CRITICAL - Primary Failure Point
**File: bot.py**
**Function: check_pending_entry_orders()**
**Lines: 659-665**

```
Line 659: position = binance_client.get_position_info(SYMBOL)
Line 660: if position:
          ↓
          ❌ If position is None, lines 661-695 are COMPLETELY SKIPPED
          ❌ No error logged
          ❌ No sell order placed
          ❌ No trade recorded
```

**What calls this**:
- Called from `scheduled_job()` at line 950 (before `check_exit_signals`)

**When it's called**:
- At each candle close (every 5 minutes or whatever TIMEFRAME is set)
- Only when a pending entry order exists

---

### 🔴 CRITICAL - Secondary Failure Point  
**File: bot.py**
**Function: check_pending_entry_orders()**
**Lines: 664-695**

```
Line 664: if position_amt > 0:
          ↓
          ❌ If position_amt <= 0, lines 665-695 are COMPLETELY SKIPPED
          ❌ No error logged
          ❌ No sell order placed
          ❌ No trade recorded
```

---

### 🔴 CRITICAL - Tertiary Failure Point (Early Return #1)
**File: bot.py**
**Function: check_pending_entry_orders()**
**Lines: 639-640**

```
Line 639: if open_algo_orders is None:
Line 640:     logger.warning("Could not fetch open algo orders")
Line 641:     return  ❌ EXITS WITHOUT CHECKING FOR FILLED ORDER
```

---

### 🔴 CRITICAL - Quaternary Failure Point (Early Return #2)
**File: bot.py**
**Function: check_pending_entry_orders()**
**Lines: 647-648**

```
Line 647: if open_orders is None:
Line 648:     logger.warning("Could not fetch open orders")
Line 649:     return  ❌ EXITS WITHOUT CHECKING FOR FILLED ORDER
```

---

### 🟡 HIGH - Inadequate Response Validation
**File: bot.py**
**Function: check_pending_entry_orders()**
**Lines: 677-695**

```
Line 677: sell_order = binance_client.place_order(...)
Line 679: if sell_order and 'orderId' in sell_order:
          ↓
          ✓ Success path (lines 680-706)
          
Line 694: else:
Line 695:     logger.error("Failed to place take profit LIMIT SELL order")
          ↓
          ❌ Generic error message
          ❌ No logging of actual sell_order response
          ❌ Can't diagnose what went wrong
```

---

### 🟡 HIGH - Trade Recording Issue
**File: bot.py**
**Function: check_pending_entry_orders()**
**Lines: 683-707**

```
Line 683: trade_id = trade_manager.open_trade(
              entry_price=entry_price,
              quantity=quantity,
              position_type='LONG'
          )

Line 686: if trade_id and trade_id in trade_manager.open_trades:
          ↓
          ❌ What if trade_id is None?
          ❌ What if trade_id not in open_trades?
          ❌ Sell order recorded but trade may not be
```

---

### 🟡 HIGH - Misleading Error Message
**File: bot.py**
**Function: check_pending_entry_orders()**
**Lines: 716-718**

```
Line 716: # Order not filled, was cancelled or expired
Line 717: logger.warning(f"⚠ Entry order {order_id} was not filled")
          ↓
          ❌ MISLEADING: Order may have been filled but:
          ❌ Position fetch failed (returned None), OR
          ❌ Position amount was 0 (timing issue)
          ❌ This message incorrectly indicates order wasn't filled
```

---

## Related Code That Can Fail

### get_position_info() in binance_api.py
**Lines: 322-330**

```python
def get_position_info(self, symbol: str) -> Optional[dict]:
    """Get position information for a symbol"""
    try:
        positions = self.client.futures_position_information(symbol=symbol)
        if positions:
            return positions[0]
        return None  ❌ CAN RETURN NONE
    except Exception as e:
        logger.error(f"Error fetching position info: {e}")
        return None  ❌ CAN RETURN NONE
```

**Called from**: bot.py line 659

**Can return None when**:
- Binance API error
- Network timeout
- Position not yet registered
- Permission denied
- Any exception during API call

---

### get_open_orders() in binance_api.py
**Lines: 210-217**

```python
def get_open_orders(self, symbol: str) -> Optional[List[dict]]:
    """Get all open orders for a symbol"""
    try:
        orders = self.client.futures_get_open_orders(symbol=symbol)
        logger.debug(f"Found {len(orders)} open orders for {symbol}")
        return orders
    except Exception as e:
        logger.error(f"Error fetching open orders: {e}")
        return None  ❌ CAN RETURN NONE
```

**Called from**: bot.py line 649

**Can return None when**:
- Binance API error
- Network timeout
- Any exception during API call

---

### get_open_algo_orders() in binance_api.py
**Lines: 219-242**

```python
def get_open_algo_orders(self, symbol: str) -> Optional[List[dict]]:
    """Get all open algorithmic/conditional orders for a symbol (STOP orders)"""
    try:
        # Try the official algo orders endpoint first
        if hasattr(self.client, 'futures_get_open_algo_orders'):
            orders = self.client.futures_get_open_algo_orders(symbol=symbol)
            logger.debug(f"Found {len(orders)} open algo orders for {symbol}")
            return orders
        
        # Fallback: Check regular open orders for STOP orders
        regular_orders = self.get_open_orders(symbol)
        if regular_orders:
            stop_orders = [o for o in regular_orders if o.get('type') in [...]]
            logger.debug(f"Found {len(stop_orders)} STOP orders in regular orders for {symbol}")
            return stop_orders
        
        return []  ❌ SOMETIMES RETURNS EMPTY LIST (not None)
    except Exception as e:
        logger.error(f"Error fetching open algo orders: {e}")
        return []  ❌ NOW RETURNS EMPTY LIST (not None, which is inconsistent!)
```

**Called from**: bot.py line 638

**Inconsistency**: Returns `[]` in catch block but other functions return `None`

---

## Call Chain

```
scheduled_job() 
  line 950
  ↓
check_pending_entry_orders()
  line 953
  ↓
Checks pending_entry_order global
  line 617
  ↓
Gets open orders/algo orders
  line 638: binance_client.get_open_algo_orders(SYMBOL)
  line 649: binance_client.get_open_orders(SYMBOL)
  ↓
If order no longer open:
  line 659: binance_client.get_position_info(SYMBOL)  ← 🔴 CRITICAL FAILURE POINT
  ↓
If position exists:
  line 664: Check if position_amt > 0  ← 🔴 CRITICAL FAILURE POINT
  ↓
Places sell order:
  line 677: binance_client.place_order(...)  ← 🟡 CAN FAIL
  ↓
Records trade:
  line 683: trade_manager.open_trade(...)  ← 🟡 CAN RETURN None
```

---

## Timeout/Error Scenarios

### Scenario 1: Position Fetch Times Out
```
Time T: Entry BUY order fills on Binance
        But order is still in "PARTIALLY_FILLED" state initially

Time T+1s: Bot calls check_pending_entry_orders()
          Calls binance_client.get_open_orders()
          ✓ Order not in list (filled)
          
          Calls binance_client.get_position_info(SYMBOL)
          ❌ TIMEOUT or API ERROR
          ❌ Returns None
          
          if position:  # None → False
          ❌ ENTIRE SELL BLOCK SKIPPED
          
Result: No sell order placed
        Position open on Binance unprotected
```

### Scenario 2: Position Amount Not Yet Updated
```
Time T: Entry BUY order fills on Binance
        Position created
        But amount not yet propagated through Binance's system

Time T+1s: Bot calls check_pending_entry_orders()
          Calls binance_client.get_position_info(SYMBOL)
          ✓ Returns position dict
          BUT: position['positionAmt'] = 0 (or "0")
          
          if position_amt > 0:  # 0 > 0 → False
          ❌ ENTIRE SELL BLOCK SKIPPED
          
Result: No sell order placed
        Position open on Binance but bot can't see it
```

### Scenario 3: Open Orders Fetch Fails
```
Time T: Entry BUY order fills on Binance

Time T+1s: Bot calls check_pending_entry_orders()
          Calls binance_client.get_open_orders(SYMBOL)
          ❌ NETWORK ERROR
          ❌ Returns None
          
          if open_orders is None:
          logger.warning("Could not fetch open orders")
          return  # ❌ EXITS IMMEDIATELY
          
Result: Function exits without checking if order filled
        No error recovery attempted
        Sell order never placed
```

---

## Key Line Numbers to Watch

| Issue | File | Line | Type |
|-------|------|------|------|
| Early return - algo orders | bot.py | 640 | RETURN |
| Early return - open orders | bot.py | 648 | RETURN |
| Position fetch | bot.py | 659 | CRITICAL |
| Position check | bot.py | 660 | CRITICAL |
| Position amount check | bot.py | 664 | CRITICAL |
| Sell order placed | bot.py | 677 | API CALL |
| Sell order validation | bot.py | 679 | CONDITIONAL |
| Trade recorded | bot.py | 683 | FUNCTION CALL |
| Trade tracking setup | bot.py | 686 | CONDITIONAL |
| Misleading message | bot.py | 717 | LOG MESSAGE |

---

## What Logs to Check

When diagnosing this issue, look for these messages in order:

1. `"🔍 Checking pending entry order 12345 (algo=False)..."`
   - Entry function called ✓

2. `"✓ Entry order 12345 is no longer open!"`
   - Order found not in open orders ✓
   - Now should fetch position...

3. **NEXT MESSAGE SHOULD BE ONE OF THESE:**
   - `"✓ ENTRY ORDER FILLED! Position opened at $45000.00"` ← SUCCESS
   - `"⚠ Entry order 12345 was not filled"` ← POSITION FETCH FAILED or AMOUNT WAS 0
   - `"❌ Failed to place take profit LIMIT SELL order"` ← POSITION OK BUT SELL ORDER FAILED

If message #3 doesn't appear and message #2 does, **position fetch failed**.
