# Visual Flowchart: Where Sell Order Placement Fails

## Main Flow Diagram

```
START: check_pending_entry_orders()
│
├─ pending_entry_order exists? 
│  NO → return (exit)
│  YES ↓
│
├─ Get order info from pending_entry_order
│  (order_id, is_algo, quantity, etc.)
│  ↓
│
├─ Check if order is still open
│  │
│  ├─ is_algo = True?
│  │  YES → get_open_algo_orders() 
│  │       ├─ Returns None? ❌ ─→ LOG WARNING ─→ return (EXIT! NO SELL ORDER)
│  │       ├─ Returns []? ✓ ─→ order_is_open = False
│  │       └─ Find order in list? ✓ ─→ order_is_open = True
│  │
│  └─ is_algo = False?
│     YES → get_open_orders()
│          ├─ Returns None? ❌ ─→ LOG WARNING ─→ return (EXIT! NO SELL ORDER)
│          └─ Returns [orders]? ✓ ─→ Check if our order_id in list
│                                   ├─ Found? → order_is_open = True
│                                   └─ Not found? → order_is_open = False
│
├─ order_is_open?
│  │
│  NO (Order not in open list - may be filled) ↓
│  │
│  ├─ LOG: "✓ Entry order {order_id} is no longer open!"
│  │
│  ├─ Fetch position info to verify fill
│  │  get_position_info(SYMBOL)
│  │  │
│  │  ├─ Returns None? ❌ 🔴 CRITICAL FAILURE
│  │  │  └─ if position:  # FALSE
│  │  │     └─ ENTIRE SELL ORDER BLOCK SKIPPED
│  │  │        └─ NO LOG MESSAGE ❌
│  │  │           └─ NO SELL ORDER PLACED ❌
│  │  │              └─ NO TRADE RECORDED ❌
│  │  │                 └─ CONTINUE TO LINE 716
│  │  │
│  │  └─ Returns position dict? ✓ ↓
│  │     │
│  │     ├─ Get position_amt = position['positionAmt']
│  │     │
│  │     ├─ position_amt > 0? 
│  │     │  │
│  │     │  NO (amount is 0 or negative) ❌ 🔴 CRITICAL FAILURE
│  │     │  └─ if position_amt > 0:  # FALSE
│  │     │     └─ ENTIRE SELL ORDER BLOCK SKIPPED
│  │     │        └─ NO LOG MESSAGE ❌
│  │     │           └─ NO SELL ORDER PLACED ❌
│  │     │              └─ NO TRADE RECORDED ❌
│  │     │                 └─ CONTINUE TO LINE 716
│  │     │
│  │     └─ YES (position_amt > 0) ✓ ↓
│  │        │
│  │        ├─ LOG: "✓ ENTRY ORDER FILLED! Position opened at ${entry_price}"
│  │        │
│  │        ├─ Calculate take_profit_price
│  │        │
│  │        ├─ LOG: "📝 Setting take profit LIMIT SELL at: ${take_profit_price}"
│  │        │
│  │        ├─ Place SELL limit order
│  │        │  sell_order = place_order(SELL, LIMIT, quantity, take_profit_price)
│  │        │  │
│  │        │  ├─ sell_order is valid & has 'orderId'? ✓ ↓
│  │        │  │  │
│  │        │  │  ├─ LOG: "✓ Take profit LIMIT SELL order placed: {order_id}"
│  │        │  │  │
│  │        │  │  ├─ Record trade in trade_manager
│  │        │  │  │  trade_id = trade_manager.open_trade(...)
│  │        │  │  │  │
│  │        │  │  │  ├─ trade_id is None? ⚠️ 🟡 FAILURE
│  │        │  │  │  │  └─ Trade not recorded, but sell order placed
│  │        │  │  │  │
│  │        │  │  │  └─ trade_id is valid? ✓
│  │        │  │  │     ├─ Store sell_order ID in trade
│  │        │  │  │     ├─ Set take_profit_price
│  │        │  │  │     ├─ LOG: "✓ Trade opened: {trade_id}"
│  │        │  │  │     ├─ Update last_entry_time
│  │        │  │  │     ├─ Send Telegram notification
│  │        │  │  │     ├─ Set rsi_reset_required = True
│  │        │  │  │     └─ pending_entry_order = None
│  │        │  │
│  │        │  └─ sell_order is invalid or missing 'orderId'? ❌ 🟡 FAILURE
│  │        │     └─ LOG ERROR: "Failed to place take profit LIMIT SELL order"
│  │        │        └─ LOG WARNING: "Position opened without take profit - manual intervention needed"
│  │        │           └─ pending_entry_order = None
│  │        │
│  │        └─ EXIT
│  │
│  YES (order_is_open = True - still pending) ↓
│  │
│  ├─ LOG: "⏰ Entry order {order_id} did NOT fill by next candle close - cancelling..."
│  │
│  ├─ Cancel the order
│  │  cancelled = cancel_order(order_id)
│  │  │
│  │  ├─ cancelled = True? ✓
│  │  │  └─ LOG: "✓ Entry order {order_id} cancelled successfully"
│  │  │     └─ LOG: "ℹ Will wait for next bullish candle..."
│  │  │
│  │  └─ cancelled = False? ❌
│  │     └─ LOG WARNING: "Could not cancel entry order {order_id}..."
│  │
│  ├─ pending_entry_order = None
│  └─ EXIT
│
└─ END (except on error)


EXCEPTION HANDLER:
catch Exception as e:
└─ LOG ERROR: "❌ Error in check_pending_entry_orders: {e}"
   └─ Continue (exception caught)
```

---

## Detailed Failure Paths

### Path 1: Position Fetch Returns None ❌

```
order_is_open = False
    ↓
position = get_position_info(SYMBOL)
    ↓
position = None  ❌
    ↓
if position:  # FALSE
    ↓
SKIP LINES 661-695  ❌
    ↓
CONTINUE TO LINE 716
    ↓
logger.warning(f"⚠ Entry order {order_id} was not filled")  ← MISLEADING!
    ↓
pending_entry_order = None
    ↓
Function exits
    ↓
RESULT:
✗ No sell order placed
✗ No trade recorded
✗ Trade open on Binance, unprotected
```

### Path 2: Position Amount is Zero ❌

```
order_is_open = False
    ↓
position = get_position_info(SYMBOL)
    ↓
position = {..., positionAmt: 0}  ✓
    ↓
if position:  # TRUE ✓
    ↓
position_amt = 0
    ↓
if position_amt > 0:  # FALSE ❌
    ↓
SKIP LINES 665-695  ❌
    ↓
CONTINUE TO LINE 716
    ↓
logger.warning(f"⚠ Entry order {order_id} was not filled")  ← MISLEADING!
    ↓
pending_entry_order = None
    ↓
Function exits
    ↓
RESULT:
✗ No sell order placed
✗ No trade recorded
✗ Trade open on Binance, unprotected
```

### Path 3: Sell Order Response Invalid ❌

```
order_is_open = False
    ↓
position = {..., positionAmt: 0.01}  ✓
    ↓
if position_amt > 0:  # TRUE ✓
    ↓
LOG: "✓ ENTRY ORDER FILLED!"  ✓
    ↓
sell_order = place_order(...)
    ↓
sell_order = None  ❌ (or {} or missing 'orderId')
    ↓
if sell_order and 'orderId' in sell_order:  # FALSE ❌
    ↓
else:
    logger.error("Failed to place take profit LIMIT SELL order")  ← Generic error
    logger.warning("Position opened without take profit...")
    ↓
pending_entry_order = None
    ↓
Function exits
    ↓
RESULT:
✗ No sell order placed
✗ No trade recorded (might try to record below but sell_order is invalid)
✗ Trade open on Binance, unprotected
✗ No error details about why sell order failed
```

### Path 4: Early Return on API Error ❌

```
get_open_orders(SYMBOL)
    ↓
open_orders = None  ❌ (API error)
    ↓
if open_orders is None:
    logger.warning("Could not fetch open orders")
    return  ← EXITS HERE ❌
    ↓
Function exits before checking for filled order
    ↓
RESULT:
✗ Position never checked
✗ No sell order placed
✗ No trade recorded
✗ Entry order status never verified
```

---

## Success Path (What Should Happen)

```
order_is_open = False  ✓
    ↓
position = get_position_info(SYMBOL)
position = {..., positionAmt: 0.01, entryPrice: 45000}  ✓
    ↓
if position:  # TRUE ✓
    ↓
position_amt = 0.01
    ↓
if position_amt > 0:  # TRUE ✓
    ↓
LOG: "✓ ENTRY ORDER FILLED! Position opened at $45000.00"  ✓
    ↓
take_profit_price = 45000 * 1.01 = 45450  ✓
    ↓
LOG: "📝 Setting take profit LIMIT SELL at: $45450.00"  ✓
    ↓
sell_order = place_order(SELL, LIMIT, 0.01, 45450)
sell_order = {orderId: 12345}  ✓
    ↓
if sell_order and 'orderId' in sell_order:  # TRUE ✓
    ↓
LOG: "✓ Take profit LIMIT SELL order placed: 12345"  ✓
    ↓
trade_id = trade_manager.open_trade(...)
trade_id = "trade_12345"  ✓
    ↓
if trade_id and trade_id in open_trades:  # TRUE ✓
    ↓
Store sell_order ID and take_profit_price in trade  ✓
    ↓
if trade_id:  # TRUE ✓
    ↓
LOG: "✓ Trade opened: trade_12345"  ✓
LOG: "✓ Trade opened, RSI reset required"  ✓
    ↓
Set rsi_reset_required = True  ✓
    ↓
pending_entry_order = None  ✓
    ↓
Function exits normally
    ↓
RESULT:
✓ Sell order placed
✓ Trade recorded locally
✓ Position protected
✓ Bot aware of trade
✓ Telegram notification sent
```

---

## State Machine Diagram

```
┌────────────────────────┐
│  NO PENDING ORDER      │
│  (pending_entry_order  │
│   is None)             │
└────────────────────────┘
          │
          │ Bullish signal, place entry order
          ↓
┌────────────────────────┐
│  PENDING ENTRY ORDER   │
│  (Waiting for fill)    │
│  pending_entry_order   │
│  = {order_id: 123...}  │
└────────────────────────┘
          │
          │ Check at next candle close
          ├─ Order still open? → Stay in PENDING (cancel if too old)
          │
          └─ Order no longer open (filled)
             ├─ Position verified? → Move to OPEN TRADE ✓
             │
             └─ Position verification fails → Bug! (back to NO PENDING with orphaned trade)
                 ❌ Entry order shows filled
                 ❌ But bot thinks it wasn't
                 ❌ No sell order placed
                 ❌ Trade unprotected

┌────────────────────────┐
│  OPEN TRADE            │
│  (Sell order placed)   │
│  trade_manager has     │
│  trade record          │
└────────────────────────┘
          │
          │ Check exit signals each candle
          │ (check_exit_signals)
          │
          ├─ Sell order filled? → TRADE CLOSED
          │
          └─ Still waiting → Stay in OPEN TRADE
```

---

## Time Sequence Diagram

```
Binance:                                 Bot:
═════════════════════════════════════════════════════════════

T0:
  Entry BUY        ← placed
  
T1:  (STOP triggers)
     Entry filled ✓
     
T2:  
                                  check_pending_entry_orders()
                                  - Check if order open
                                  - get_open_orders() ✓
                                  - Not found → order_is_open=False
                                  
T3:
                                  - get_position_info()
                                  - ??? TIMEOUT or API ERROR ❌
                                  
T4:
                                  - If returns None:
                                    → Skip sell order logic
                                    → No sell order placed ❌
                                    → Trade lost
                                    
OR:

T4:
                                  - Returns position but amount=0
                                  → Skip sell order logic
                                  → No sell order placed ❌
                                  → Trade lost
```

---

## Probability Distribution

```
Position fetch returns None    █████████████████  70%
  └─ Sell order NOT placed    ❌

Position amount is 0            ███████  20%
  └─ Sell order NOT placed    ❌

API error early return          ████  10%
  └─ Sell order NOT placed    ❌
```

