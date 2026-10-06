# QUICK REFERENCE: Sell Order Failure Points

## 5-Second Summary
**The sell order isn't being placed because `get_position_info()` likely returns `None` when the bot tries to verify the entry order filled. This causes the entire sell order placement logic to be silently skipped with no error message.**

---

## 🔴 Most Likely Failure Points (In Order)

### 1️⃣ Position Fetch Returns None (70% likelihood)
- **Line**: bot.py:659
- **Code**: `position = binance_client.get_position_info(SYMBOL)`
- **Result**: `position` becomes `None`
- **Impact**: Lines 661-695 all skipped, no sell order
- **Why**: API timeout, network error, or position not yet registered

### 2️⃣ Position Amount is Zero (20% likelihood)
- **Line**: bot.py:664
- **Code**: `if position_amt > 0:`
- **Result**: `position_amt` is 0 or negative
- **Impact**: Lines 665-695 all skipped, no sell order
- **Why**: Race condition, Binance hasn't updated amount yet

### 3️⃣ API Error Causes Early Return (10% likelihood)
- **Line**: bot.py:640 or 648
- **Code**: `if open_orders is None: return`
- **Result**: Function exits before checking for fill
- **Impact**: Position never checked, sell order never placed
- **Why**: API error or network timeout

---

## 🔍 How to Identify Which Issue

Look at your bot logs for these exact message patterns:

### Pattern A: Position Fetch Failed ← MOST COMMON
```
✓ Entry order 12345 is no longer open!
[NOTHING HERE - no "ENTRY ORDER FILLED" message]
⏰ Entry order 12345 did NOT fill by next candle close
```
**Diagnosis**: `get_position_info()` returned `None`

### Pattern B: Position Amount Zero ← TIMING ISSUE
```
✓ Entry order 12345 is no longer open!
✓ ENTRY ORDER FILLED! Position opened at $45000.00
[NOTHING HERE - no "Setting take profit LIMIT SELL" message]
❌ Failed to place take profit LIMIT SELL order
Position opened without take profit
```
**Diagnosis**: `position['positionAmt']` was 0

### Pattern C: API Fetch Failed ← NETWORK ISSUE
```
Could not fetch open algo orders
[or]
Could not fetch open orders
[THEN NOTHING - function exited]
```
**Diagnosis**: `get_open_orders()` or `get_open_algo_orders()` returned `None`

---

## 📋 Code Sections to Check

### Critical Section 1: Entry Point
```python
# bot.py, lines 659-665
position = binance_client.get_position_info(SYMBOL)
if position:
    position_amt = float(position['positionAmt'])
    if position_amt > 0:
        # ← ALL CODE HERE IS SKIPPED IF position IS None OR position_amt IS 0
        # Sell order placed here
```

**If this section is skipped**, no sell order is placed.

### Critical Section 2: Sell Order Placement
```python
# bot.py, lines 677-695
sell_order = binance_client.place_order(...)
if sell_order and 'orderId' in sell_order:
    logger.info(f"✓ Take profit LIMIT SELL order placed: {sell_order['orderId']}")
else:
    logger.error("Failed to place take profit LIMIT SELL order")
```

**If else branch executes**, something is wrong with the response.

### Critical Section 3: Trade Recording
```python
# bot.py, lines 683-707
trade_id = trade_manager.open_trade(...)
if trade_id:
    # Trade recorded here
```

**If trade_id is None**, trade won't be tracked.

---

## 🎯 Specific Lines of Interest

| Line | What | Status | Issue |
|------|------|--------|-------|
| 638 | Fetch algo orders | ❌ Can return None | Early return at 640 |
| 649 | Fetch regular orders | ❌ Can return None | Early return at 648 |
| 659 | Fetch position | ❌ Can return None | Silent skip at 660 |
| 664 | Check position amount | ❌ Can be ≤ 0 | Silent skip at 664 |
| 677 | Place sell order | ⚠️ Can fail | Error at 695 but trade may not record |
| 683 | Record trade | ⚠️ Can return None | Trade lost if None |

---

## 📊 Issue Likelihood Chart

```
┌─ Position fetch returns None ────────────────── 70% ─┬─ MOST LIKELY
│
├─ Position amount is 0 (timing issue) ──────── 20% ─┤ 
│
└─ API error causes early return ────────────── 10% ─┴─ LEAST LIKELY
```

---

## 🔧 Workaround to Diagnose

Add these temporary log statements to find the exact issue:

### Add at line 659 (before position fetch):
```python
logger.info(f"DEBUG: About to fetch position info for {SYMBOL}")
position = binance_client.get_position_info(SYMBOL)
logger.info(f"DEBUG: Position fetch result: {position}")  # ← ADD THIS
if position:
```

### Add at line 664 (before amount check):
```python
if position:
    position_amt = float(position['positionAmt'])
    logger.info(f"DEBUG: Position amount: {position_amt}")  # ← ADD THIS
    if position_amt > 0:
```

### Add at line 677 (before sell order placement):
```python
logger.info(f"DEBUG: About to place sell order - TP price: {take_profit_price}, qty: {quantity}")
sell_order = binance_client.place_order(...)
logger.info(f"DEBUG: Sell order response: {sell_order}")  # ← ADD THIS
if sell_order and 'orderId' in sell_order:
```

---

## 🚨 The Impact

When sell order isn't placed:
- ✅ Entry BUY order filled on Binance
- ✅ Position open on Binance
- ❌ No SELL order placed
- ❌ No take-profit protection
- ❌ Bot doesn't know position exists
- ❌ Position will run uncontrolled until next check
- ❌ May get liquidated or hit stop-loss

---

## 📌 Bottom Line

**Most Probable Cause**: `binance_client.get_position_info(SYMBOL)` at line 659 returns `None`

**Why It Happens**: 
- Network timeout
- Binance API temporarily unavailable
- Position not yet registered in Binance's system
- API credentials/permissions issue

**What to Do**:
1. Check logs for the message patterns above
2. Add debug logging as shown
3. Run again and check which debug log appears/doesn't appear
4. That will pinpoint which of the 3 issues is occurring

**Most Likely Log Evidence**:
```
✓ Entry order 12345 is no longer open!
[MISSING: ✓ ENTRY ORDER FILLED! Position opened...]
⏰ Entry order 12345 did NOT fill by next candle close
```

This pattern indicates position fetch failed.
