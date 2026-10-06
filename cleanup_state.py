#!/usr/bin/env python3
"""
Cleanup script to fix trade state and cancel stuck orders
"""

import json
from pathlib import Path
from binance_api import BinanceAPI
from config import BINANCE_API_KEY, BINANCE_API_SECRET, SYMBOL, DEMO_MODE

def main():
    print("=== Trade State Cleanup ===\n")
    
    # Initialize Binance client
    client = BinanceAPI(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=DEMO_MODE)
    
    # Get all open orders
    open_orders = client.get_open_orders(SYMBOL)
    if open_orders:
        print(f"Found {len(open_orders)} open orders:")
        for order in open_orders:
            print(f"  Order {order['orderId']}: {order['side']} {order['type']} @ ${order.get('price')} - Status: {order['status']}")
            
            # Ask to cancel
            response = input(f"\nCancel order {order['orderId']}? (y/n): ")
            if response.lower() == 'y':
                cancelled = client.cancel_order(SYMBOL, order['orderId'])
                if cancelled:
                    print(f"✓ Cancelled order {order['orderId']}")
                else:
                    print(f"✗ Failed to cancel order {order['orderId']}")
    else:
        print("No open orders found")
    
    # Load trade state
    state_file = Path(__file__).parent / "trade_state.json"
    with open(state_file, 'r') as f:
        state = json.load(f)
    
    print(f"\n=== Current Trade State ===")
    print(f"Open trades: {len(state['open_trades'])}")
    print(f"Closed trades: {len(state['closed_trades'])}")
    
    # Ask about clearing closed trades
    if state['closed_trades']:
        print(f"\nClosed trades:")
        for trade in state['closed_trades']:
            print(f"  {trade['trade_id']}: Entry ${trade['entry_price']} -> Exit ${trade.get('exit_price', 'N/A')} | PnL: ${trade.get('pnl', 0):.2f}")
        
        response = input("\nClear phantom closed trades? (y/n): ")
        if response.lower() == 'y':
            state['closed_trades'] = []
            with open(state_file, 'w') as f:
                json.dump(state, f, indent=2)
            print("✓ Cleared closed trades from state")
    
    print("\n✓ Cleanup complete")

if __name__ == "__main__":
    main()
